"""Evaluate the predeclared experimental state/window detector on ROAD.

No thresholds are selected using attack or held-out normal evaluation labels.
The split and parameters live in app/state_detector.py and are saved verbatim.
"""
from __future__ import annotations
import argparse
import gc
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from app import metrics
from app.state_detector import StateDetector
from scripts.evaluate_detectors import protocol
from scripts.evaluate_midterm import BACKEND, capture, pooled, sha256


def run(profile: str, output: Path) -> dict:
    out = output.resolve() / f"road_{profile}_state_window"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "results.json"
    if path.exists():
        raise ValueError(f"Refusing to overwrite {path}")
    started = time.perf_counter()
    baselines, jobs, excluded = protocol("road", profile)
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
              "dataset": "road", "baseline_profile": profile, "detector": "state_window",
              "methodology": "Fixed parameters; independent normal temporal split inside each recording; "
                             "same ROAD capture/window scopes as paired detector experiment; no evaluation-label tuning. "
                             "Baseline fits per-window rates/entropy/bitflips/jitter and payload-byte support.",
              "excluded_attacks": excluded, "baseline_inputs": [], "captures": []}
    sources = ["app/state_detector.py", "app/features.py", "app/loader.py", "app/detector.py",
               "app/metrics.py", "scripts/evaluate_state_detector.py", "scripts/evaluate_detectors.py",
               "scripts/evaluate_midterm.py"]
    report["source_sha256"] = {}
    for source in sources:
        target = out / "source_snapshot" / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((BACKEND / source).read_bytes())
        report["source_sha256"][source] = sha256(target)
    normal = []
    for source, start, stop in baselines:
        print(f"normal {source.name}", flush=True)
        df, record = capture(source, out, start=start, stop=stop)
        normal.append(df)
        report["baseline_inputs"].append(record)
    detector = StateDetector().fit(normal)
    report["calibration"] = detector.calibration
    report["fit_s"] = time.perf_counter() - started
    print(json.dumps(detector.calibration, indent=2), flush=True)
    del normal, df
    gc.collect()
    path.write_text(json.dumps(report, indent=2) + "\n")
    comparator = BACKEND / "out/detectors_2026-10-30" / f"road_{profile}"
    reference = json.loads((comparator / "results.json").read_text())
    reference_captures = {item["capture"]: item for item in reference["captures"]}
    report["paired_reference"] = {"path": str(comparator.relative_to(BACKEND)),
                                  "results_sha256": sha256(comparator / "results.json")}
    for source, start, stop, role in jobs:
        print(f"score {source.name}", flush=True)
        before = time.perf_counter()
        df, record = capture(source, out, start=start, stop=stop)
        loaded = time.perf_counter()
        windows, alerts = detector.run(df)
        elapsed = time.perf_counter() - loaded
        reference_capture = reference_captures[source.stem]
        expected = pd.read_csv(comparator / reference_capture["detectors"]["rule"]["scores"])
        for column in ["start", "end", "label", "attack_type"]:
            if windows[column].tolist() != expected[column].tolist():
                raise ValueError(f"Unpaired evaluation windows for {source.name}: {column}")
        score_path = out / f"{source.stem}__{role}_windows.csv.gz"
        compact = windows[["start", "end", "label", "attack_type", "score", "flagged"]].copy()
        for key in detector.cutoffs:
            compact[key] = [item[key] for item in windows.components]
        compact.to_csv(score_path, index=False)
        report["captures"].append({"capture": source.stem, "role": role, "input": record,
                                   "detection": metrics.detection_metrics(windows), "alerts": len(alerts),
                                   "ingest_s": loaded - before, "features_score_s": elapsed,
                                   "end_to_end_frames_per_s": len(df) / (time.perf_counter() - before),
                                   "scores": score_path.name, "scores_sha256": sha256(score_path),
                                   "paired_reference_verified": True})
        path.write_text(json.dumps(report, indent=2) + "\n")
        del df, windows, compact
        gc.collect()
    report["pooled"] = {role: pooled([c for c in report["captures"] if role == "all" or c["role"] == role])
                        for role in ["all", "attack_capture", "held_out_normal"]}
    report["per_attack_type"] = {}
    for item in report["captures"]:
        for attack, counts in item["detection"]["per_attack_type"].items():
            entry = report["per_attack_type"].setdefault(attack, {"windows": 0, "detected": 0})
            entry["windows"] += counts["windows"]
            entry["detected"] += counts["detected"]
    for value in report["per_attack_type"].values():
        value["recall"] = value["detected"] / value["windows"]
    report["elapsed_s"] = time.perf_counter() - started
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pooled": report["pooled"], "per_attack_type": report["per_attack_type"]}, indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-profile", choices=["midterm", "broad"], default="broad")
    parser.add_argument("--out", type=Path, default=BACKEND / "out/detectors_2026-10-30")
    args = parser.parse_args()
    run(args.baseline_profile, args.out)


if __name__ == "__main__":
    main()
