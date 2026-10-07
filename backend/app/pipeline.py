"""Pipeline orchestration and the in-memory analysis store."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import features, loader, metrics
from .detector import Alert, get_detector
from .evidence import build_evidence
from .features import Baseline
from .llm import Explainer, Explanation, get_explainer
from .synth import ID_INFO


@dataclass
class Analysis:
    analysis_id: str
    source: str
    params: dict
    df: pd.DataFrame
    baseline: Baseline
    windows: pd.DataFrame
    alerts: list[Alert]
    baseline_end: float
    detector: str
    explanations: dict[int, Explanation] = field(default_factory=dict)
    evidence_cache: dict[int, dict] = field(default_factory=dict)

    # --- derived views -------------------------------------------------
    def summary(self) -> dict:
        m = metrics.detection_metrics(self.windows, skip_until=self.baseline_end)
        return {
            "analysis_id": self.analysis_id,
            "source": self.source,
            "params": self.params,
            "detector": self.detector,
            "duration_s": round(float(self.df["timestamp"].max()), 3),
            "frame_count": int(len(self.df)),
            "unique_ids": int(self.df["can_id"].nunique()),
            "mean_rate": round(len(self.df) / max(float(self.df["timestamp"].max()), 1e-6), 1),
            "baseline_end": self.baseline_end,
            "window_count": int(len(self.windows)),
            "alert_count": len(self.alerts),
            "attack_intervals": self.df.attrs.get("attack_intervals", []),
            "labeled": bool(self.df["label"].max() > 0),
            "metrics": m,
        }

    def timeline(self) -> dict:
        w = self.windows
        return {
            "points": [
                {
                    "t": float(r.start),
                    "msg_rate": float(r.msg_rate),
                    "score": float(r.score),
                    "flagged": bool(r.flagged),
                    "label": int(r.label),
                }
                for r in w.itertuples()
            ],
            "baseline_rate": round(self.baseline.total_rate, 2),
            "threshold": self.params.get("threshold", 0.55),
            "attack_intervals": self.df.attrs.get("attack_intervals", []),
            "alerts": [{"alert_id": a.alert_id, "start": a.start, "end": a.end, "score": a.score}
                       for a in self.alerts],
        }

    def id_table(self, limit: int = 80) -> list[dict]:
        rows = []
        flagged_ids: set[int] = set()
        for a in self.alerts:
            flagged_ids.update(a.top_ids)
        for cid, grp in self.df.groupby("can_id"):
            cid = int(cid)
            ts = grp["timestamp"].to_numpy()
            iats = np.diff(ts)
            info = ID_INFO.get(cid, {})
            rows.append({
                "can_id": f"0x{cid:03X}",
                "name": info.get("name", "unknown"),
                "function": info.get("function", "unknown"),
                "count": int(len(grp)),
                "rate": round(len(grp) / max(float(self.df["timestamp"].max()), 1e-6), 2),
                "baseline_rate": round(self.baseline.rate.get(cid, 0.0), 2),
                "iat_mean_ms": round(float(iats.mean()) * 1000, 3) if iats.size else 0.0,
                "iat_std_ms": round(float(iats.std()) * 1000, 3) if iats.size else 0.0,
                "entropy": round(features.byte_entropy(list(grp["data"])), 3),
                "baseline_entropy": round(self.baseline.entropy.get(cid, 0.0), 3),
                "known": cid in self.baseline.known_ids,
                "in_alert": cid in flagged_ids,
            })
        # Fuzzing can introduce hundreds of one-off IDs, so the most
        # interesting rows come first and the tail is truncated.
        rows.sort(key=lambda r: (not r["in_alert"], r["known"], -r["count"]))
        return rows[:limit]

    def id_series(self, can_id: int, bucket_s: float = 0.5) -> dict:
        seg = self.df[self.df["can_id"] == can_id]
        t_max = float(self.df["timestamp"].max())
        edges = np.arange(0, t_max + bucket_s, bucket_s)
        counts, _ = np.histogram(seg["timestamp"].to_numpy(), bins=edges)
        return {
            "can_id": f"0x{can_id:03X}",
            "baseline_rate": round(self.baseline.rate.get(can_id, 0.0), 2),
            "points": [{"t": round(float(edges[i]), 3), "rate": round(float(c) / bucket_s, 2)}
                       for i, c in enumerate(counts)],
        }

    def true_type_for(self, alert: Alert) -> str:
        seg = self.df[(self.df["timestamp"] >= alert.start) & (self.df["timestamp"] < alert.end)]
        atk = seg[seg["label"] == 1]
        if atk.empty:
            return "normal"
        return str(atk["attack_type"].mode().iat[0])

    def evidence_for(self, alert_id: int) -> dict:
        if alert_id not in self.evidence_cache:
            alert = self.alerts[alert_id]
            self.evidence_cache[alert_id] = build_evidence(
                alert, self.df, self.windows, self.baseline)
        return self.evidence_cache[alert_id]

    def explain(self, alert_id: int, explainer: Explainer, force: bool = False) -> Explanation:
        if force or alert_id not in self.explanations:
            self.explanations[alert_id] = explainer.explain(self.evidence_for(alert_id))
        return self.explanations[alert_id]

    def alert_list(self, include_explanations: bool = False) -> list[dict]:
        out = []
        for a in self.alerts:
            ev = self.evidence_for(a.alert_id)
            item = {
                "alert_id": a.alert_id,
                "start": a.start,
                "end": a.end,
                "duration_s": round(a.end - a.start, 3),
                "score": a.score,
                "components": a.components,
                "reasons": a.reasons,
                "ids_involved": ev["ids_involved"],
                "frame_count": ev["frame_count"],
                "true_type": self.true_type_for(a),
            }
            exp = self.explanations.get(a.alert_id)
            if include_explanations and exp:
                item["explanation"] = exp.to_json()
            out.append(item)
        return out


class Store:
    def __init__(self) -> None:
        self._items: dict[str, Analysis] = {}

    def put(self, analysis: Analysis) -> None:
        self._items[analysis.analysis_id] = analysis
        # Keep memory bounded: drop the oldest beyond 8 analyses.
        if len(self._items) > 8:
            oldest = next(iter(self._items))
            self._items.pop(oldest, None)

    def get(self, analysis_id: str) -> Analysis | None:
        return self._items.get(analysis_id)

    def list(self) -> list[dict]:
        return [{"analysis_id": a.analysis_id, "source": a.source,
                 "frame_count": int(len(a.df)), "alert_count": len(a.alerts)}
                for a in self._items.values()]


STORE = Store()


def run_analysis(df: pd.DataFrame, *, source: str, params: dict,
                 window_s: float = 0.5, stride_s: float = 0.25,
                 baseline_s: float | None = None, detector: str = "rule",
                 threshold: float = 0.55,
                 baseline_df: pd.DataFrame | None = None) -> Analysis:
    """Baseline, window, detect. Explanations are generated on demand.

    By default the baseline is learned from the log's own opening stretch.
    Pass baseline_df (a separate attack-free capture of the same vehicle)
    when the log has no clean prefix; the whole log is then scored.
    """
    t_max = float(df["timestamp"].max())
    if baseline_df is not None:
        baseline = features.learn_baseline(baseline_df, float("inf"), window_s=window_s)
        baseline_s = 0.0
    else:
        if baseline_s is None:
            baseline_s = float(df.attrs.get("benign_prefix_s", min(30.0, t_max * 0.25)))
        baseline_s = max(window_s * 4, min(baseline_s, t_max * 0.5))
        baseline = features.learn_baseline(df, baseline_s, window_s=window_s)
    windows = features.extract_windows(df, baseline, window_s=window_s, stride_s=stride_s)
    det = get_detector(detector, baseline, threshold=threshold)
    if detector == "forest":
        windows, alerts = det.run(windows, fit_until=baseline_s)
    else:
        windows, alerts = det.run(windows)

    analysis = Analysis(
        analysis_id=uuid.uuid4().hex[:12],
        source=source,
        params={**params, "window_s": window_s, "stride_s": stride_s,
                "baseline_s": round(baseline_s, 2), "threshold": threshold},
        df=df,
        baseline=baseline,
        windows=windows,
        alerts=alerts,
        baseline_end=baseline_s,
        detector=detector,
    )
    STORE.put(analysis)
    return analysis


def run_synthetic(duration_s: float = 120.0, seed: int = 7,
                  attacks: list[str] | None = None, **kwargs) -> Analysis:
    df = loader.load_synthetic(duration_s=duration_s, seed=seed, attacks=attacks)
    return run_analysis(df, source="synthetic",
                        params={"duration_s": duration_s, "seed": seed,
                                "attacks": attacks or ["dos", "fuzzing", "spoofing", "masquerade"]},
                        **kwargs)


def explain_all(analysis: Analysis, explainer: Explainer) -> None:
    for a in analysis.alerts:
        analysis.explain(a.alert_id, explainer)


def evaluation_report(analysis: Analysis, explainer: Explainer) -> dict:
    explain_all(analysis, explainer)
    alerts = analysis.alert_list(include_explanations=True)
    return {
        "detection": metrics.detection_metrics(analysis.windows, skip_until=analysis.baseline_end),
        "classification": metrics.classification_accuracy(alerts),
        "grounding": metrics.grounding_rate(alerts),
        "explainer": explainer.name,
        "detector": analysis.detector,
    }
