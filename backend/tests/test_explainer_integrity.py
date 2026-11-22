from __future__ import annotations

from copy import deepcopy
import json
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import pipeline
from app.llm import Explanation, MockExplainer, RCDExplainer, _check_citations, explainer_key, get_explainer
from scripts.benchmark_models import summarize


@pytest.fixture(scope="module")
def analysis():
    return pipeline.run_synthetic(duration_s=90, seed=3, attacks=["dos", "spoofing", "masquerade"])


def test_unknown_count_is_exact_over_merged_alert(analysis):
    found = False
    for alert in analysis.alerts:
        evidence = analysis.evidence_for(alert.alert_id)
        segment = analysis.df[(analysis.df.timestamp >= alert.start) & (analysis.df.timestamp < alert.end)]
        for item in evidence["items"]:
            if item["kind"] == "unknown_id":
                found = True
                detail = item["detail"]
                expected = int((segment.can_id == int(detail["can_id"], 16)).sum())
                assert detail["count"] == detail["alert_count"] == expected
                assert detail["count_scope"] == "full_alert"
                assert detail["alert_mean_rate"] == pytest.approx(expected / (alert.end - alert.start), abs=.001)
    assert found


def test_prompt_contains_control_jitter_measurement(analysis):
    evidence = analysis.evidence_for(analysis.alerts[-1].alert_id)
    prompt = RCDExplainer()._user_prompt(evidence)
    packet = json.loads(prompt.removeprefix("Evidence packet:\n"))
    for original, sent in zip(evidence["items"], packet["evidence"]):
        assert sent["detail"] == original["detail"]
    assert "true_type" not in prompt and "attack_intervals" not in prompt


def packet(stats):
    return {"window_start": 0., "window_end": 1., "frame_count": 100,
            "detector_score": .8, "detector_components": {}, "ids_involved": [],
            "sample_frames": [], "items": [{"id": "E0", "kind": "bus_load", "detail": {"observed": 100, "baseline": 100}, "text": "load"}] + stats}


def stat(index, ratio=1., jitter=0.):
    return {"id": f"E{index}", "kind": "id_stats", "text": "stats", "detail": {
        "can_id": f"0x{index:03X}", "count": 20, "jitter_ratio": jitter, "rate_ratio": ratio,
        "rate": 20 * ratio, "baseline_rate": 20, "entropy_delta": 0}}


def test_zero_jitter_is_not_replaced_by_missing_default():
    assert MockExplainer().explain(packet([stat(1)])).attack_type == "masquerade"


def test_multiple_inflated_ids_do_not_prove_replay():
    result = MockExplainer().explain(packet([stat(i, ratio=2, jitter=1) for i in range(1, 4)]))
    assert result.attack_type == "spoofing"
    assert all("duplicated" not in claim["text"] for claim in result.claims)


def test_high_priority_flood_does_not_require_bus_load_doubling():
    evidence = packet([{"id": "E1", "kind": "unknown_id", "text": "priority flood",
                        "detail": {"can_id": "0x000", "count": 500, "alert_mean_rate": 500}}])
    assert MockExplainer().explain(evidence).attack_type == "dos"
    evidence["items"][1]["detail"]["alert_mean_rate"] = 1
    assert MockExplainer().explain(evidence).attack_type != "dos"


def test_empty_claims_are_not_grounded():
    exp = Explanation("unknown", .5, "low", "unknown", "summary", [])
    assert not _check_citations(exp, packet([])).grounded


@pytest.mark.parametrize("field,value", [("confidence", float("nan")), ("confidence", 2), ("claims", []), ("claims", ["bad"]), ("severity", "critical"), ("attack_type", "fabrication")])
def test_malformed_response_rejected(field, value):
    payload = {"attack_type": "dos", "confidence": .8, "severity": "high", "claims": [{"text": "load", "cites": ["E0"]}]}
    payload[field] = value
    with pytest.raises(ValueError):
        RCDExplainer()._parse(json.dumps(payload), packet([]), "model")


def test_model_selectors_preserve_case_and_cache_settings(monkeypatch):
    a = get_explainer("rcd:MixedCaseModel")
    assert a.model == "MixedCaseModel"
    b = get_explainer("rcd:MixedCaseModel")
    b.temperature = .5
    assert explainer_key(a) != explainer_key(b)
    b.temperature = a.temperature
    b.base_url = "https://example.test/v1"
    assert explainer_key(a) != explainer_key(b)
    with pytest.raises(ValueError):
        get_explainer("typo")


def test_failed_model_is_not_scored_using_control_prediction():
    records = [{"true_type": "dos", "explanation": {"attack_type": "dos", "fallback": True, "latency_s": 1, "grounded": True}, "estimated_cost_usd": None},
               {"true_type": "dos", "explanation": {"attack_type": "dos", "fallback": False, "latency_s": 3, "grounded": True}, "estimated_cost_usd": None}]
    result = summarize(records)
    assert result["classification"]["accuracy"] == .5
    assert result["classification"]["successful_only_accuracy"] == 1
    assert result["fallbacks"] == 1
    assert result["latency_s_median"] == 3
    assert result["estimated_cost_usd"] is None


def test_parse_failure_preserves_token_usage_and_finish_reason(monkeypatch):
    from types import SimpleNamespace as NS
    response = NS(model="served-model", choices=[NS(finish_reason="length", message=NS(content=""))],
                  usage=NS(prompt_tokens=90, completion_tokens=1800,
                           completion_tokens_details=NS(reasoning_tokens=1800)))
    ex = RCDExplainer()
    def create(**kwargs):
        assert kwargs["reasoning_effort"] == "low"
        return response
    monkeypatch.setattr(ex, "_client", lambda: NS(chat=NS(completions=NS(create=create))))
    result = ex.explain(packet([]))
    assert result.fallback and result.error_type == "JSONDecodeError"
    assert result.usage == {"input_tokens": 90, "output_tokens": 1800, "reasoning_tokens": 1800}
    assert result.finish_reason == "length" and result.response_model == "served-model"


def test_benchmark_resume_reuses_paid_responses_and_rejects_changed_corpus(tmp_path, monkeypatch):
    from scripts import benchmark_models as runner
    calls = []
    class Counted(MockExplainer):
        def explain(self, evidence):
            calls.append(1)
            return super().explain(evidence)
    monkeypatch.setattr(runner, "get_explainer", lambda kind: Counted())
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **k: "test-revision")
    corpus = tmp_path / "corpus.json"
    row = {"capture": "test", "alert_id": 0, "true_type": "dos", "evidence": packet([])}
    corpus.write_text(json.dumps({"dataset": "test", "alerts": [row]}))
    monkeypatch.setattr(sys, "argv", ["benchmark", "--corpus", str(corpus), "--model", "mock", "--workers", "1", "--out", str(tmp_path / "run"), "--env-file", str(tmp_path / "missing.env")])
    runner.main()
    runner.main()
    assert len(calls) == 1
    row["evidence"]["frame_count"] += 1
    corpus.write_text(json.dumps({"dataset": "test", "alerts": [row]}))
    with pytest.raises(SystemExit):
        runner.main()
    assert len(calls) == 1


def test_sparse_rate_ratio_and_unmeasured_iat_have_truthful_units():
    import pandas as pd
    from app.features import Baseline, extract_windows
    from app.detector import Alert
    from app.evidence import build_evidence
    frame = pd.DataFrame({"timestamp": [.1], "can_id": [0x25], "dlc": [1], "data": [[0]], "label": [0], "attack_type": ["normal"]})
    baseline = Baseline(known_ids={0x25}, rate={0x25: 1.}, iat_mean={0x25: 1.}, total_rate=1.)
    windows = extract_windows(frame, baseline)
    alert = Alert(0, 0, 0., .5, .6, {}, [], [0x25])
    evidence = build_evidence(alert, frame, windows, baseline)
    item = next(i for i in evidence["items"] if i["kind"] == "id_stats")
    detail = item["detail"]
    assert detail["rate"] == 2. and detail["baseline_rate"] == 1.
    assert detail["rate_ratio"] == 2.
    assert detail["detector_rate_ratio"] == pytest.approx(1 / 3, abs=.001)
    assert detail["detector_rate_reference"] == 6.
    assert detail["iat_mean_ms"] is None and detail["jitter_ratio"] is None
    assert detail["bitflip_rate"] is None and detail["bitflip_delta"] is None
    assert "raw observed/baseline 2.0x" in item["text"]
    assert "gap and jitter unavailable" in item["text"]
    # Control keeps its minimum expected count safeguard, despite raw 2x ratio.
    assert MockExplainer().explain(evidence).attack_type != "spoofing"


def test_unknown_ids_have_no_invented_payload_or_timing_baseline(analysis):
    found = False
    for alert in analysis.alerts:
        evidence = analysis.evidence_for(alert.alert_id)
        for item in evidence["items"]:
            if item["kind"] != "unknown_id":
                continue
            found = True
            detail = item["detail"]
            assert detail["baseline_available"] is False
            for key in ("baseline_entropy", "entropy_delta", "baseline_iat_ms", "iat_z", "jitter_ratio", "bitflip_delta", "rate_ratio"):
                assert detail[key] is None, key
            assert detail["alert_entropy"] >= 0
            assert detail["alert_mean_rate"] > 0
    assert found


def test_below_baseline_bus_load_is_not_described_as_a_rise():
    evidence = packet([{"id": f"E{i}", "kind": "unknown_id", "text": "unknown ID",
                        "detail": {"can_id": f"0x{i:03X}", "count": 1}} for i in (1, 2)])
    evidence["items"][0]["detail"]["observed"] = 67
    result = MockExplainer().explain(evidence)
    assert result.attack_type == "fuzzing"
    assert any("Bus load was 0.67x baseline" in c["text"] for c in result.claims)
    assert not any("rose" in c["text"] for c in result.claims)


def test_fuzzing_count_cites_every_retained_unknown_id():
    evidence = packet([{"id": f"E{i}", "kind": "unknown_id", "text": "unknown ID",
                        "detail": {"can_id": f"0x{i:03X}", "count": 1}} for i in range(1, 7)])
    result = MockExplainer().explain(evidence)
    claim = next(c for c in result.claims if "6 arbitration IDs" in c["text"])
    assert result.attack_type == "fuzzing"
    assert set(claim["cites"]) == {f"E{i}" for i in range(1, 7)}
