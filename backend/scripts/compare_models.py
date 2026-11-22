"""Compare complete runs on exactly matched evidence; never calls a model.

Reports empirical paired outcomes, not statistical equivalence: development
alerts can overlap and share source captures.
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.benchmark_models import atomic_write, summarize


def validated_records(run):
    if run.get("status") not in {"complete", "complete_with_failures"}:
        raise ValueError("Paired comparisons require completed attempts")
    if (run.get("manifest") or {}).get("limit") is not None:
        raise ValueError("Smoke-test prefixes cannot establish full-corpus parity")
    rows = run.get("alerts", [])
    if not run.get("corpus_sha256") or len(rows) != run.get("expected_alerts"):
        raise ValueError("Missing corpus identity or incomplete alert set")
    indexed = {r["corpus_index"]: r for r in rows}
    if len(indexed) != len(rows) or set(indexed) != set(range(len(rows))):
        raise ValueError("Duplicate or missing corpus indices")
    if not all(r.get("evidence_sha256") for r in rows):
        raise ValueError("Every record must identify its exact evidence")
    return indexed


def compare(control, model):
    controls, models = validated_records(control), validated_records(model)
    if (control["dataset"] != model["dataset"] or control["corpus_sha256"] != model["corpus_sha256"]
            or set(controls) != set(models)):
        raise ValueError("Runs do not use the same full evidence corpus")
    counts = dict(both_correct=0, control_only_correct=0, model_only_correct=0, neither_correct=0)
    errors = []
    for i, a in controls.items():
        b = models[i]
        keys = ("capture", "alert_id", "start", "end", "true_type", "evidence_sha256")
        if any(a.get(k) != b.get(k) for k in keys):
            raise ValueError(f"Mismatched evidence or target at corpus index {i}")
        truth = a["true_type"]
        if truth in {"normal", "benign", "unknown", "injected", ""}:
            continue
        ac = not a["explanation"].get("fallback") and a["explanation"]["attack_type"] == truth
        bc = not b["explanation"].get("fallback") and b["explanation"]["attack_type"] == truth
        bucket = ("both_correct" if ac and bc else "control_only_correct" if ac
                  else "model_only_correct" if bc else "neither_correct")
        counts[bucket] += 1
        if not (ac and bc):
            errors.append({"corpus_index": i, "capture": a.get("capture"), "alert_id": a["alert_id"],
                           "true_type": truth, "control_prediction": a["explanation"]["attack_type"],
                           "model_prediction": "request_failed" if b["explanation"].get("fallback") else b["explanation"]["attack_type"],
                           "paired_outcome": bucket})
    n = sum(counts.values())
    return {"dataset": control["dataset"], "corpus_sha256": control["corpus_sha256"],
            "control": control["model"], "model": model["model"], "matched_alerts": len(controls),
            "matched_attack_alerts": n, "paired_attack_outcomes": counts,
            "model_minus_control_accuracy": (counts["model_only_correct"] - counts["control_only_correct"]) / n if n else None,
            "observed_accuracy_at_least_control": counts["model_only_correct"] >= counts["control_only_correct"] if n else None,
            "control_summary": summarize(list(controls.values())), "model_summary": summarize(list(models.values())),
            "errors": errors,
            "interpretation": "Observed paired outcomes on this development corpus only, not statistical equivalence, held-out validation, or evidence of analyst benefit. Alerts may overlap and share captures."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    control = json.loads(args.control.read_text())
    results = []
    try:
        for path in args.run:
            result = compare(control, json.loads(path.read_text()))
            result["source_sha256"] = {"control": hashlib.sha256(args.control.read_bytes()).hexdigest(),
                                       "model": hashlib.sha256(path.read_bytes()).hexdigest()}
            result["source_paths"] = {"control": str(args.control), "model": str(path)}
            results.append(result)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    atomic_write(args.out, {"comparisons": results})
    for result in results:
        print(f"{result['dataset']} {result['model']}: accuracy delta {result['model_minus_control_accuracy']}; {result['paired_attack_outcomes']}")


if __name__ == "__main__":
    main()
