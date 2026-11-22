"""Saved benchmark results for the dashboard's read-only Benchmark tab.

Reads the explanations_<name>.json files that scripts/evaluate_midterm.py
writes, preferring the _rescored copy when scripts/rescore_grounding.py has
made one, and lines up every explainer's answer for the same alert. Nothing
here calls a model or reruns the detector.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"
DATASETS = {"hcrl": "Car-Hacking", "hcrl_full": "Car-Hacking (full captures)", "road": "ROAD"}
KEEP = ("attack_type", "confidence", "severity", "affected_function", "summary", "claims",
        "recommended_action", "model", "grounded", "latency_s", "raw_response", "fallback", "requested_model", "error_type", "usage", "cost_usd",
        "validation_version", "validation_warnings")


def load_detection(root: Path = OUT) -> dict:
    """Completed detection experiments, including negative results, without raw frames."""
    runs, errors = [], []
    for path in sorted(root.glob("detectors_*/*/results.json")):
        try:
            payload = json.loads(path.read_text())
            if payload.get("status") != "complete":
                continue
            pooled = payload["pooled"]
            by_detector = {payload["detector"]: pooled} if "all" in pooled else pooled
            for detector, scopes in by_detector.items():
                runs.append({"id": f"{path.relative_to(root)}:{detector}",
                             "dataset": payload["dataset"],
                             "profile": payload["baseline_profile"] +
                                 (" / full captures" if payload.get("full_hcrl") else "") +
                                 (f" / {payload['forest_split']}" if payload.get("forest_split") else ""),
                             "detector": detector, "scope": "all", "metrics": scopes["all"],
                             "normal_metrics": scopes.get("held_out_normal"),
                             "source": str(path.relative_to(root.parent)),
                             "methodology": payload.get("methodology", {}),
                             "created_utc": payload.get("created_utc")})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"source": str(path.relative_to(root.parent)), "error": str(exc)})
    return {"runs": runs, "errors": errors}


def _run(payload: dict, run_id: str, source: Path, root: Path) -> dict:
    rescore = payload.get("rescore")
    summary = dict(payload["summary"])
    grounding = dict(summary.get("grounding", {}))
    if "rate" in grounding:
        grounding["grounded_rate"] = grounding["rate"]
    summary["grounding"] = grounding
    if "false_alarms_labeled_benign" in summary:
        summary["false_alarms_called_benign"] = summary["false_alarms_labeled_benign"]
    return {
        "id": run_id,
        "explainer": payload["explainer"],
        "label": "Offline control" if payload["explainer"] == "mock" else payload.get("model"),
        "model": payload.get("model"),
        "temperature": payload.get("temperature"),
        "git": {"commit": payload["git"]} if isinstance(payload.get("git"), str) else payload.get("git"),
        "summary": summary,
        "status": payload["status"],
        "limited_run": payload.get("manifest", {}).get("limit"),
        "summary_as_run": rescore["summary_before"] if rescore else summary,
        "rescore_method": rescore["method"] if rescore else None,
        "source": str(source.relative_to(root.parent)),
        "corpus_sha256": payload.get("corpus_sha256"),
        "protocol": payload.get("protocol") or payload.get("scoring"),
        "prompt_version": payload.get("prompt_version"),
        "request_key": payload.get("manifest", {}).get("request_key"),
    }


def load(root: Path = OUT) -> dict:
    datasets: dict[str, dict] = {}
    errors = []
    annotations = {}
    for annotation_path in sorted(root.glob("validation_*/*.json")):
        try:
            annotation = json.loads(annotation_path.read_text())
            if annotation.get("status") != "complete" or not annotation.get("source_run_sha256"):
                continue
            for row in annotation["alerts"]:
                key = (annotation["source_run_sha256"], annotation["corpus_sha256"],
                       row["corpus_index"], row["evidence_sha256"])
                annotations[key] = {"validation_version": row["validation_version"],
                                    "validation_warnings": row["validation_warnings"],
                                    "validation_source": str(annotation_path.relative_to(root.parent))}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"source": str(annotation_path.relative_to(root.parent)), "error": str(exc)})
    for path in sorted(root.glob("explanations_*/*/explanations_*.json")):
        if path.stem.endswith("_rescored"):
            continue
        rescored = path.with_name(f"{path.stem}_rescored.json")
        source = rescored if rescored.exists() else path
        try:
            source_bytes = source.read_bytes()
            payload = json.loads(source_bytes)
        except (OSError, ValueError) as exc:
            errors.append({"source": str(source.relative_to(root.parent)), "error": str(exc)})
            continue
        if payload.get("status") not in {"complete", "complete_with_failures"}:
            continue  # a run still in progress has partial counts
        dataset = payload.get("dataset", path.parent.name)
        # A repeated alert number is not evidence that two runs saw the same input.
        # New runs carry the frozen corpus digest. Legacy runs are conservatively
        # grouped by detector/evidence implementation and exact alert boundaries.
        corpus = payload.get("corpus_sha256")
        if corpus:
            key = f"{dataset}:{corpus[:12]}"
            if payload.get("manifest", {}).get("limit") is not None:
                key += f":limit{payload['manifest']['limit']}"
            label = f"{DATASETS.get(dataset, dataset)} · corrected evidence {corpus[:8]}"
            if payload.get("manifest", {}).get("limit") is not None:
                label += " · smoke test only"
        else:
            code = payload.get("code_sha256", {})
            signature = {"code": {k: code.get(k) for k in
                ("app/detector.py", "app/features.py", "app/evidence.py", "app/loader.py")},
                "alerts": [(r["capture"], r["alert_id"], r["start"], r["end"], r["true_type"])
                           for r in payload["alerts"]]}
            fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
            key = dataset if dataset not in datasets or datasets[dataset].get("fingerprint") == fingerprint else f"{dataset}:{fingerprint[:12]}"
            label = DATASETS.get(dataset, dataset) + " · historical"
        ds = datasets.setdefault(key, {"key": key, "dataset": dataset,
                                       "fingerprint": corpus or fingerprint, "label": label,
                                       "runs": [], "alerts": {}})
        run_id = str(path.relative_to(root))
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        ds["runs"].append(_run(payload, run_id, source, root))
        for record in payload["alerts"]:
            row = ds["alerts"].setdefault((record["capture"], record["alert_id"]), {
                k: record[k] for k in
                ("capture", "role", "alert_id", "start", "end", "detector_score", "true_type")})
            exp = record["explanation"]
            row.setdefault("results", {})[run_id] = {
                **{k: exp.get(k) for k in KEEP},
                **annotations.get((source_sha256, corpus, record.get("corpus_index"),
                                   record.get("evidence_sha256")), {}),
                "grounded_as_run": record.get("grounded_before_rescore", exp.get("grounded")),
            }
    for ds in datasets.values():
        ds["runs"].sort(key=lambda r: (r["explainer"] != "mock", r["id"]))
        ds["alerts"] = sorted(ds["alerts"].values(), key=lambda a: (a["capture"], a["alert_id"]))
    order = list(DATASETS)
    return {"datasets": sorted(datasets.values(),
                               key=lambda d: (order.index(d["dataset"]) if d["dataset"] in order else 99, d["key"])),
            "errors": errors}
