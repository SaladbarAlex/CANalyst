from copy import deepcopy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.compare_models import compare


def run(predictions):
    rows = [{"corpus_index": i, "capture": "capture", "alert_id": i, "start": i, "end": i + 1,
             "evidence_sha256": f"evidence-{i}", "true_type": "dos", "estimated_cost_usd": None,
             "explanation": {"attack_type": p, "fallback": False, "latency_s": 1, "grounded": True}}
            for i, p in enumerate(predictions)]
    return {"status": "complete", "dataset": "test", "corpus_sha256": "same-corpus", "expected_alerts": len(rows),
            "model": "example", "alerts": rows}


def test_paired_errors_distinguish_equal_aggregate_accuracy():
    result = compare(run(["dos", "spoofing"]), run(["spoofing", "dos"]))
    assert result["model_minus_control_accuracy"] == 0
    assert result["paired_attack_outcomes"] == {"both_correct": 0, "neither_correct": 0, "control_only_correct": 1, "model_only_correct": 1}
    assert len(result["errors"]) == 2


@pytest.mark.parametrize("mutation", ["hash", "target", "missing", "duplicate", "running", "corpus", "smoke"])
def test_incompatible_or_incomplete_runs_cannot_claim_parity(mutation):
    control = run(["dos", "dos"])
    model = deepcopy(control)
    if mutation == "hash": model["alerts"][0]["evidence_sha256"] = "different"
    elif mutation == "target": model["alerts"][0]["true_type"] = "spoofing"
    elif mutation == "missing": model["alerts"].pop()
    elif mutation == "duplicate": model["alerts"][1]["corpus_index"] = 0
    elif mutation == "running": model["status"] = "running"
    elif mutation == "corpus": model["corpus_sha256"] = "different"
    elif mutation == "smoke": model["manifest"] = {"limit": 2}
    with pytest.raises(ValueError): compare(control, model)


def test_model_failure_never_inherits_control_correctness():
    model = run(["dos"])
    model["alerts"][0]["explanation"]["fallback"] = True
    model["status"] = "complete_with_failures"
    result = compare(run(["dos"]), model)
    assert result["model_minus_control_accuracy"] == -1
    assert result["errors"][0]["model_prediction"] == "request_failed"


def test_binary_attack_label_does_not_claim_attack_type_accuracy():
    control = run(["dos"])
    control["alerts"][0]["true_type"] = "injected"
    result = compare(control, deepcopy(control))
    assert result["matched_attack_alerts"] == 0
    assert result["observed_accuracy_at_least_control"] is None
    assert result["model_summary"]["classification"]["accuracy"] is None
