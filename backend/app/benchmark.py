"""Saved benchmark results for the dashboard's read-only Benchmark tab.

Reads the explanations_<name>.json files that scripts/evaluate_midterm.py
writes, preferring the _rescored copy when scripts/rescore_grounding.py has
made one, and lines up every explainer's answer for the same alert. Nothing
here calls a model or reruns the detector.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"
DATASETS = {"hcrl": "Car-Hacking", "hcrl_full": "Car-Hacking (full captures)", "road": "ROAD"}
KEEP = ("attack_type", "confidence", "severity", "affected_function", "summary", "claims",
        "recommended_action", "model", "grounded", "latency_s", "raw_response")


def _run(payload: dict, run_id: str, source: Path, root: Path) -> dict:
    rescore = payload.get("rescore")
    return {
        "id": run_id,
        "explainer": payload["explainer"],
        "label": "Offline control" if payload["explainer"] == "mock" else payload.get("model"),
        "model": payload.get("model"),
        "temperature": payload.get("temperature"),
        "git": payload.get("git"),
        "summary": payload["summary"],
        "summary_as_run": rescore["summary_before"] if rescore else payload["summary"],
        "rescore_method": rescore["method"] if rescore else None,
        "source": str(source.relative_to(root.parent)),
    }


def load(root: Path = OUT) -> dict:
    datasets: dict[str, dict] = {}
    for path in sorted(root.glob("explanations_*/*/explanations_*.json")):
        if path.stem.endswith("_rescored"):
            continue
        rescored = path.with_name(f"{path.stem}_rescored.json")
        source = rescored if rescored.exists() else path
        payload = json.loads(source.read_text())
        if payload.get("status") != "complete":
            continue  # a run still in progress has partial counts
        key = path.parent.name
        ds = datasets.setdefault(key, {"key": key, "label": DATASETS.get(key, key),
                                       "runs": [], "alerts": {}})
        run_id = f"{path.parent.parent.name}/{payload['explainer']}"
        ds["runs"].append(_run(payload, run_id, source, root))
        for record in payload["alerts"]:
            row = ds["alerts"].setdefault((record["capture"], record["alert_id"]), {
                k: record[k] for k in
                ("capture", "role", "alert_id", "start", "end", "detector_score", "true_type")})
            exp = record["explanation"]
            row.setdefault("results", {})[run_id] = {
                **{k: exp.get(k) for k in KEEP},
                "grounded_as_run": record.get("grounded_before_rescore", exp.get("grounded")),
            }
    for ds in datasets.values():
        ds["runs"].sort(key=lambda r: (r["explainer"] != "mock", r["id"]))
        ds["alerts"] = sorted(ds["alerts"].values(), key=lambda a: (a["capture"], a["alert_id"]))
    order = list(DATASETS)
    return {"datasets": sorted(datasets.values(),
                               key=lambda d: order.index(d["key"]) if d["key"] in order else 99)}
