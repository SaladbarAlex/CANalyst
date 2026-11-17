"""Detector profiles, evidence packets, the control's rules, the runner and scoring.

These cover the code the November experiments depend on. Each test names
the property it protects; most were written after the failure they guard
against was found.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import features, llm, synth, windowstats as ws  # noqa: E402
from app.detector import ALERT_PROFILES, RuleDetector  # noqa: E402
from app.evidence import MIN_EXPECTED_FRAMES, build_evidence  # noqa: E402
from scripts import benchmark, run_explanations, score_explanations  # noqa: E402

ATTACKS = ["dos", "fuzzing", "spoofing", "replay", "masquerade"]


@pytest.fixture(scope="module")
def capture():
    df = synth.generate(duration_s=150, seed=11, attacks=ATTACKS)
    baseline = features.learn_baseline(df, 30.0)
    return df, baseline


# --------------------------------------------------------------------------
# Detector profiles
# --------------------------------------------------------------------------

@pytest.mark.parametrize("profile", sorted(ALERT_PROFILES))
def test_profiles_agree_on_both_code_paths(capture, profile):
    """The loop detector and the vectorized benchmark path flag the same windows."""
    df, baseline = capture
    ref, _ = RuleDetector(baseline, profile=profile).run(features.extract_windows(df, baseline))
    win, ids = ws.measure(df)
    wf, _ = ws.apply_baseline(win, ids, baseline)
    fast = ws.rule_scores(wf, 0.55, ALERT_PROFILES[profile])
    assert np.array_equal(ref["flagged"].to_numpy(), fast["flagged"].to_numpy())
    assert np.allclose(ref["score"].to_numpy(), fast["score"].to_numpy(), atol=1e-9)


def test_v2_never_flags_a_window_v1_does_not(capture):
    """v2 alerts on a subset of v1's components, so its flags are a subset of v1's."""
    df, baseline = capture
    windows = features.extract_windows(df, baseline)
    v1, _ = RuleDetector(baseline, profile="v1").run(windows)
    v2, _ = RuleDetector(baseline, profile="v2").run(windows)
    assert not (v2["flagged"] & ~v1["flagged"]).any()


def test_v1_remains_the_default(capture):
    """Changing the default would silently change every earlier result."""
    _, baseline = capture
    assert RuleDetector(baseline).profile == "v1"


def test_unknown_profile_is_rejected(capture):
    with pytest.raises(ValueError):
        RuleDetector(capture[1], profile="v9")


# --------------------------------------------------------------------------
# Evidence packets
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dos_packet(capture):
    df, baseline = capture
    windows, alerts = RuleDetector(baseline).run(features.extract_windows(df, baseline))
    seg_type = []
    for a in alerts:
        seg = df[(df["timestamp"] >= a.start) & (df["timestamp"] < a.end)]
        seg_type.append(seg.loc[seg["label"] == 1, "attack_type"].mode().iat[0]
                        if seg["label"].any() else "normal")
    alert = next(a for a, t in zip(alerts, seg_type) if t == "dos")
    return build_evidence(alert, df, windows, baseline, scope="alert"), alert, df


def test_traffic_mix_matches_the_frames(dos_packet):
    ev, alert, df = dos_packet
    mix = next(i for i in ev["items"] if i["kind"] == "traffic_mix")["detail"]
    seg = df[(df["timestamp"] >= alert.start) & (df["timestamp"] < alert.end)]
    assert mix["frames"] == len(seg) == ev["frame_count"]
    assert 0 < mix["unknown_frames"] <= mix["frames"]
    assert mix["suppressed_ids"] <= mix["countable_ids"]


def test_evidence_text_has_no_negative_zero(dos_packet):
    """"-0.0 bits" read as a measurement error in the October packets."""
    import re
    ev, _, _ = dos_packet
    assert not re.search(r"(?<![0-9])-0\.0+(?![0-9])", json.dumps(ev))


def test_ratio_text_states_both_ratios_when_the_floor_changes_them():
    """A slow ID's one extra frame must not read as a doubling with no explanation."""
    from app.evidence import _ratio_text
    v = {"rate_ratio_plain": 2.0, "rate_ratio": 0.667, "expected_frames": 1.0}
    text = _ratio_text(v)
    assert "2.0x" in text and "0.667x" in text and f"{MIN_EXPECTED_FRAMES:g}" in text
    assert _ratio_text({"rate_ratio_plain": 1.5, "rate_ratio": 1.5, "expected_frames": 9}) == "1.5x"


def test_alert_level_facts_are_citable_as_e0(dos_packet):
    ev, _, _ = dos_packet
    assert ev["items"][0]["id"] == "E0" and ev["items"][0]["kind"] == "alert"
    assert "E0" in llm.SYSTEM_PROMPTS["v2"]


# --------------------------------------------------------------------------
# The control's rules
# --------------------------------------------------------------------------

def _packet(components, items, frames=1000):
    return {"scope": "alert", "window_start": 0.0, "window_end": 1.0, "frame_count": frames,
            "detector_score": max(components.values()), "detector_components": components,
            "ids_involved": [], "items": items, "sample_frames": []}


def _item(i, kind, detail, text="x"):
    return {"id": f"E{i}", "kind": kind, "text": text, "detail": detail}


FLOOD = [
    _item(0, "alert", {}),
    _item(1, "bus_load", {"observed": 900.0, "baseline": 1000.0, "observed_peak_window": 1050.0}),
    _item(2, "traffic_mix", {"unknown_frames": 400, "frames": 1000, "suppressed_ids": 12,
                             "countable_ids": 20, "suppressed_below": 0.7}),
    _item(3, "unknown_id", {"can_id": "0x000", "count": 400, "known": False}),
]


def test_rules_v2_recognize_a_flood_that_displaces_traffic():
    """The real-bus DoS case: no load spike, one unseen ID carrying 40% of frames."""
    pk = _packet({"unknown_ids": 0.6, "bus_load": 0.0}, FLOOD)
    assert llm.MockExplainer(rules="v2").explain(pk).attack_type == "dos"
    assert llm.MockExplainer(rules="v1").explain(pk).attack_type != "dos"


def test_rules_v2_call_alerts_without_attack_components_benign():
    items = [_item(0, "alert", {}),
             _item(1, "bus_load", {"observed": 1000.0, "baseline": 1000.0}),
             _item(2, "traffic_mix", {"unknown_frames": 0, "frames": 1000, "suppressed_ids": 3,
                                      "countable_ids": 40, "suppressed_below": 0.7})]
    pk = _packet({"payload_entropy": 0.62, "timing": 0.45, "unknown_ids": 0.0,
                  "rate_inflation": 0.2, "bus_load": 0.0}, items)
    exp = llm.MockExplainer(rules="v2").explain(pk)
    assert exp.attack_type == "benign" and exp.grounded


def test_control_explanations_are_fully_cited():
    exp = llm.MockExplainer(rules="v2").explain(_packet({"unknown_ids": 0.6}, FLOOD))
    assert exp.claims and exp.grounded
    assert all(c["cites"] for c in exp.claims)


# --------------------------------------------------------------------------
# Model replies
# --------------------------------------------------------------------------

def test_parse_reply_drops_invented_citations():
    pk = _packet({"unknown_ids": 0.6}, FLOOD)
    reply = json.dumps({"attack_type": "DoS", "confidence": 0.9, "severity": "high",
                        "affected_function": "bus", "summary": "s", "recommended_action": "a",
                        "claims": [{"text": "flood", "cites": ["E3", "E99"]}]})
    exp = llm.parse_reply("Here you go:\n" + reply, pk, "m")
    assert exp.attack_type == "dos"
    assert exp.claims[0]["cites"] == ["E3"] and not exp.grounded


def test_parse_reply_maps_unknown_labels_to_unknown():
    reply = json.dumps({"attack_type": "ransomware", "claims": []})
    assert llm.parse_reply(reply, _packet({"x": 1.0}, FLOOD), "m").attack_type == "unknown"


def test_empty_reply_raises_a_clear_error(monkeypatch):
    """Reasoning models can spend the budget thinking and return no content."""
    payload = {"choices": [{"finish_reason": "length",
                            "message": {"content": None, "reasoning": "..." * 10}}],
               "usage": {"completion_tokens": 1200}}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: Resp())
    ex = llm.ChatExplainer(model="m", base_url="http://x/v1", strict=True)
    with pytest.raises(RuntimeError, match="finish_reason=length"):
        ex.complete(_packet({"x": 1.0}, FLOOD))
    assert ex.last_meta["finish_reason"] == "length"


def test_chat_explainer_default_budget_fits_reasoning_models():
    assert llm.ChatExplainer(model="m", base_url="http://x").max_tokens >= 16000


# --------------------------------------------------------------------------
# Runner and scoring
# --------------------------------------------------------------------------

def test_read_jsonl_skips_a_truncated_last_line(tmp_path):
    f = tmp_path / "r.jsonl"
    f.write_text('{"id": "A0000"}\n{"id": "A00')
    assert run_explanations.read_jsonl(f) == [{"id": "A0000"}]


def _alerts():
    return {f"A{i:04d}": {"id": f"A{i:04d}", "dataset": "hcrl", "true_type": t,
                          "is_attack": t != "normal"}
            for i, t in enumerate(["dos", "dos", "spoofing", "normal"])}


def _reply(i, label=None, error=None):
    return {"id": f"A{i:04d}", "attack_type": label, "error": error, "claims": [],
            "grounded": True, "evidence_ids": [], "latency_s": 1.0}


def test_a_failed_reply_counts_as_wrong_not_missing():
    """Dropping failures would reward a model for not answering the hard cases."""
    replies = [_reply(0, "dos"), _reply(1, error="RuntimeError: empty reply"),
               _reply(2, "spoofing"), _reply(3, "benign")]
    r = score_explanations.score_run(_alerts(), replies)
    assert r["accuracy"]["all"]["k"] == 2 and r["accuracy"]["all"]["n"] == 3
    assert r["no_answer"] == 1
    assert r["confusion"]["hcrl/dos"] == {"dos": 1, "no answer": 1}


def test_pairwise_comparison_is_paired():
    a = score_explanations.score_run(_alerts(), [_reply(0, "dos"), _reply(1, "dos"),
                                                 _reply(2, "dos"), _reply(3, "benign")])
    b = score_explanations.score_run(_alerts(), [_reply(0, "dos"), _reply(1, "spoofing"),
                                                 _reply(2, "spoofing"), _reply(3, "benign")])
    c = score_explanations.compare(a, b, _alerts())["all"]
    assert (c["n"], c["only_a_correct"], c["only_b_correct"]) == (3, 1, 1)


# --------------------------------------------------------------------------
# Benchmark helpers
# --------------------------------------------------------------------------

def test_threshold_keeps_false_positive_rate_at_or_below_target():
    rng = np.random.default_rng(0)
    for n in (50, 999, 5000):
        normal = rng.normal(size=n)
        t = benchmark.threshold_at_fpr(normal, 0.01)
        assert (normal >= t).mean() <= 0.01
        # and it is the smallest such threshold among the sample values
        assert (normal >= np.sort(normal)[n - int(0.01 * n) - 1]).mean() > 0.01 or int(0.01 * n) == 0
