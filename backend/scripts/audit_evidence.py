"""Read-only frozen evidence arithmetic/missingness audit; no model calls.

python -m scripts.audit_evidence --corpus-dir out/frozen_2026-10-30_v4 \
  --out out/semantic_audit_2026-10-30/numeric_validation_v4.json

Exit status 1 means evidence defects. Passing is not raw-frame or semantic validation.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOLERANCES = {"duration_s": .0006, "window_rate": .0051,
              "alert_rate_and_ratios": .00051, "entropy_delta": .00151}


def audit(paths: list[Path]) -> dict:
    sources, arithmetic, missing = {}, [], []
    checked, counts = Counter(), Counter()
    for path in paths:
        raw = path.read_bytes()
        source = str(path.resolve().relative_to(ROOT)) if path.resolve().is_relative_to(ROOT) else str(path.resolve())
        sources[source] = hashlib.sha256(raw).hexdigest()
        corpus = json.loads(raw)
        for index, row in enumerate(corpus["alerts"]):
            evidence = row["evidence"]
            counts["alerts"] += 1
            location = {"dataset": corpus["dataset"], "corpus_index": index,
                        "capture": row["capture"], "alert_id": row["alert_id"]}

            def check(name, ok, item="E0", values=None, schema=False):
                checked[name] += 1
                if not ok:
                    (missing if schema else arithmetic).append(
                        {**location, "item": item, "check": name, "values": values})

            def approximately(name, actual, expected, tolerance, item="E0"):
                valid = isinstance(actual, (int, float)) and math.isfinite(actual)
                check(name, valid and abs(actual - expected) <= tolerance,
                      item, {"actual": actual, "expected": expected})

            duration = evidence["window_end"] - evidence["window_start"]
            check("positive_alert_duration", duration > 0, values=duration)
            if duration <= 0:
                continue
            approximately("alert_duration", evidence["duration_s"], duration, TOLERANCES["duration_s"])
            for item in evidence["items"]:
                value, kind, item_id = item["detail"], item["kind"], item["id"]
                counts[kind] += 1
                if kind == "bus_load":
                    check("peak_bus_rate_at_least_full_alert_mean",
                          value["observed"] + .01 >= evidence["frame_count"] / duration, item_id)
                if kind not in {"id_stats", "unknown_id"}:
                    continue
                window = value["statistics_end"] - value["statistics_start"]
                check("positive_statistics_duration", window > 0, item_id, window)
                if window <= 0:
                    continue
                count = value["window_count"]
                approximately("window_rate_equals_count_over_duration", value["rate"], count / window,
                              TOLERANCES["window_rate"], item_id)
                approximately("alert_rate_equals_count_over_duration", value["alert_mean_rate"],
                              value["alert_count"] / duration, TOLERANCES["alert_rate_and_ratios"], item_id)
                check("id_alert_count_within_total", 0 <= value["alert_count"] <= evidence["frame_count"], item_id)
                check("statistics_window_within_alert", evidence["window_start"] <= value["statistics_start"]
                      < value["statistics_end"] <= evidence["window_end"], item_id)
                if kind == "id_stats":
                    check("positive_known_baseline_rate", value["baseline_rate"] > 0, item_id)
                    if value["baseline_rate"] > 0:
                        approximately("raw_rate_ratio", value["rate_ratio"], value["rate"] / value["baseline_rate"],
                                      TOLERANCES["alert_rate_and_ratios"], item_id)
                    reference = value.get("detector_rate_reference")
                    check("guarded_reference_present_positive", isinstance(reference, (float, int)) and reference > 0,
                          item_id, reference)
                    if reference and reference > 0:
                        approximately("guarded_rate_ratio", value["detector_rate_ratio"], value["rate"] / reference,
                                      TOLERANCES["alert_rate_and_ratios"], item_id)
                    approximately("entropy_delta", value["entropy_delta"], value["entropy"] - value["baseline_entropy"],
                                  TOLERANCES["entropy_delta"], item_id)
                else:
                    keys = ["baseline_entropy", "entropy_delta", "baseline_iat_ms", "iat_z", "jitter_ratio", "bitflip_delta"]
                    fields = {key: value.get(key) for key in keys}
                    check("unknown_id_baseline_comparisons_null", all(v is None for v in fields.values()),
                          item_id, fields, schema=True)
                    check("unknown_id_baseline_unavailable", value.get("baseline_available") is False,
                          item_id, value.get("baseline_available"), schema=True)
                if count < 2:
                    keys = ["iat_mean_ms", "iat_std_ms", "iat_z", "jitter_ratio"]
                    fields = {key: value.get(key) for key in keys}
                    check("single_frame_timing_null", all(v is None for v in fields.values()),
                          item_id, fields, schema=True)
                    fields = {key: value.get(key) for key in ["bitflip_rate", "bitflip_delta"]}
                    check("single_frame_bitflip_null", all(v is None for v in fields.values()),
                          item_id, fields, schema=True)
                    check("single_frame_iat_unavailable", value.get("iat_available") is False,
                          item_id, value.get("iat_available"), schema=True)
                if value.get("iat_mean_ms") is not None:
                    check("iat_mean_fits_statistics_window", value["iat_mean_ms"] * (count - 1)
                          <= window * 1000 + .005 * max(1, count), item_id)
    return {
        "review_type": "Automated numerical/schema audit authored by AI; not human semantic review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auditor_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_sha256": sources,
        "scope": "Read-only arithmetic, count/duration, bounds and missingness checks on frozen evidence",
        "rounding_tolerances": TOLERANCES, "item_counts": dict(counts),
        "checks_performed": dict(checked), "total_checks": sum(checked.values()),
        "arithmetic_or_bound_failures": arithmetic, "schema_issues": missing,
        "schema_issue_counts": dict(Counter(item["check"] for item in missing)),
        "passed": not arithmetic and not missing,
        "limitations": "No independent raw-frame feature or label recomputation. Passing does not validate causal claims, model labels, or analyst usefulness.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.corpus_dir.glob("*.json"))
    if not paths:
        parser.error("No corpus JSON files found")
    if args.out.exists():
        parser.error("Output exists; choose a new path to preserve the earlier audit")
    result = audit(paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "alerts": result["item_counts"].get("alerts", 0),
                      "total_checks": result["total_checks"],
                      "arithmetic_failures": len(result["arithmetic_or_bound_failures"]),
                      "schema_issue_counts": result["schema_issue_counts"]}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
