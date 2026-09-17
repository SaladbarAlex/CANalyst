"""Window-level anomaly detection.

Two detectors share one interface:

  RuleDetector  - interpretable statistical scoring, the default. Each
                  component maps a measured deviation to a 0..1 score, and
                  the window score is the strongest component. Because the
                  components are named, the alert carries its own reasons.

  ForestDetector - IsolationForest over the same feature vector, kept as a
                  learned comparison point for the evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS, Baseline


@dataclass
class Alert:
    alert_id: int
    window: int
    start: float
    end: float
    score: float
    components: dict[str, float]
    reasons: list[str]
    top_ids: list[int]


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


class RuleDetector:
    name = "rule"

    def __init__(self, baseline: Baseline, threshold: float = 0.55):
        self.baseline = baseline
        self.threshold = threshold

    def score_window(self, row: pd.Series) -> tuple[float, dict[str, float], list[str], list[int]]:
        per_id: dict[int, dict] = row["per_id"]
        comp: dict[str, float] = {}
        reasons: list[str] = []

        # 1. Total bus load. A flood pushes the whole bus rate up.
        load = row["rate_ratio_total"]
        comp["bus_load"] = _clip01((load - 1.25) / 1.75)
        if comp["bus_load"] > 0.3:
            reasons.append(f"Bus load is {load:.2f}x baseline")

        # 2. Unknown arbitration IDs, the fuzzing signature.
        comp["unknown_ids"] = _clip01(row["n_unknown_ids"] / 8.0)
        if row["n_unknown_ids"] > 0:
            ids = ", ".join(f"0x{i:03X}" for i in row["unknown_ids"][:4])
            comp["unknown_ids"] = max(comp["unknown_ids"], 0.6)
            reasons.append(f"{row['n_unknown_ids']} ID(s) never seen in baseline ({ids})")

        # 3. Per-ID rate inflation, the fabrication/spoofing signature.
        comp["rate_inflation"] = _clip01((row["max_rate_ratio"] - 1.35) / 1.15)
        if comp["rate_inflation"] > 0.3:
            worst = max((c for c in per_id if per_id[c]["known"]),
                        key=lambda c: per_id[c]["rate_ratio"] or 0, default=None)
            if worst is not None:
                reasons.append(
                    f"0x{worst:03X} is sending {per_id[worst]['rate_ratio']:.2f}x its baseline rate")

        # 4. Missing IDs, which suppression or bus-off leaves behind.
        comp["missing_ids"] = _clip01(row["n_missing_ids"] / 3.0)
        if row["n_missing_ids"] > 0:
            ids = ", ".join(f"0x{i:03X}" for i in row["missing_ids"][:4])
            reasons.append(f"{row['n_missing_ids']} expected ID(s) absent ({ids})")

        # 5. Timing structure. Injection breaks the rhythm; masquerade flattens jitter.
        comp["timing"] = _clip01((row["max_iat_z"] - 3.0) / 9.0)
        # Jitter collapse only means something with enough samples in the window,
        # so low-rate IDs (a handful of frames) are excluded rather than flagged.
        jitter_flags = [
            c for c, v in per_id.items()
            if v["known"] and v["count"] >= 8 and v["jitter_ratio"] is not None
            and v["jitter_ratio"] < 0.35 and v["baseline_iat_ms"] > 0
            and 0.8 <= (v["rate_ratio"] or 0) <= 1.25
        ]
        if jitter_flags:
            comp["timing"] = max(comp["timing"], 0.6)
            reasons.append(
                "Timing jitter collapsed on " +
                ", ".join(f"0x{c:03X}" for c in jitter_flags[:3]) +
                " (consistent with a different sender)")
        elif comp["timing"] > 0.3:
            reasons.append(f"Inter-arrival times deviate up to {row['max_iat_z']:.1f} sigma")

        # 6. Payload randomness.
        comp["payload_entropy"] = _clip01(row["max_entropy_delta"] / 2.5)
        if comp["payload_entropy"] > 0.3:
            reasons.append(f"Payload entropy up {row['max_entropy_delta']:.2f} bits over baseline")

        score = max(comp.values()) if comp else 0.0
        ranked = sorted(
            (c for c in per_id),
            key=lambda c: (
                not per_id[c]["known"],
                (per_id[c]["rate_ratio"] or 0) if per_id[c]["known"] else 0,
                per_id[c]["count"],
            ),
            reverse=True,
        )
        return score, {k: round(v, 3) for k, v in comp.items()}, reasons, ranked[:5]

    def run(self, windows: pd.DataFrame) -> tuple[pd.DataFrame, list[Alert]]:
        scores, comps, reasons_all, tops = [], [], [], []
        for _, row in windows.iterrows():
            s, c, r, t = self.score_window(row)
            scores.append(s)
            comps.append(c)
            reasons_all.append(r)
            tops.append(t)
        out = windows.copy()
        out["score"] = np.round(scores, 4)
        out["components"] = comps
        out["reasons"] = reasons_all
        out["top_ids"] = tops
        out["flagged"] = out["score"] >= self.threshold

        alerts: list[Alert] = []
        for i, (_, row) in enumerate(out[out["flagged"]].iterrows()):
            alerts.append(Alert(
                alert_id=len(alerts),
                window=int(row["window"]),
                start=float(row["start"]),
                end=float(row["end"]),
                score=float(row["score"]),
                components=row["components"],
                reasons=row["reasons"],
                top_ids=row["top_ids"],
            ))
        return out, merge_adjacent(alerts)


class ForestDetector:
    """IsolationForest baseline over the same features, for comparison."""

    name = "forest"

    def __init__(self, baseline: Baseline, contamination: float = 0.1):
        from sklearn.ensemble import IsolationForest
        self.baseline = baseline
        self.model = IsolationForest(n_estimators=200, contamination=contamination,
                                     random_state=0)

    def _matrix(self, windows: pd.DataFrame) -> np.ndarray:
        X = windows[FEATURE_COLUMNS].to_numpy(dtype=float)
        return np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)

    def run(self, windows: pd.DataFrame, fit_until: float | None = None
            ) -> tuple[pd.DataFrame, list[Alert]]:
        X = self._matrix(windows)
        fit_rows = X if fit_until is None else X[windows["end"].to_numpy() <= fit_until]
        self.model.fit(fit_rows if len(fit_rows) > 10 else X)
        raw = -self.model.score_samples(X)  # higher means more anomalous
        lo, hi = float(raw.min()), float(raw.max())
        norm = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)
        out = windows.copy()
        out["score"] = np.round(norm, 4)
        out["components"] = [{"isolation_forest": round(float(v), 3)} for v in norm]
        out["reasons"] = [["IsolationForest flagged this window as an outlier"] for _ in norm]
        out["top_ids"] = [sorted(r, key=lambda c: r[c]["count"], reverse=True)[:5]
                          for r in windows["per_id"]]
        out["flagged"] = out["score"] >= 0.6
        alerts = [
            Alert(alert_id=i, window=int(row["window"]), start=float(row["start"]),
                  end=float(row["end"]), score=float(row["score"]),
                  components=row["components"], reasons=row["reasons"], top_ids=row["top_ids"])
            for i, (_, row) in enumerate(out[out["flagged"]].iterrows())
        ]
        return out, merge_adjacent(alerts)


def merge_adjacent(alerts: list[Alert], gap_s: float = 0.26) -> list[Alert]:
    """Collapse consecutive flagged windows into one alert per incident."""
    if not alerts:
        return []
    merged: list[Alert] = []
    cur = alerts[0]
    for nxt in alerts[1:]:
        if nxt.start - cur.end <= gap_s:
            comps = {k: max(cur.components.get(k, 0), nxt.components.get(k, 0))
                     for k in set(cur.components) | set(nxt.components)}
            # Merged windows repeat the same reason with different numbers, so
            # dedupe on the wording and keep the first occurrence.
            def key(r: str) -> str:
                return " ".join(r.split()[:3]).lower()
            seen = {key(r) for r in cur.reasons}
            nxt = Alert(nxt.alert_id, nxt.window, nxt.start, nxt.end, nxt.score,
                        nxt.components,
                        [r for r in nxt.reasons if key(r) not in seen],
                        nxt.top_ids)
            cur = Alert(
                alert_id=cur.alert_id,
                window=cur.window,
                start=cur.start,
                end=max(cur.end, nxt.end),
                score=max(cur.score, nxt.score),
                components=comps,
                reasons=(cur.reasons + nxt.reasons)[:8],
                top_ids=list(dict.fromkeys(cur.top_ids + nxt.top_ids))[:5],
            )
        else:
            merged.append(cur)
            cur = nxt
    merged.append(cur)
    for i, a in enumerate(merged):
        a.alert_id = i
    return merged


def get_detector(kind: str, baseline: Baseline, threshold: float = 0.55):
    if kind == "forest":
        return ForestDetector(baseline)
    return RuleDetector(baseline, threshold=threshold)
