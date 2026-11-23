"""Freeze a set of alerts and their evidence packets for explainer runs.

Every explainer in a comparison must see the same alerts, so the detector
is run once and its alerts are written to disk. Explainers then read the
frozen packets; nothing about the detector can differ between them.

Run from the backend folder:
    python -m scripts.freeze_alerts --set midterm100

Sets
    midterm100   The 100 alerts of the October 21 run, rebuilt from the raw
                 captures: the first 120 s of each Car-Hacking attack capture
                 and its normal holdout (69 alerts), and the 29 labeled ROAD
                 attack captures plus two 120 s normal excerpts (31 alerts).
                 Same slices, baseline, rule detector and threshold as
                 scripts/evaluate_midterm.py.
    heldout      Alerts no explainer, prompt or control rule was developed on.
                 Car-Hacking: 120 s from the evaluation part of each attack
                 capture, starting at its median non-empty window (the split
                 point of app/datasets.py), plus 120 s of the attack-free
                 capture's evaluation part. ROAD: attack-free excerpts of the
                 evaluation ambient captures, which supply false alarms. No
                 ROAD attack capture is in this set: all of them were in
                 midterm100, so none is held out for an explainer.
    ctt          Four more vehicles, added after every prompt and rule was
                 fixed: can-train-and-test (see app/datasets.py). Each
                 vehicle's baseline comes from its own attack-free capture;
                 its DoS, fuzzing and spoofing evaluation captures are
                 scored in full, plus 240 s of a second attack-free capture
                 for false alarms.

Output, under out/alerts/<set>/
    alerts.jsonl           one row per alert: opaque id, capture, span, ground truth
    packets_window.jsonl   evidence as built through October 21 (per-ID numbers
                           from one window of the alert)
    packets_alert.jsonl    evidence measured over the whole alert
    manifest.json          inputs, hashes, counts

Packets carry only the opaque id and the evidence. Capture names and
labels live in alerts.jsonl and are never part of a prompt.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, datasets, features  # noqa: E402
from app.detector import RuleDetector  # noqa: E402
from app.evidence import build_evidence  # noqa: E402
from scripts.evaluate_midterm import (PREFIX_S, STRIDE_S, THRESHOLD, WINDOW_S,  # noqa: E402
                                      capture)

BACKEND = Path(__file__).resolve().parents[1]
HELDOUT_S = 120.0
# Explainer runs cost time per alert. On the four extra vehicles most alerts
# are false alarms (92 from one Silverado capture), so every attack alert is
# kept and at most this many false alarms per capture, drawn with a fixed seed.
FALSE_ALARM_CAP = {"ctt": 3}
CAP_SEED = 0


def _median_window_start(dataset: str, name: str) -> float:
    """Start of a capture's median non-empty window: the tuning/evaluation split point."""
    path = BACKEND / "out" / "cache" / dataset / f"{name}.npz"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run python -m scripts.build_cache first")
    starts = cache.load(path).win["start"].to_numpy()
    return float(starts[len(starts) // 2])


def _jobs(set_name: str) -> list[dict]:
    """One entry per dataset: baseline slice and the captures to score."""
    hcrl = {c.name: c for c in datasets.catalog("hcrl")}
    road = {c.name: c for c in datasets.catalog("road")}
    normal = hcrl["normal_run_data"].path
    road_ref = road[datasets.ROAD_REFERENCE].path
    attacks = [c for c in road.values() if c.kind == "attack" and c.role != "excluded"]
    if set_name == "midterm100":
        return [
            {"dataset": "hcrl", "baseline": (normal, 0.0, PREFIX_S),
             "captures": [(hcrl[f"{n}_dataset"].path, 0.0, PREFIX_S)
                          for n in ["DoS", "Fuzzy", "RPM", "gear"]]
             + [(normal, 121.0, 241.0)]},
            {"dataset": "road", "baseline": (road_ref, 0.0, None),
             "captures": [(c.path, 0.0, None) for c in sorted(attacks, key=lambda c: c.name)]
             + [(road[n].path, 0.0, PREFIX_S) for n in
                ["ambient_dyno_drive_basic_long", "ambient_dyno_drive_extended_short"]]},
        ]
    if set_name == "heldout":
        hcrl_slices = []
        for n in ["DoS", "Fuzzy", "RPM", "gear"]:
            start = float(math.ceil(_median_window_start("hcrl", f"{n}_dataset")))
            hcrl_slices.append((hcrl[f"{n}_dataset"].path, start, start + HELDOUT_S))
        normal_start = datasets.HCRL_NORMAL_EVAL_START_S
        hcrl_slices.append((normal, normal_start, normal_start + HELDOUT_S))
        # extended_short [0, 120) was part of midterm100, so its next 120 s are used.
        road_slices = [(road[n].path, lo, hi) for n, lo, hi in [
            ("ambient_dyno_drive_benign_anomaly", 0.0, HELDOUT_S),
            ("ambient_dyno_drive_extended_short", HELDOUT_S, 2 * HELDOUT_S),
            ("ambient_dyno_drive_winter", 0.0, HELDOUT_S),
            ("ambient_dyno_idle_radio_infotainment", 0.0, HELDOUT_S),
            ("ambient_highway_street_driving_diagnostics", 0.0, HELDOUT_S),
        ]]
        assert all(road[p.stem].role == "evaluation" for p, _, _ in road_slices)
        return [
            {"dataset": "hcrl", "baseline": (normal, 0.0, PREFIX_S), "captures": hcrl_slices},
            {"dataset": "road", "baseline": (road_ref, 0.0, None), "captures": road_slices},
        ]
    if set_name == "ctt":
        caps = datasets.catalog("ctt")
        jobs = []
        for vehicle in datasets.CTT_VEHICLES:
            mine = [c for c in caps if c.meta["vehicle"] == vehicle]
            ref = next(c for c in mine if c.role == "reference")
            ambient = next(c for c in mine if c.kind == "ambient" and c.role == "evaluation")
            attacks = sorted((c for c in mine if c.kind == "attack"), key=lambda c: c.name)
            jobs.append({"dataset": "ctt", "baseline": (ref.path, 0.0, None),
                         "captures": [(c.path, 0.0, None) for c in attacks]
                         + [(ambient.path, 0.0, 2 * HELDOUT_S)]})
        return jobs
    raise ValueError(f"unknown set: {set_name}")


def cap_false_alarms(out: Path, per_capture: int, seed: int = CAP_SEED) -> dict:
    """Keep every attack alert and at most `per_capture` false alarms per capture.
    The full set stays in alerts_all.jsonl; ids are not renumbered."""
    import random
    full = out / "alerts_all.jsonl"
    if not full.exists():
        (out / "alerts.jsonl").rename(full)
    rows = [json.loads(line) for line in full.read_text().splitlines() if line.strip()]
    rng = random.Random(seed)
    keep = {r["id"] for r in rows if r["is_attack"]}
    by_capture: dict[str, list[str]] = {}
    for r in rows:
        if not r["is_attack"]:
            by_capture.setdefault(r["capture"], []).append(r["id"])
    for capture_name in sorted(by_capture):
        ids = by_capture[capture_name]
        keep.update(rng.sample(ids, min(per_capture, len(ids))))
    (out / "alerts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows if r["id"] in keep))
    for scope in ("window", "alert"):
        path = out / f"packets_{scope}.jsonl"
        full_p = out / f"packets_{scope}_all.jsonl"
        if not full_p.exists():
            path.rename(full_p)
        lines = [line for line in full_p.read_text().splitlines() if line.strip()]
        path.write_text("".join(line + "\n" for line in lines if json.loads(line)["id"] in keep))
    return {"false_alarm_cap_per_capture": per_capture, "seed": seed,
            "alerts_before_cap": len(rows), "alerts_after_cap": len(keep)}


def _true_type(df: pd.DataFrame, start: float, end: float) -> str:
    seg = df[(df["timestamp"] >= start) & (df["timestamp"] < end)]
    atk = seg[seg["label"] == 1]
    return "normal" if atk.empty else str(atk["attack_type"].mode().iat[0])


def _json(obj):
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"not serializable: {type(obj)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_name", default="midterm100",
                    choices=["midterm100", "heldout", "ctt"])
    ap.add_argument("--out", type=Path, default=BACKEND / "out" / "alerts")
    ap.add_argument("--cap-only", action="store_true",
                    help="only apply the false-alarm cap to an existing frozen set")
    args = ap.parse_args()
    out = (args.out / args.set_name).resolve()
    if args.cap_only:
        _apply_cap(out, args.set_name)
        return
    out.mkdir(parents=True, exist_ok=True)

    alerts_rows: list[dict] = []
    packets = {"window": [], "alert": []}
    manifest = {
        "set": args.set_name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "detector": "rule", "threshold": THRESHOLD,
        "window_s": WINDOW_S, "stride_s": STRIDE_S,
        "code_sha256": {name: cache.sha256(BACKEND / name) for name in
                         ["app/loader.py", "app/features.py", "app/detector.py",
                          "app/evidence.py", "scripts/freeze_alerts.py"]},
        "inputs": [],
    }
    for job in _jobs(args.set_name):
        path, start, stop = job["baseline"]
        base_df, base_rec = capture(path, out, start=start, stop=stop)
        assert base_df.label.sum() == 0, "baseline contains labeled attacks"
        baseline = features.learn_baseline(base_df, float("inf"), window_s=WINDOW_S)
        manifest["inputs"].append({"role": "baseline", "dataset": job["dataset"], **base_rec})
        del base_df
        detector = RuleDetector(baseline, threshold=THRESHOLD)
        for path, start, stop in job["captures"]:
            df, rec = capture(path, out, start=start, stop=stop)
            windows = features.extract_windows(df, baseline, window_s=WINDOW_S,
                                               stride_s=STRIDE_S)
            windows, alerts = detector.run(windows)
            manifest["inputs"].append({"role": "scored", "dataset": job["dataset"],
                                       "alerts": len(alerts), **rec})
            for alert in alerts:
                uid = f"A{len(alerts_rows):04d}"
                true_type = _true_type(df, alert.start, alert.end)
                alerts_rows.append({
                    "id": uid, "dataset": job["dataset"],
                    "capture": (datasets.ctt_capture_name(path) if job["dataset"] == "ctt"
                                else path.stem),
                    "slice_start_s": start, "slice_stop_s": stop,
                    "alert_id": alert.alert_id, "start": alert.start, "end": alert.end,
                    "duration_s": round(alert.end - alert.start, 3),
                    "score": alert.score, "components": alert.components,
                    "true_type": true_type, "is_attack": true_type != "normal",
                })
                for scope in packets:
                    ev = build_evidence(alert, df, windows, baseline, scope=scope)
                    packets[scope].append({"id": uid, "evidence": ev})
            print(f"{job['dataset']}/{path.parent.parent.name}/{path.stem}: {len(alerts)} alert(s)",
                  flush=True)
            del df, windows
            gc.collect()

    (out / "alerts.jsonl").write_text(
        "".join(json.dumps(r, default=_json) + "\n" for r in alerts_rows))
    for scope, rows in packets.items():
        (out / f"packets_{scope}.jsonl").write_text(
            "".join(json.dumps(r, default=_json) + "\n" for r in rows))
    by_ds: dict[str, dict] = {}
    for r in alerts_rows:
        d = by_ds.setdefault(r["dataset"], {"alerts": 0, "attack": 0, "false_alarm": 0})
        d["alerts"] += 1
        d["attack" if r["is_attack"] else "false_alarm"] += 1
    manifest["counts"] = {"alerts": len(alerts_rows), "by_dataset": by_ds}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=_json) + "\n")
    print(json.dumps(manifest["counts"]))
    _apply_cap(out, args.set_name)


def _apply_cap(out: Path, set_name: str) -> None:
    if set_name not in FALSE_ALARM_CAP:
        return
    info = cap_false_alarms(out, FALSE_ALARM_CAP[set_name])
    manifest = json.loads((out / "manifest.json").read_text())
    rows = [json.loads(line) for line in (out / "alerts.jsonl").read_text().splitlines() if line]
    manifest["cap"] = info
    manifest["counts_after_cap"] = {
        "alerts": len(rows), "attack": sum(r["is_attack"] for r in rows),
        "false_alarm": sum(not r["is_attack"] for r in rows)}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["counts_after_cap"]))


if __name__ == "__main__":
    main()
