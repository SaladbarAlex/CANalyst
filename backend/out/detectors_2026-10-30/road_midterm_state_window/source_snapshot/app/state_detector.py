"""Experimental normal-only detector with window-scale operating-state references.

This module deliberately leaves the frozen midterm feature/evidence path alone.
The 80/20 split is within each baseline recording; calibration never sees an
attack/evaluation capture. Parameters are fixed before evaluating ROAD.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import features, loader
from .detector import Alert, merge_adjacent

# Fixed physical/finite-sample scale floors, not selected against evaluation labels.
FIELDS = {"rate": 6.0, "entropy": 0.15, "bitflip_rate": 0.02, "iat_std_ms": 0.005}
COMPONENT_FLOORS = {"state_deviation": 1.0, "payload_novelty": 0.25, "unknown_rate": 4.0}


def split_frames(captures: list[pd.DataFrame]) -> tuple[list[pd.DataFrame], list[float]]:
    training, cuts = [], []
    for df in captures:
        if df.empty or (df.label != 0).any():
            raise ValueError("State detector requires nonempty normal baseline captures.")
        begin, end = float(df.timestamp.min()), float(df.timestamp.max())
        cut = begin + 0.8 * (end - begin)
        if cut - begin < 10 or end - cut < 3:
            raise ValueError("Each normal capture needs at least 15 seconds for fitting/calibration.")
        training.append(df[df.timestamp < cut].copy())
        cuts.append(cut)
    return training, cuts


class StateDetector:
    name = "state_window"

    def __init__(self, window_s: float = .5, stride_s: float = .25, alpha: float = .01):
        self.window_s, self.stride_s, self.alpha = window_s, stride_s, alpha
        self.profiles = []
        self.allowed = {}
        self.cutoffs = {}
        self.calibration = {}

    def fit(self, captures: list[pd.DataFrame]) -> "StateDetector":
        train_parts, cuts = split_frames(captures)
        training = loader.concat_captures(train_parts)
        self.baseline = features.learn_baseline(training, float("inf"), window_s=self.window_s)
        self.profiles = []
        self.allowed = {}
        for cid, group in training.groupby("can_id"):
            allowed = [set() for _ in range(8)]
            for payload in group.data:
                for byte, value in enumerate(payload):
                    allowed[byte].add(value)
            self.allowed[int(cid)] = allowed
        calibration_samples = []
        training_counts, calibration_counts = [], []
        for index, (df, cut) in enumerate(zip(captures, cuts)):
            windows = features.extract_windows(df, self.baseline, self.window_s, self.stride_s)
            fit_windows = windows[windows.end <= cut]
            calibration_windows = windows[(windows.start >= cut) & (windows.end <= df.timestamp.max())]
            if len(fit_windows) < 10 or len(calibration_windows) < 5:
                raise ValueError("Insufficient disjoint normal fitting/calibration windows.")
            profile = {}
            for cid in self.baseline.known_ids:
                reference = {}
                for field, floor in FIELDS.items():
                    values = []
                    for per_id in fit_windows.per_id:
                        record = per_id.get(cid)
                        if field == "rate":
                            values.append(record["rate"] if record else 0.0)
                        elif record and record["count"] >= 8:
                            values.append(record[field])
                    if values:
                        lo, q25, q75, hi = np.quantile(values, [.005, .25, .75, .995])
                        reference[field] = (float(lo), float(hi), max(float(q75 - q25), floor))
                profile[cid] = reference
            self.profiles.append(profile)
            training_counts.append(len(fit_windows))
            calibration_counts.append(len(calibration_windows))
            calibration_samples.append((df, calibration_windows))
        # All normal states are available before calibration is scored.
        raw = []
        for df, windows in calibration_samples:
            for row in windows.itertuples():
                raw.append(self.raw_window(row, df)[0])
        quantile = 1.0 - self.alpha / len(COMPONENT_FLOORS)
        self.cutoffs = {key: max(float(np.quantile([r[key] for r in raw], quantile,
                                                  method="higher")), floor)
                        for key, floor in COMPONENT_FLOORS.items()}
        self.calibration = {
            "method": "per_capture_normal_window_profiles_v1",
            "normal_fraction_for_fitting": .8, "alpha_target": self.alpha,
            "component_quantile": quantile, "cutoffs": self.cutoffs,
            "training_windows_per_capture": training_counts,
            "calibration_windows_per_capture": calibration_counts,
            "split_timestamp_per_capture": cuts, "field_scale_floors": FIELDS,
            "component_floors": COMPONENT_FLOORS,
            "decision": "max(raw_component / normal_cutoff) > 1; displayed score ratio/(1+ratio)",
            "normal_profiles": len(self.profiles),
            "limitations": "Normal calibration targets are empirical; overlapping windows are dependent. "
                           "A saturated novelty cutoff of 1 disables that component. No accuracy guarantee.",
        }
        return self

    def raw_window(self, row, df: pd.DataFrame) -> tuple[dict, list[str], list[int]]:
        profile_scores = []
        for profile in self.profiles:
            strongest, reasons, involved = 0.0, [], []
            for cid, reference in profile.items():
                observed = row.per_id.get(cid)
                for field, (low, high, scale) in reference.items():
                    if field == "rate":
                        value = observed["rate"] if observed else 0.0
                    elif observed and observed["count"] >= 8:
                        value = observed[field]
                    else:
                        continue
                    deviation = max(low - value, value - high, 0.0) / scale
                    if deviation > strongest:
                        strongest = deviation
                        reasons = [f"0x{cid:03X} {field} {value:.4g} outside normal window range [{low:.4g}, {high:.4g}]"]
                        involved = [cid]
            profile_scores.append((strongest, reasons, involved))
        state, reasons, involved = min(profile_scores, key=lambda v: v[0])
        timestamps = df.timestamp.to_numpy()
        lo, hi = np.searchsorted(timestamps, [row.start, row.end])
        window = df.iloc[lo:hi]
        novelty = 0.0
        unknown_frames = 0
        for cid, group in window.groupby("can_id"):
            cid = int(cid)
            if cid not in self.allowed:
                unknown_frames += len(group)
                involved.append(cid)
                continue
            if len(group) < 4:
                continue
            for byte, allowed in enumerate(self.allowed[cid]):
                values = [payload[byte] for payload in group.data if len(payload) > byte]
                if len(values) < 4:
                    continue
                fraction = sum(value not in allowed for value in values) / len(values)
                if fraction > novelty:
                    novelty = fraction
                    involved.append(cid)
        return {"state_deviation": state, "payload_novelty": novelty,
                "unknown_rate": unknown_frames / self.window_s}, reasons, list(dict.fromkeys(involved))[:5]

    def run(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[Alert]]:
        if not self.cutoffs:
            raise ValueError("Fit on normal captures before scoring.")
        df = df.sort_values("timestamp", kind="stable")
        windows = features.extract_windows(df, self.baseline, self.window_s, self.stride_s)
        scores, components, reasons, tops = [], [], [], []
        for row in windows.itertuples():
            raw, why, ids = self.raw_window(row, df)
            ratios = {key: value / self.cutoffs[key] for key, value in raw.items()}
            normalized = {key: ratio / (1.0 + ratio) for key, ratio in ratios.items()}
            scores.append(max(normalized.values()))
            components.append(normalized)
            if raw["payload_novelty"] > self.cutoffs["payload_novelty"]:
                why.append(f"Payload byte novelty fraction {raw['payload_novelty']:.3f} exceeds normal calibration")
            if raw["unknown_rate"] > self.cutoffs["unknown_rate"]:
                why.append(f"Unknown IDs transmitted {raw['unknown_rate']:.1f} frames/s")
            reasons.append(why)
            tops.append(ids)
        windows["score"] = scores
        windows["flagged"] = windows.score > .5
        windows["components"], windows["reasons"], windows["top_ids"] = components, reasons, tops
        alerts = [Alert(i, int(r.window), float(r.start), float(r.end), float(r.score),
                        r.components, r.reasons, r.top_ids)
                  for i, r in enumerate(windows[windows.flagged].itertuples())]
        return windows, merge_adjacent(alerts)
