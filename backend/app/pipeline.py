"""Pipeline orchestration and the in-memory analysis store."""
from __future__ import annotations

import uuid
import time
import threading
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import features, loader, metrics
from .detector import Alert, get_detector
from .evidence import build_evidence
from .features import Baseline
from .llm import Explainer, Explanation, explainer_key, get_explainer
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
    # explainer_key -> alert_id -> explanation, so switching explainers never
    # shows one model's answer under another's name.
    explanations: dict[str, dict[int, Explanation]] = field(default_factory=dict)
    evidence_cache: dict[int, dict] = field(default_factory=dict)

    timing_s: dict[str, float] = field(default_factory=dict)
    _summary_cache: dict | None = field(default=None, init=False, repr=False)
    _timeline_default: dict | None = field(default=None, init=False, repr=False)
    _alert_rows: dict[int, dict] = field(default_factory=dict, repr=False)
    _id_rows: list[dict] | None = field(default=None, repr=False)
    _locks: dict[tuple[str, int], threading.Lock] = field(default_factory=dict, repr=False)
    _cache_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # --- derived views -------------------------------------------------
    def summary(self) -> dict:
        if self._summary_cache is None:
            m = metrics.detection_metrics(self.windows, skip_until=self.baseline_end)
            observed_ids = set(int(v) for v in self.df["can_id"].unique())
            self._summary_cache = {
                "analysis_id": self.analysis_id,
                "source": self.source,
                "params": self.params,
                "detector": self.detector,
                "duration_s": round(float(self.df["timestamp"].max()), 3),
                "frame_count": int(len(self.df)),
                "unique_ids": len(observed_ids),
                "unknown_ids_count": len(observed_ids - self.baseline.known_ids),
                "mean_rate": round(len(self.df) / max(float(self.df["timestamp"].max()), 1e-6), 1),
                "baseline_end": self.baseline_end,
                "window_count": int(len(self.windows)),
                "alert_count": len(self.alerts),
                "attack_intervals": self.df.attrs.get("attack_intervals", []),
                "labeled": bool(self.df.attrs.get("has_labels", (self.df["attack_type"] != "unknown").all())),
                "metrics": m,
                "timing_s": self.timing_s,
                "baseline_source": "separate capture" if self.baseline_end == 0 else "clean prefix",
            }
        return {**self._summary_cache, "params": self.params, "timing_s": self.timing_s}

    def ask_context(self, explainer: Explainer | None = None) -> dict:
        """What the free-form question box may show a model.

        Ground truth (true types, injected intervals, the injected attack list,
        label-derived metrics) and the source filename, which often names the
        attack, are left out so an answer cannot read the label instead of the
        evidence.
        """
        summary = {k: v for k, v in self.summary().items()
                   if k not in {"source", "attack_intervals", "labeled", "metrics"}}
        summary["params"] = {k: v for k, v in self.params.items()
                             if k in {"window_s", "stride_s", "baseline_s", "threshold"}}
        alerts = [{k: v for k, v in a.items() if k != "true_type"}
                  for a in self.alert_list(include_explanations=True, explainer=explainer)]
        for a in alerts:
            if "explanation" in a:  # raw replies only bloat the prompt
                a["explanation"] = {k: v for k, v in a["explanation"].items()
                                    if k != "raw_response"}
        return {"summary": summary, "alerts": alerts, "baseline": self.baseline.to_json()}

    def timeline(self, max_points: int = 2000) -> dict:
        if max_points == 2000 and self._timeline_default is not None:
            return self._timeline_default
        w = self.windows
        original_count = len(w)
        if len(w) > max_points:
            # Keep real measurements at each bucket's rate and score extrema.
            # Uniform decimation can erase brief attacks entirely.
            selected = {0, len(w) - 1}
            for indices in np.array_split(np.arange(len(w)), max(1, (max_points - 2) // 4)):
                chunk = w.iloc[indices]
                for column in ("msg_rate", "score"):
                    values = chunk[column].to_numpy()
                    selected.update((int(indices[values.argmin()]), int(indices[values.argmax()])))
            w = w.iloc[sorted(selected)]
        result = {
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
            "original_point_count": original_count,
            "downsampled": original_count > len(w),
            "baseline_rate": round(self.baseline.total_rate, 2),
            "threshold": self.params.get("threshold", 0.55),
            "attack_intervals": self.df.attrs.get("attack_intervals", []),
            "alerts": [{"alert_id": a.alert_id, "start": a.start, "end": a.end, "score": a.score}
                       for a in self.alerts],
        }
        if max_points == 2000:
            self._timeline_default = result
        return result

    def id_table(self, limit: int = 80) -> list[dict]:
        if self._id_rows is not None:
            return self._id_rows[:limit]
        rows = []
        # Synthetic signal names are not a vehicle-independent CAN database.
        id_info = ID_INFO if self.df.attrs.get("source") == "synthetic" else {}
        flagged_ids: set[int] = set()
        for a in self.alerts:
            flagged_ids.update(a.top_ids)
        for cid, grp in self.df.groupby("can_id"):
            cid = int(cid)
            ts = grp["timestamp"].to_numpy()
            iats = np.diff(ts)
            info = id_info.get(cid, {})
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
        self._id_rows = rows
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
            return "unknown" if (seg["attack_type"] == "unknown").any() else "normal"
        return str(atk["attack_type"].mode().iat[0])

    def evidence_for(self, alert_id: int) -> dict:
        if alert_id not in self.evidence_cache:
            alert = self.alerts[alert_id]
            self.evidence_cache[alert_id] = build_evidence(
                alert, self.df, self.windows, self.baseline)
        return self.evidence_cache[alert_id]

    def explain(self, alert_id: int, explainer: Explainer, force: bool = False) -> Explanation:
        key = explainer_key(explainer)
        with self._cache_lock:
            lock = self._locks.setdefault((key, alert_id), threading.Lock())
        # Two tabs requesting the same alert share one hosted request.
        with lock:
            cache = self.explanations.setdefault(key, {})
            if force or alert_id not in cache:
                cache[alert_id] = explainer.explain(self.evidence_for(alert_id))
            return cache[alert_id]

    def cached_explanation(self, alert_id: int, explainer: Explainer) -> Explanation | None:
        return self.explanations.get(explainer_key(explainer), {}).get(alert_id)

    def alert_item(self, alert_id: int, include_explanations: bool = False,
                   explainer: Explainer | None = None) -> dict:
        if alert_id not in self._alert_rows:
            a = self.alerts[alert_id]
            ev = self.evidence_for(alert_id)
            self._alert_rows[alert_id] = {
                "alert_id": a.alert_id, "start": a.start, "end": a.end,
                "duration_s": round(a.end - a.start, 3), "score": a.score,
                "components": a.components, "reasons": a.reasons,
                "ids_involved": ev["ids_involved"], "frame_count": ev["frame_count"],
                "true_type": self.true_type_for(a),
            }
        item = dict(self._alert_rows[alert_id])
        if include_explanations:
            exp = self.cached_explanation(alert_id, explainer or get_explainer("mock"))
            if exp:
                item["explanation"] = exp.to_json()
        return item

    def alert_list(self, include_explanations: bool = False,
                   explainer: Explainer | None = None) -> list[dict]:
        """Read immutable alert measurements once; attach the requested model cache."""
        return [self.alert_item(a.alert_id, include_explanations, explainer) for a in self.alerts]


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
    started = time.perf_counter()
    if df.empty:
        raise ValueError("Capture contains no CAN frames")
    if not (0.05 < window_s <= 5 and 0.01 < stride_s <= window_s):
        raise ValueError("Require 0.05 < window_s <= 5 and 0.01 < stride_s <= window_s")
    if detector not in {"rule", "forest"}:
        raise ValueError("detector must be rule or forest")
    if not 0.05 <= threshold <= 0.99:
        raise ValueError("threshold must be between 0.05 and 0.99")
    t_max = float(df["timestamp"].max())
    if baseline_df is not None:
        if baseline_df.empty or baseline_df["label"].any():
            raise ValueError("Separate baseline must contain attack-free CAN frames")
        columns = ["timestamp", "can_id", "dlc", "data"]
        if df[columns].equals(baseline_df[columns]):
            raise ValueError("Evaluation capture and baseline must be separate traffic")
        baseline = features.learn_baseline(baseline_df, float("inf"), window_s=window_s)
        baseline_s = 0.0
    else:
        if baseline_s is None:
            baseline_s = float(df.attrs.get("benign_prefix_s", min(30.0, t_max * 0.25)))
            baseline_s = max(window_s * 4, min(baseline_s, t_max * 0.5))
        if not np.isfinite(baseline_s) or not window_s <= baseline_s < t_max:
            raise ValueError("Baseline duration must span at least one window and end before the capture")
        if df.loc[df.timestamp < baseline_s, "label"].any():
            raise ValueError("Opening baseline contains labeled attacks. Supply a separate normal baseline capture.")
        baseline = features.learn_baseline(df, baseline_s, window_s=window_s)
    baseline_done = time.perf_counter()
    windows = features.extract_windows(df, baseline, window_s=window_s, stride_s=stride_s)
    windows.attrs["has_labels"] = bool(df.attrs.get("has_labels", (df["attack_type"] != "unknown").all()))
    features_done = time.perf_counter()
    det = get_detector(detector, baseline, threshold=threshold)
    if detector == "forest":
        if baseline_df is not None:
            normal_windows = features.extract_windows(baseline_df, baseline, window_s=window_s, stride_s=stride_s)
            det.fit(normal_windows)
            windows, alerts = det.run(windows)
        else:
            windows, alerts = det.run(windows, fit_until=baseline_s)
    else:
        windows, alerts = det.run(windows)

    windows.attrs["has_labels"] = bool(df.attrs.get("has_labels", (df["attack_type"] != "unknown").all()))
    analysis = Analysis(
        analysis_id=uuid.uuid4().hex[:12],
        source=source,
        params={**params, "window_s": window_s, "stride_s": stride_s,
                "baseline_s": round(baseline_s, 2), "threshold": threshold,
                "calibration": getattr(det, "calibration", None)},
        df=df,
        baseline=baseline,
        windows=windows,
        alerts=alerts,
        baseline_end=baseline_s,
        detector=detector,
        timing_s={"baseline": round(baseline_done - started, 4),
                  "features": round(features_done - baseline_done, 4),
                  "detection": round(time.perf_counter() - features_done, 4),
                  "total": round(time.perf_counter() - started, 4)},
    )
    STORE.put(analysis)
    return analysis


def run_synthetic(duration_s: float = 120.0, seed: int = 7,
                  attacks: list[str] | None = None, **kwargs) -> Analysis:
    df = loader.load_synthetic(duration_s=duration_s, seed=seed, attacks=attacks)
    return run_analysis(df, source="synthetic",
                        params={"duration_s": duration_s, "seed": seed,
                                "attacks": attacks if attacks is not None else ["dos", "fuzzing", "spoofing", "masquerade"]},
                        **kwargs)


def explain_all(analysis: Analysis, explainer: Explainer) -> None:
    for a in analysis.alerts:
        analysis.explain(a.alert_id, explainer)


def evaluation_report(analysis: Analysis, explainer: Explainer, *, generate: bool = True) -> dict:
    if generate:
        explain_all(analysis, explainer)
    alerts = analysis.alert_list(include_explanations=True, explainer=explainer)
    return {
        "detection": metrics.detection_metrics(analysis.windows, skip_until=analysis.baseline_end),
        "classification": metrics.classification_accuracy([a for a in alerts if a.get("explanation")]),
        "explained_alerts": sum(bool(a.get("explanation")) for a in alerts),
        "total_alerts": len(alerts),
        "grounding": metrics.grounding_rate(alerts),
        "explainer": explainer.name,
        "detector": analysis.detector,
    }
