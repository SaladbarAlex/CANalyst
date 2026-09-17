"""Evaluation metrics.

Window-level detection metrics plus per-attack-type recall and
classification accuracy for the explanation layer.
"""
from __future__ import annotations

import pandas as pd


def detection_metrics(windows: pd.DataFrame, skip_until: float = 0.0) -> dict:
    """Precision, recall and F1 over windows.

    Windows ending before skip_until are excluded, because that stretch
    trained the baseline and scoring it would leak.
    """
    ev = windows[windows["end"] > skip_until]
    tp = int(((ev["flagged"]) & (ev["label"] == 1)).sum())
    fp = int(((ev["flagged"]) & (ev["label"] == 0)).sum())
    fn = int(((~ev["flagged"]) & (ev["label"] == 1)).sum())
    tn = int(((~ev["flagged"]) & (ev["label"] == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    per_type = {}
    for atype, grp in ev[ev["label"] == 1].groupby("attack_type"):
        per_type[str(atype)] = {
            "windows": int(len(grp)),
            "detected": int(grp["flagged"].sum()),
            "recall": round(float(grp["flagged"].mean()), 4),
        }

    return {
        "windows_evaluated": int(len(ev)),
        "true_positive": tp, "false_positive": fp,
        "false_negative": fn, "true_negative": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "per_attack_type": per_type,
        "labeled": bool(ev["label"].max() > 0),
    }


def classification_accuracy(alerts: list[dict]) -> dict:
    """How often the explainer's attack_type matches ground truth.

    Only alerts that overlap a labeled attack interval count. The
    confusion counts are per predicted/true pair.
    """
    scored = [a for a in alerts if a.get("true_type") and a["true_type"] != "normal"]
    if not scored:
        return {"scored_alerts": 0, "accuracy": None, "confusion": {}}
    correct = 0
    confusion: dict[str, dict[str, int]] = {}
    for a in scored:
        true_t, pred = a["true_type"], (a.get("explanation") or {}).get("attack_type", "unknown")
        confusion.setdefault(true_t, {}).setdefault(pred, 0)
        confusion[true_t][pred] += 1
        if true_t == pred:
            correct += 1
    return {
        "scored_alerts": len(scored),
        "accuracy": round(correct / len(scored), 4),
        "confusion": confusion,
    }


def grounding_rate(alerts: list[dict]) -> dict:
    """Fraction of explanations whose every claim cites real evidence."""
    with_exp = [a for a in alerts if a.get("explanation")]
    if not with_exp:
        return {"explained": 0, "grounded_rate": None}
    grounded = sum(1 for a in with_exp if a["explanation"].get("grounded"))
    claims = sum(len(a["explanation"].get("claims", [])) for a in with_exp)
    uncited = sum(1 for a in with_exp for c in a["explanation"].get("claims", [])
                  if not c.get("cites"))
    return {
        "explained": len(with_exp),
        "grounded_rate": round(grounded / len(with_exp), 4),
        "total_claims": claims,
        "uncited_claims": uncited,
    }
