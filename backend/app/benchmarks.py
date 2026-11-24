"""Saved benchmark results for the Evaluation tab, and prediction submissions.

The dashboard reads saved replies and scores without running an experiment.

    detection()            out/benchmark/results.json (scripts/benchmark.py)
    explainers()           out/explanations/<set>/scores.json and each run.json
                           (scripts/run_explanations.py, score_explanations.py)
    compare(set, a, b)     alerts two runs disagree on, with both replies and
                           the evidence they were given
    packets(set)           the frozen inputs, without labels, so anyone can run
                           their own model offline
    submit(set, name, ...) score an uploaded predictions file like any other run

Submissions are predictions, never code. A file is one JSON object per line:
    {"id": "A0000", "attack_type": "dos",
     "claims": [{"text": "...", "cites": ["E2"]}], "latency_s": 12.5}
Only `id` and `attack_type` are required. An alert left out of the file is
scored as a wrong answer ("no answer"). Labels stay on the server; a
submission is checked against the frozen alert ids and the label vocabulary,
then scored with the same code as every built-in run.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .llm import ATTACK_LABELS, _check_citations, Explanation

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "out"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
MAX_SUBMISSION_BYTES = 5_000_000


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def sets() -> list[str]:
    root = OUT / "alerts"
    return sorted(p.name for p in root.iterdir()
                  if (p / "alerts.jsonl").exists()) if root.exists() else []


def _set_dir(set_name: str) -> Path:
    if set_name not in sets():
        raise KeyError(f"unknown alert set: {set_name}")
    return OUT / "alerts" / set_name


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def detection() -> dict | None:
    path = OUT / "benchmark" / "results.json"
    if not path.exists():
        return None
    # Undefined metrics in historical reports use NaN. JSON responses use null.
    data = json.loads(path.read_text(), parse_constant=lambda value: None)
    keep = ("threshold", "windows", "tp", "fp", "fn", "tn", "precision", "recall", "f1",
            "fpr", "auroc", "auprc", "recall_by_type", "fpr_by_source")
    out = {"created_utc": data["created_utc"], "bootstrap": data["bootstrap"],
           "target_fpr": data["target_fpr"], "datasets": []}
    for ds in data["datasets"]:
        refs = {}
        for name, ref in ds["references"].items():
            refs[name] = {
                "reference_captures": ref["reference_captures"],
                "reference_seconds": ref["reference_seconds"],
                "detectors": {k: {f: v[f] for f in keep if f in v}
                              for k, v in ref["evaluation"].items()},
            }
        out["datasets"].append({"dataset": ds["dataset"], "split": ds["split"],
                                "references": refs,
                                "coverage": [{k: row[k] for k in
                                              ("added", "reference_captures", "reference_seconds",
                                               "fpr_ambient", "recall")}
                                             for row in ds.get("coverage", [])]})
    return out


# --------------------------------------------------------------------------
# Explainers
# --------------------------------------------------------------------------

def _run_meta(set_name: str, run: str) -> dict:
    path = OUT / "explanations" / set_name / run / "run.json"
    return json.loads(path.read_text()) if path.exists() else {}


def explainers() -> dict:
    from scripts import score_explanations as se

    out = {}
    for set_name in sets():
        path = OUT / "explanations" / set_name / "scores.json"
        if not path.exists():
            continue
        sc = json.loads(path.read_text(), parse_constant=lambda _: None)
        alerts = {a["id"]: a for a in _read_jsonl(_set_dir(set_name) / "alerts.jsonl")}
        updated = {}
        runs = {}
        for run, r in sc["runs"].items():
            meta = _run_meta(set_name, run)
            targets = se.declared_targets(set_name, run, meta, alerts)
            replies_path = path.parent / run / "replies.jsonl"
            if targets is not None and replies_path.is_file():
                replies = {row["id"]: row for row in _read_jsonl(replies_path)}
                r = se.score_run(alerts, list(se.target_replies(replies, targets).values()))
                updated[run] = r
            runs[run] = {
                **{k: r.get(k) for k in ("alerts", "attack_alerts", "false_alarms", "accuracy",
                                         "accuracy_by_type", "confusion", "false_alarm_labels",
                                         "false_alarms_called_benign", "claims",
                                         "claims_with_valid_citations", "latency_s",
                                         "completion_tokens", "no_answer")},
                "model": meta.get("model"), "explainer": meta.get("explainer"),
                "prompt_version": meta.get("prompt_version"), "scope": meta.get("scope"),
                "control_rules": meta.get("control_rules"),
                "submitted": meta.get("explainer") == "submission",
            }
        pairs = sc.get("pairs", {})
        if updated:
            rescored = updated.copy()
            for pair in pairs:
                a, _, b = pair.partition(" vs ")
                if a not in updated and b not in updated:
                    continue
                for run in (a, b):
                    if run not in rescored:
                        replies = _read_jsonl(path.parent / run / "replies.jsonl")
                        rescored[run] = se.score_run(alerts, replies)
                pairs[pair] = se.compare(rescored[a], rescored[b], alerts)
        out[set_name] = {
            "alerts": len(alerts),
            "attack_alerts": sum(1 for a in alerts.values() if a["is_attack"]),
            "datasets": sorted({a["dataset"] for a in alerts.values()}),
            "runs": runs,
            "pairs": pairs,
        }
    return out


def compare(set_name: str, a: str, b: str, limit: int = 200) -> dict:
    """Every attack alert where exactly one of two runs is right, and every
    false alarm the two runs labeled differently, with both replies."""
    from scripts import score_explanations as se

    d = _set_dir(set_name)
    alerts = {x["id"]: x for x in _read_jsonl(d / "alerts.jsonl")}
    replies, scopes = {}, {}
    for run in (a, b):
        path = OUT / "explanations" / set_name / run / "replies.jsonl"
        if not path.exists():
            raise KeyError(f"unknown run: {run}")
        meta = _run_meta(set_name, run)
        targets = se.declared_targets(set_name, run, meta, alerts)
        replies[run] = se.target_replies({r["id"]: r for r in _read_jsonl(path)}, targets)
        scopes[run] = meta.get("scope", "alert")
    packets = {s: {r["id"]: r["evidence"] for r in _read_jsonl(d / f"packets_{s}.jsonl")}
               for s in set(scopes.values()) if (d / f"packets_{s}.jsonl").exists()}

    def label(run: str, alert_id: str) -> str | None:
        r = replies[run].get(alert_id)
        if r is None:
            return None
        return "no answer" if r.get("error") else r.get("attack_type")

    rows = []
    for alert_id, al in alerts.items():
        la, lb = label(a, alert_id), label(b, alert_id)
        if la is None or lb is None:
            continue
        ca, cb = la == al["true_type"], lb == al["true_type"]
        if al["is_attack"] and ca == cb:
            continue
        if not al["is_attack"] and la == lb:
            continue
        def view(run: str) -> dict:
            r = replies[run][alert_id]
            return {"label": label(run, alert_id), "correct": label(run, alert_id) == al["true_type"],
                    "summary": r.get("summary"), "claims": r.get("claims") or [],
                    "error": r.get("error"), "latency_s": r.get("latency_s")}
        scope = scopes[a]
        ev = packets.get(scope, {}).get(alert_id, {})
        rows.append({
            "id": alert_id, "dataset": al["dataset"], "true_type": al["true_type"],
            "is_attack": al["is_attack"], "span_s": [al["start"], al["end"]],
            "evidence": [{"id": i["id"], "kind": i["kind"], "text": i["text"]}
                         for i in ev.get("items", []) if i["kind"] != "frames"],
            "a": view(a), "b": view(b),
        })
    return {"set": set_name, "a": a, "b": b, "total": len(rows), "alerts": rows[:limit]}


def packets(set_name: str, scope: str = "alert") -> str:
    """The frozen packets as JSON lines: ids and evidence only, no labels."""
    path = _set_dir(set_name) / f"packets_{scope}.jsonl"
    if not path.exists():
        raise KeyError(f"no {scope} packets for {set_name}")
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------------

class SubmissionError(ValueError):
    pass


def submit(set_name: str, name: str, raw: bytes, description: str = "") -> dict:
    """Validate an uploaded predictions file, save it as a run, rescore the set."""
    d = _set_dir(set_name)
    if not NAME_RE.match(name or ""):
        raise SubmissionError("name: 1 to 48 letters, digits, '.', '_' or '-'")
    if len(raw) > MAX_SUBMISSION_BYTES:
        raise SubmissionError(f"file larger than {MAX_SUBMISSION_BYTES // 1_000_000} MB")
    run = f"submitted-{name}"
    run_dir = OUT / "explanations" / set_name / run
    if run_dir.exists():
        raise SubmissionError(f"a submission named {name!r} already exists for {set_name}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SubmissionError("file is not UTF-8 text") from exc

    known = {a["id"] for a in _read_jsonl(d / "alerts.jsonl")}
    evidence = {r["id"]: r["evidence"] for r in _read_jsonl(d / "packets_alert.jsonl")}
    seen, rows = set(), []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SubmissionError(f"line {n}: not valid JSON ({exc.msg})") from exc
        if not isinstance(obj, dict):
            raise SubmissionError(f"line {n}: expected a JSON object")
        alert_id = obj.get("id")
        if alert_id not in known:
            raise SubmissionError(f"line {n}: unknown alert id {alert_id!r}")
        if alert_id in seen:
            raise SubmissionError(f"line {n}: duplicate alert id {alert_id}")
        seen.add(alert_id)
        label = str(obj.get("attack_type", "")).lower().strip()
        if label not in ATTACK_LABELS:
            raise SubmissionError(f"line {n}: attack_type must be one of {', '.join(ATTACK_LABELS)}")
        claims = [c for c in (obj.get("claims") or []) if isinstance(c, dict)
                  and isinstance(c.get("text"), str)]
        exp = _check_citations(Explanation(attack_type=label, confidence=0.0, severity="",
                                           affected_function="", summary=str(obj.get("summary", "")),
                                           claims=[{"text": c["text"][:2000],
                                                    "cites": [str(x) for x in (c.get("cites") or [])][:20]}
                                                   for c in claims[:20]]),
                               evidence[alert_id])
        latency = obj.get("latency_s")
        rows.append({"id": alert_id, "error": None, "raw": None, "attack_type": label,
                     "summary": exp.summary[:4000], "claims": exp.claims, "grounded": exp.grounded,
                     "evidence_ids": sorted(i["id"] for i in evidence[alert_id]["items"]),
                     "latency_s": float(latency) if isinstance(latency, (int, float)) else None})
    if not rows:
        raise SubmissionError("no predictions in file")
    # An alert left out is a wrong answer, as a failed reply is for built-in
    # runs: otherwise a submission could skip the hard cases and score higher.
    skipped = sorted(known - seen)
    rows += [{"id": alert_id, "error": "no prediction submitted", "raw": None,
              "attack_type": None, "summary": "", "claims": [], "grounded": False,
              "evidence_ids": [], "latency_s": None} for alert_id in skipped]
    missing = len(skipped)

    run_dir.mkdir(parents=True)
    (run_dir / "replies.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run_dir / "run.json").write_text(json.dumps({
        "set": set_name, "run": run, "explainer": "submission", "model": name,
        "description": description[:500], "scope": "alert", "prompt_version": None,
        "alerts": len(rows) - missing, "errors": 0, "missing_alerts": missing,
        "submitted_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2) + "\n")
    rescore(set_name)
    return {"run": run, "predictions": len(rows) - missing, "missing_alerts": missing}


def rescore(set_name: str) -> None:
    from scripts import score_explanations as se
    alerts = {a["id"]: a for a in _read_jsonl(_set_dir(set_name) / "alerts.jsonl")}
    root = OUT / "explanations" / set_name
    names = sorted(p.name for p in root.iterdir() if (p / "replies.jsonl").exists())
    se.write_report(set_name, alerts, root, names)
