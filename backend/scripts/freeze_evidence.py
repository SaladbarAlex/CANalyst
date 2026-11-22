"""Rebuild corrected evidence on the original midterm alert boundaries.

No detector rerun or model calls. Original window scores/components are retained;
only measured features and evidence are rebuilt. Outputs are diagnostic development
corpora, not untouched test data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from app import features, loader
from app.detector import Alert
from app.evidence import build_evidence
from scripts.evaluate_midterm import BACKEND, sha256


def freeze(dataset: str, source: Path, destination: Path) -> None:
    folder = source / dataset
    report = json.loads((folder / "results.json").read_text())
    original = json.loads((folder / "explanations_mock.json").read_text())
    base_path = BACKEND / report["baseline"]["input"]["selected_input"]
    baseline = features.learn_baseline(loader.load_auto(str(base_path)), float("inf"))
    records, inputs = [], {str(base_path.relative_to(BACKEND)): sha256(base_path)}
    for capture in report["captures"]:
        selected = [r for r in original["alerts"] if r["capture"] == capture["capture"]]
        if not selected:
            continue
        path = BACKEND / capture["input"]["selected_input"]
        inputs[str(path.relative_to(BACKEND))] = sha256(path)
        df = loader.load_auto(str(path))
        windows = features.extract_windows(df, baseline, window_s=0.5, stride_s=0.25)
        historical = pd.read_csv(BACKEND / capture["score_file"])
        component_names = ["bus_load", "unknown_ids", "rate_inflation", "missing_ids", "timing", "payload_entropy"]
        for old in selected:
            span = historical[(historical.start >= old["start"] - 1e-9) &
                              (historical.end <= old["end"] + 1e-9)]
            rows = windows[(windows.start >= old["start"] - 1e-9) &
                           (windows.end <= old["end"] + 1e-9)]
            if span.empty or rows.empty:
                raise ValueError(f"No measured windows for {capture['capture']} alert {old['alert_id']}")
            alert = Alert(old["alert_id"], int(rows.iloc[0]["window"]), old["start"], old["end"],
                          old["detector_score"], {k: float(span[k].max()) for k in component_names}, [], [])
            evidence = build_evidence(alert, df, windows, baseline)
            encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
            records.append({**{k: v for k, v in old.items() if k != "explanation"},
                            "evidence": evidence, "evidence_sha256": hashlib.sha256(encoded.encode()).hexdigest()})
        print(f"{dataset}: {capture['capture']}: {len(selected)} frozen alerts", flush=True)
    result = {"dataset": dataset, "status": "complete", "protocol": "original midterm alert boundaries; corrected evidence; development diagnostic",
              "source": str(folder.relative_to(BACKEND)), "source_sha256": sha256(folder / "explanations_mock.json"),
              "input_sha256": inputs, "code_sha256": {n: sha256(BACKEND / n) for n in
              ("app/features.py", "app/evidence.py", "app/loader.py", "scripts/freeze_evidence.py")}, "alerts": records}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=["hcrl", "road"], required=True)
    ap.add_argument("--source", type=Path, default=BACKEND / "out/explanations_2026-10-21")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    freeze(args.dataset, args.source, args.out)
