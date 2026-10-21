"""Reproducible preliminary real-data benchmark, without test-set tuning.

Run from backend:
    .venv/bin/python -u -m scripts.evaluate_midterm --dataset hcrl
    .venv/bin/python -u -m scripts.evaluate_midterm --dataset road

The scope and fixed threshold are declared before scoring. This calls the
same loader, feature extractor, and rule detector as the dashboard, while
avoiding the dashboard's in-memory analysis retention.

Add --explainer (mock, rcd, claude or openai) to also explain every merged
alert with the same evidence packets the dashboard builds:
    EXPLAINER=rcd .venv/bin/python -u -m scripts.evaluate_midterm --dataset road --explainer rcd

Explanations go to explanations_<explainer>.json, one record per alert with
the true type, prediction, grounding, latency, fallback and raw reply. The
explainer only receives the evidence packet; labels, capture names and
metadata never reach it. Without --out, explanation runs write under
out/explanations_<date> so the midterm detection artifacts stay untouched.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import features, loader, metrics
from app.detector import RuleDetector
from app.evidence import build_evidence
from app.llm import get_explainer

BACKEND = Path(__file__).resolve().parents[1]
THRESHOLD = 0.55
WINDOW_S = 0.5
STRIDE_S = 0.25
PREFIX_S = 120.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def timestamp(line: str) -> float:
    if line.startswith("Timestamp:"):
        return float(line.split()[1])
    if line.startswith("("):
        return float(line[1:line.index(")")])
    return float(line.split(",", 1)[0])


def capture(path: Path, out: Path, *, start: float = 0.0,
            stop: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Read a contiguous timestamp slice; preserve format and metadata.

    Timestamps are normalized by the existing loader. Every selected source
    line must produce a frame; a silently skipped malformed row aborts the run.
    """
    original = path
    if stop is not None:
        # Keep derivative raw traffic under the project's ignored data tree.
        target = (BACKEND / "data/evaluation_inputs" / out.parent.name / out.name /
                  f"{path.stem}_{start:g}_{stop:g}" / path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        first = None
        previous = None
        count = 0
        with original.open() as source, target.open("w") as dest:
            for line in source:
                if not line.strip():
                    continue
                ts = timestamp(line)
                if first is None:
                    first = ts
                if previous is not None and ts < previous:
                    raise ValueError(f"Nonmonotonic timestamps in selected prefix: {original}")
                previous = ts
                relative = ts - first
                if relative >= stop:
                    break
                if relative >= start:
                    dest.write(line)
                    count += 1
        meta = original.parent / "capture_metadata.json"
        if meta.exists():
            (target.parent / meta.name).write_text(meta.read_text())
        path = target
    else:
        with original.open() as stream:
            count = sum(bool(line.strip()) for line in stream)
    df = loader.load_auto(str(path))
    if len(df) != count:
        raise ValueError(f"{original}: selected {count} nonempty lines but loaded {len(df)} frames")
    record = {
        "source": str(original.relative_to(BACKEND)),
        "source_sha256": sha256(original),
        "selected_input": str(path.relative_to(BACKEND)),
        "selected_input_sha256": sha256(path),
        "source_relative_start_s": start,
        "source_relative_stop_s_exclusive": stop,
        "frame_count": len(df),
        "selected_nonempty_lines": count,
        "skipped_selected_lines": count - len(df),
        "duration_s": float(df.timestamp.max()),
        "unique_ids": int(df.can_id.nunique()),
        "attack_labeled_frames": int(df.label.sum()),
    }
    return df, record


def pooled(records: list[dict]) -> dict:
    counts = {key: sum(r["detection"][key] for r in records) for key in
              ("true_positive", "false_positive", "false_negative", "true_negative")}
    tp, fp, fn, tn = (counts[k] for k in
                       ("true_positive", "false_positive", "false_negative", "true_negative"))
    p = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {**counts, "windows_evaluated": tp + fp + fn + tn,
            "precision": p, "recall": recall, "f1": f1,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
            "captures": len(records), "frame_count": sum(r["input"]["frame_count"] for r in records)}


def git_state() -> dict:
    """Commit and dirty flag, so a result can be traced to the exact detector."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=BACKEND, capture_output=True,
                              text=True, check=False).stdout.strip()
    return {"commit": git("rev-parse", "HEAD") or None,
            "dirty": bool(git("status", "--porcelain", "--", "app", "scripts"))}


def true_type(df: pd.DataFrame, start: float, end: float) -> str:
    """Majority attack type of labeled frames in [start, end), as the dashboard scores it."""
    seg = df[(df["timestamp"] >= start) & (df["timestamp"] < end)]
    attack = seg[seg["label"] == 1]
    return "normal" if attack.empty else str(attack["attack_type"].mode().iat[0])


def explanation_summary(records: list[dict]) -> dict:
    """Classification, grounding, false-alarm handling, fallbacks and latency."""
    alerts = [{"true_type": r["true_type"], "explanation": r["explanation"]} for r in records]
    false_alarms = [r for r in records if r["true_type"] == "normal"]
    latencies = sorted(r["explanation"]["latency_s"] for r in records
                       if r["explanation"].get("latency_s") is not None)
    return {
        "alerts_explained": len(records),
        "classification": metrics.classification_accuracy(alerts),
        "grounding": metrics.grounding_rate(alerts),
        "false_alarms": len(false_alarms),
        "false_alarms_called_benign": sum(r["explanation"]["attack_type"] == "benign"
                                          for r in false_alarms),
        "fallbacks": sum(r["explanation"]["model"].startswith("mock (fallback") for r in records),
        "latency_s_median": latencies[len(latencies) // 2] if latencies else None,
        "latency_s_max": latencies[-1] if latencies else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["hcrl", "road"], required=True)
    parser.add_argument("--full-hcrl", action="store_true",
                        help="evaluate all rows of HCRL attack captures instead of 120 s prefixes")
    parser.add_argument("--out", type=Path, default=None,
                        help="output root (default out/midterm_2026-10-20, or "
                             "out/explanations_<date> with --explainer)")
    parser.add_argument("--explainer", choices=["mock", "rcd", "claude", "openai"],
                        help="also explain every merged alert with this backend")
    parser.add_argument("--max-alerts", type=int, default=0,
                        help="explain at most this many alerts per capture (0 = all)")
    args = parser.parse_args()
    if args.out is None:
        args.out = BACKEND / "out" / (
            f"explanations_{datetime.now().date()}" if args.explainer else "midterm_2026-10-20")
    explainer = get_explainer(args.explainer) if args.explainer else None
    explanations: list[dict] = []
    out = args.out.resolve() / (args.dataset + ("_full" if args.full_hcrl else ""))
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    excluded = []
    if args.dataset == "hcrl":
        raw = BACKEND / "data/raw/hcrl-car-hacking"
        baseline_path = raw / "normal_run_data/normal_run_data.txt"
        baseline_stop = PREFIX_S
        jobs = [(raw / f"{name}_dataset.csv", 0.0, None if args.full_hcrl else PREFIX_S, "attack_capture")
                for name in ["DoS", "Fuzzy", "RPM", "gear"]]
        jobs.append((baseline_path, 121.0, 241.0, "held_out_normal"))
        scope = (("Complete contents" if args.full_hcrl else "First 120 seconds") +
                 " of each of the four attack captures; normal baseline "
                 "uses [0,120) seconds of the separate normal capture, with [121,241) "
                 "seconds reserved for normal evaluation. No frame overlap. The normal "
                 "holdout is from the same recording and is not an independent drive.")
    else:
        raw = BACKEND / "data/raw/road/road"
        baseline_path = raw / "ambient/ambient_dyno_drive_basic_short.log"
        baseline_stop = None
        meta = json.loads((raw / "attacks/capture_metadata.json").read_text())
        jobs = [(raw / f"attacks/{name}.log", 0.0, None, "attack_capture")
                for name, entry in sorted(meta.items()) if entry.get("injection_interval")]
        excluded = [{"capture": name, "reason": "No injection interval in supplied metadata; cannot assign reliable window ground truth"}
                    for name, entry in sorted(meta.items()) if not entry.get("injection_interval")]
        jobs += [(raw / f"ambient/{name}.log", 0.0, PREFIX_S, "held_out_normal") for name in
                 ["ambient_dyno_drive_basic_long", "ambient_dyno_drive_extended_short"]]
        scope = ("All 29 attack captures with supplied injection intervals (13 fabrication, "
                 "13 derived masquerade, 3 fuzzing). Full basic_short ambient capture is "
                 "baseline-only. First 120 seconds each of basic_long and extended_short "
                 "ambient captures are held out for normal evaluation. The paired "
                 "fabrication/masquerade captures share underlying recordings.")

    report = {
        "dataset": args.dataset,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "methodology": {
            "stage": "preliminary fixed-threshold benchmark",
            "scope": scope,
            "detector": "rule", "threshold": THRESHOLD,
            "threshold_selection": "Existing application default, fixed before this run; no tuning on evaluated captures",
            "prior_development": "The repository documents previous rule development using Car-Hacking. These are preliminary development results, not a pristine held-out benchmark.",
            "window_s": WINDOW_S, "stride_s": STRIDE_S,
            "positive_window": "At least one frame labeled attack by the existing loader",
            "road_labels": "Metadata injection interval and injected CAN ID; fuzzing labels every frame in the interval. This is interval/ID-derived window ground truth, not exact injected-frame annotation.",
            "llm_calls": 0,
            "explanation_evaluation": ("Not evaluated in this detection benchmark" if explainer is None
                                       else f"See explanations_{explainer.name}.json"),
            "interface": "Command-line evaluation; browser upload does not yet supply separate baseline captures and ROAD metadata",
            "empty_windows": "Excluded by the existing feature extractor",
            "window_tail": "Existing extractor may include one partially observed final 0.5 s window; no records beyond the selected interval are added",
            "aggregation": "Pool window confusion counts across selected evaluation captures; overlapping windows and related captures are not independent samples",
            "capture_dependence": "HCRL attack files share source rows; ROAD fabrication/masquerade pairs share underlying recordings. Do not treat pooled windows as independent samples.",
        },
        "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                        "git": git_state()},
        "code_sha256": {name: sha256(BACKEND / name) for name in
                         ["app/loader.py", "app/features.py", "app/detector.py", "app/metrics.py",
                          "app/evidence.py", "app/llm.py", "scripts/evaluate_midterm.py"]},
        "excluded_attack_captures": excluded,
        "captures": [],
    }
    print(f"{args.dataset}: baseline {baseline_path.name}", flush=True)
    baseline_df, baseline_input = capture(baseline_path, out, stop=baseline_stop)
    assert baseline_df.label.sum() == 0, "Baseline contains labeled attacks"
    baseline = features.learn_baseline(baseline_df, float("inf"), window_s=WINDOW_S)
    report["baseline"] = {"input": baseline_input, "learned": baseline.to_json()}
    del baseline_df
    gc.collect()
    detector = RuleDetector(baseline, threshold=THRESHOLD)
    print(f"baseline learned: {len(baseline.known_ids)} IDs, {baseline.total_rate:.1f} frames/s", flush=True)
    for path, start, stop, role in jobs:
        timer = time.perf_counter()
        print(f"scoring {path.name} [{start:g}, {stop})", flush=True)
        df, input_record = capture(path, out, start=start, stop=stop)
        windows = features.extract_windows(df, baseline, window_s=WINDOW_S, stride_s=STRIDE_S)
        windows, alerts = detector.run(windows)
        detection = metrics.detection_metrics(windows)
        score_path = out / f"{path.stem}__{role}_windows.csv.gz"
        compact = windows[["start", "end", "label", "attack_type", "score", "flagged"]].copy()
        for component in ["bus_load", "unknown_ids", "rate_inflation", "missing_ids", "timing", "payload_entropy"]:
            compact[component] = [c[component] for c in windows["components"]]
        compact.to_csv(score_path, index=False)
        record = {
            "capture": path.stem, "role": role, "input": input_record,
            "detection": detection, "merged_alert_count": len(alerts),
            "score_file": str(score_path.relative_to(BACKEND)),
            "processing_seconds": round(time.perf_counter() - timer, 3),
            "attack_type": next((t for t in df.attack_type.unique() if t not in {"normal", "unknown"}), None),
            "empty_windows_excluded": int(len(np.arange(0.0, max(WINDOW_S,
                input_record["duration_s"] - WINDOW_S + STRIDE_S), STRIDE_S)) - len(windows)),
            "partial_tail_windows": int((windows["end"] > input_record["duration_s"]).sum()),
        }
        if explainer is not None:
            chosen = alerts[:args.max_alerts] if args.max_alerts else alerts
            for alert in chosen:
                evidence = build_evidence(alert, df, windows, baseline)
                exp = explainer.explain(evidence)
                explanations.append({
                    "capture": path.stem, "role": role, "alert_id": alert.alert_id,
                    "start": alert.start, "end": alert.end, "detector_score": alert.score,
                    "true_type": true_type(df, alert.start, alert.end),
                    "explanation": exp.to_json(),
                })
            record["alerts_explained"] = len(chosen)
            if explainer.name != "mock":
                report["methodology"]["llm_calls"] += len(chosen)
            write_explanations(out, explainer, explanations, report)
        report["captures"].append(record)
        report["pooled"] = pooled(report["captures"])
        (out / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(f"  {len(df):,} frames / {len(windows):,} windows / {record['processing_seconds']:.1f}s: "
              f"P={detection['precision']:.4f} R={detection['recall']:.4f} "
              f"F1={detection['f1']:.4f} FPR={detection['false_positive_rate']:.4f}", flush=True)
        del df, windows, compact, alerts
        gc.collect()
    report["pooled_attack_captures"] = pooled([r for r in report["captures"] if r["role"] == "attack_capture"])
    report["pooled_held_out_normal"] = pooled([r for r in report["captures"] if r["role"] == "held_out_normal"])
    report["by_attack_type"] = {t: pooled([r for r in report["captures"] if r["attack_type"] == t])
                                for t in sorted({r["attack_type"] for r in report["captures"] if r["attack_type"]})}
    report["status"] = "complete"
    report["total_processing_seconds"] = round(time.perf_counter() - started, 3)
    (out / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("POOLED " + json.dumps(report["pooled"]), flush=True)
    if explainer is not None:
        summary = write_explanations(out, explainer, explanations, report, complete=True)
        print("EXPLANATIONS " + json.dumps(summary), flush=True)


def write_explanations(out: Path, explainer, records: list[dict], report: dict,
                       complete: bool = False) -> dict:
    """Rewritten after every capture so an interrupted run keeps what it paid for."""
    summary = explanation_summary(records)
    payload = {
        "dataset": report["dataset"],
        "status": "complete" if complete else "running",
        "explainer": explainer.name,
        "model": getattr(explainer, "model", "mock"),
        "temperature": getattr(explainer, "temperature", None),
        "detector": "rule", "threshold": THRESHOLD,
        "inputs": "Evidence packets only: measured deviations, per-ID statistics and at most "
                  "six sample frames. No labels, capture names or metadata.",
        "scoring": "true_type is the majority attack type of labeled frames inside the alert; "
                   "alerts on unlabeled frames are false alarms and are excluded from accuracy.",
        "code_sha256": report["code_sha256"],
        "git": report["environment"]["git"],
        "summary": summary,
        "alerts": records,
    }
    (out / f"explanations_{explainer.name}.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n")
    return summary


if __name__ == "__main__":
    main()
