"""Paired rule/forest development benchmark with normal-only fitting.

Run from backend: .venv/bin/python -u -m scripts.evaluate_detectors --dataset road --baseline-profile broad
All choices are fixed before evaluation. Results preserve midterm artifacts.
ROAD profiles keep whole ambient recordings out of training.
"""
from __future__ import annotations
import argparse
import gc
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from app import features, loader, metrics
from app.detector import ForestDetector, RuleDetector
from scripts.evaluate_midterm import BACKEND, capture, git_state, pooled, sha256

WINDOW_S, STRIDE_S, THRESHOLD, PREFIX_S = 0.5, 0.25, 0.55, 120.0
BROAD_BASELINES = ["ambient_dyno_drive_basic_short", "ambient_dyno_drive_extended_long",
                   "ambient_dyno_reverse", "ambient_dyno_idle_radio_infotainment",
                   "ambient_dyno_drive_radio_infotainment"]


def protocol(dataset: str, profile: str) -> tuple[list, list, list]:
    if dataset == "hcrl":
        raw = BACKEND / "data/raw/hcrl-car-hacking"
        normal = raw / "normal_run_data/normal_run_data.txt"
        baselines = [(normal, 0.0, 120.0)]
        jobs = [(raw / f"{name}_dataset.csv", 0.0, 120.0, "attack_capture")
                for name in ["DoS", "Fuzzy", "RPM", "gear"]]
        jobs.append((normal, 121.0, 241.0, "held_out_normal"))
        return baselines, jobs, []
    raw = BACKEND / "data/raw/road/road"
    meta = json.loads((raw / "attacks/capture_metadata.json").read_text())
    jobs = [(raw / f"attacks/{name}.log", 0.0, None, "attack_capture")
            for name, entry in sorted(meta.items()) if entry.get("injection_interval")]
    excluded = [name for name, entry in sorted(meta.items()) if not entry.get("injection_interval")]
    if profile == "broad":
        baselines = [(raw / f"ambient/{name}.log", 0.0, PREFIX_S) for name in BROAD_BASELINES]
        holdouts = sorted(p for p in (raw / "ambient").glob("*.log") if p.stem not in BROAD_BASELINES)
    else:
        baselines = [(raw / "ambient/ambient_dyno_drive_basic_short.log", 0.0, None)]
        holdouts = [raw / f"ambient/{name}.log" for name in
                    ["ambient_dyno_drive_basic_long", "ambient_dyno_drive_extended_short"]]
    jobs += [(path, 0.0, PREFIX_S, "held_out_normal") for path in holdouts]
    assert not ({p for p, _, _ in baselines} & {p for p, _, _, _ in jobs})
    return baselines, jobs, excluded


def split_by_capture(windows: pd.DataFrame, normal: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out each operating state's later windows without sharing frames."""
    ranges = normal.groupby("_capture_id").timestamp.agg(["min", "max"])
    training, calibration = [], []
    for interval in ranges.itertuples():
        group = windows[(windows.start >= interval.min) & (windows.end <= interval.max)]
        if len(group) < 25:
            raise ValueError("Each normal capture needs at least 25 complete windows for a per-capture split.")
        cut = float(group.iloc[int(len(group) * 0.8)].start)
        training.append(group[group.end <= cut])
        calibration.append(group[group.start >= cut])
    return pd.concat(training, ignore_index=True), pd.concat(calibration, ignore_index=True)


def run(dataset: str, profile: str, output: Path, forest_split: str = "temporal") -> dict:
    out = output.resolve() / (f"{dataset}_{profile}" + ("_per_capture" if forest_split == "per_capture" else ""))
    out.mkdir(parents=True, exist_ok=True)
    result_path = out / "results.json"
    if result_path.exists():
        raise ValueError(f"Refusing to overwrite existing benchmark: {result_path}")
    baseline_jobs, jobs, excluded = protocol(dataset, profile)
    started = time.perf_counter()
    report = {
        "dataset": dataset, "baseline_profile": profile, "forest_split": forest_split, "status": "running",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "stage": "development benchmark; no untouched final-test claim",
            "window_s": WINDOW_S, "stride_s": STRIDE_S, "threshold": THRESHOLD,
            "forest": "200 trees; random_state=0; 1% normal calibration quantile; fixed sigmoid scores; "
                      "early 80% normal time fit and later 20% calibration, with crossing windows discarded; "
                      "per_capture applies this split separately to every recording",
            "comparison": "Both detectors score identical extracted evaluation features; forest includes jitter-collapse count",
            "baseline_profile": profile, "forest_split": forest_split,
            "normal_scope": "HCRL: [0,120) baseline and [121,241) holdout from same recording. "
                            "ROAD: baseline recordings wholly excluded from normal evaluation. Broad profile uses "
                            "120 s of each of five varied normal recordings, evaluates remaining seven ambient prefixes.",
            "labels": "HCRL supplied frame labels; ROAD interval/ID-derived labels, whole-interval fuzzing",
            "limitations": "Overlapping windows, HCRL shared normal source, related ROAD fabrication/masquerade pairs, "
                           "prior development on these datasets, and one partially observed tail window per capture. "
                           "False-positive improvements do not establish transfer to unseen vehicles.",
            "llm_calls": 0,
        },
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "git": git_state()},
        "code_sha256": {name: sha256(BACKEND / name) for name in
                        ["app/loader.py", "app/features.py", "app/detector.py", "app/metrics.py",
                         "scripts/evaluate_midterm.py", "scripts/evaluate_detectors.py"]},
        "excluded_unlabeled_attacks": excluded, "baseline_inputs": [], "captures": [],
    }
    for name, expected_hash in report["code_sha256"].items():
        snapshot = out / "source_snapshot" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((BACKEND / name).read_bytes())
        if sha256(snapshot) != expected_hash:
            raise RuntimeError("Source changed during benchmark initialization; rerun with stable code.")
    baseline_parts = []
    for path, start, stop in baseline_jobs:
        print(f"baseline {path.name} [{start}, {stop})", flush=True)
        df, record = capture(path, out, start=start, stop=stop)
        if (df.label != 0).any():
            raise ValueError(f"Attack-contaminated baseline: {path}")
        baseline_parts.append(df)
        report["baseline_inputs"].append(record)
    normal = loader.concat_captures(baseline_parts)
    baseline = features.learn_baseline(normal, float("inf"), window_s=WINDOW_S)
    train_windows = features.extract_windows(normal, baseline, WINDOW_S, STRIDE_S)
    forest = ForestDetector(baseline, threshold=THRESHOLD)
    if forest_split == "per_capture":
        training, calibration = split_by_capture(train_windows, normal)
        forest.fit(training, calibration)
        del training, calibration
    else:
        forest.fit(train_windows)
    detectors = {"rule": RuleDetector(baseline, THRESHOLD), "forest": forest}
    report["forest_calibration"] = forest.calibration
    report["baseline"] = baseline.to_json()
    report["baseline_seconds"] = time.perf_counter() - started
    del baseline_parts, normal, train_windows, df
    gc.collect()
    result_path.write_text(json.dumps(report, indent=2) + "\n")
    for path, start, stop, role in jobs:
        print(f"evaluate {path.name} [{start}, {stop})", flush=True)
        before = time.perf_counter()
        df, record = capture(path, out, start=start, stop=stop)
        loaded = time.perf_counter()
        windows = features.extract_windows(df, baseline, WINDOW_S, STRIDE_S)
        featured = time.perf_counter()
        entry = {"capture": path.stem, "role": role, "input": record,
                 "ingest_s": loaded - before, "feature_s": featured - loaded, "detectors": {}}
        for kind, detector in detectors.items():
            score_start = time.perf_counter()
            scored, alerts = detector.run(windows)
            elapsed = time.perf_counter() - score_start
            score_path = out / f"{path.stem}__{role}__{kind}_windows.csv.gz"
            scored[["start", "end", "label", "attack_type", "score", "flagged"]].to_csv(score_path, index=False)
            entry["detectors"][kind] = {
                "detection": metrics.detection_metrics(scored), "alerts": len(alerts),
                "score_s": elapsed, "score_windows_per_s": len(scored) / max(elapsed, 1e-9),
                "ingest_features_score_frames_per_s": len(df) / max(featured - before + elapsed, 1e-9),
                "scores": str(score_path.relative_to(out)), "scores_sha256": sha256(score_path),
            }
        report["captures"].append(entry)
        result_path.write_text(json.dumps(report, indent=2) + "\n")
        del df, windows, scored
        gc.collect()
    report["pooled"] = {}
    for kind in detectors:
        report["pooled"][kind] = {}
        for scope in ["all", "attack_capture", "held_out_normal"]:
            selected = [c for c in report["captures"] if scope == "all" or c["role"] == scope]
            report["pooled"][kind][scope] = pooled([
                {"input": c["input"], "detection": c["detectors"][kind]["detection"]} for c in selected])
    report["elapsed_s"] = time.perf_counter() - started
    report["status"] = "complete"
    result_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["pooled"], indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["hcrl", "road"], required=True)
    parser.add_argument("--baseline-profile", choices=["midterm", "broad"], default="midterm")
    parser.add_argument("--forest-split", choices=["temporal", "per_capture"], default="temporal")
    parser.add_argument("--out", type=Path, default=BACKEND / "out" / "detectors_2026-10-30")
    args = parser.parse_args()
    if args.dataset == "hcrl" and args.baseline_profile != "midterm":
        parser.error("HCRL has one normal recording; broad profile applies only to ROAD.")
    run(args.dataset, args.baseline_profile, args.out, args.forest_split)


if __name__ == "__main__":
    main()
