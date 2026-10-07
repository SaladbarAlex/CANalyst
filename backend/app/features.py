"""Windowed feature extraction for CAN traffic.

The traffic is cut into overlapping time windows. For each window we
compute both bus-level features (used by the detector) and per-ID
detail (used as evidence in explanations).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Baseline:
    """What normal looks like, learned from an attack-free stretch."""

    known_ids: set[int]
    rate: dict[int, float] = field(default_factory=dict)        # msgs/sec per ID
    iat_mean: dict[int, float] = field(default_factory=dict)    # mean inter-arrival time
    iat_std: dict[int, float] = field(default_factory=dict)
    jitter_floor: dict[int, float] = field(default_factory=dict)  # lowest jitter in any window
    entropy: dict[int, float] = field(default_factory=dict)     # mean payload entropy
    bitflip: dict[int, float] = field(default_factory=dict)     # mean per-byte flip rate
    total_rate: float = 0.0

    def to_json(self) -> dict:
        return {
            "known_ids": sorted(f"0x{i:03X}" for i in self.known_ids),
            "total_rate": round(self.total_rate, 2),
            "per_id": {
                f"0x{i:03X}": {
                    "rate": round(self.rate.get(i, 0.0), 2),
                    "iat_mean_ms": round(self.iat_mean.get(i, 0.0) * 1000, 3),
                    "iat_std_ms": round(self.iat_std.get(i, 0.0) * 1000, 3),
                    "entropy": round(self.entropy.get(i, 0.0), 3),
                }
                for i in sorted(self.known_ids)
            },
        }


def byte_entropy(payloads: list[list[int]]) -> float:
    """Shannon entropy in bits of the byte distribution, 0 to 8."""
    if not payloads:
        return 0.0
    flat = np.fromiter((b for p in payloads for b in p), dtype=np.int64)
    if flat.size == 0:
        return 0.0
    counts = np.bincount(flat, minlength=256).astype(float)
    p = counts[counts > 0] / flat.size
    return float(-(p * np.log2(p)).sum())


def bitflip_rate(payloads: list[list[int]]) -> float:
    """Mean fraction of bits that change between consecutive payloads (READ-style)."""
    if len(payloads) < 2:
        return 0.0
    width = max(len(p) for p in payloads)
    padded = np.array([[p[i] if i < len(p) else 0 for i in range(width)] for p in payloads],
                      dtype=np.uint8)
    xor = np.bitwise_xor(padded[1:], padded[:-1])
    bits = np.unpackbits(xor.reshape(-1, 1), axis=1)
    return float(bits.mean())


def learn_baseline(df: pd.DataFrame, end_s: float, window_s: float = 0.5) -> Baseline:
    """Learn normal behavior from timestamps < end_s (assumed attack free).

    Jitter is also measured per window_s chunk, because that is the scale
    windows are scored at. Jitter over a whole capture includes drift and
    gaps, so it overstates what a single window normally shows, and real
    ECUs vary a lot window to window. The floor is the lowest per-window
    jitter seen, so "collapsed" means quieter than this ID ever was.
    """
    seg = df[df["timestamp"] < end_s]
    if seg.empty:
        raise ValueError("Baseline segment is empty; increase benign_prefix_s.")
    span = max(1e-6, float(seg["timestamp"].max() - seg["timestamp"].min()))
    bl = Baseline(known_ids=set(int(i) for i in seg["can_id"].unique()))
    bl.total_rate = len(seg) / span
    for cid, grp in seg.groupby("can_id"):
        cid = int(cid)
        ts = grp["timestamp"].to_numpy()
        iats = np.diff(ts)
        bl.rate[cid] = len(grp) / span
        bl.iat_mean[cid] = float(iats.mean()) if iats.size else 0.0
        bl.iat_std[cid] = float(iats.std()) if iats.size else 0.0
        bl.jitter_floor[cid] = bl.iat_std[cid]
        if iats.size >= 7:
            chunks = pd.Series(iats).groupby((ts[1:] // window_s).astype(np.int64))
            per_chunk = chunks.std(ddof=0)[chunks.count() >= 7]
            if not per_chunk.empty:
                bl.jitter_floor[cid] = float(per_chunk.min())
        payloads = list(grp["data"])
        bl.entropy[cid] = byte_entropy(payloads)
        bl.bitflip[cid] = bitflip_rate(payloads)
    return bl


def _safe_ratio(obs: float, base: float) -> float:
    if base <= 1e-9:
        return float("inf") if obs > 0 else 1.0
    return obs / base


# Rate ratios are taken against at least this many expected frames per
# window. A 1 Hz ID seen once in a 0.5 s window is otherwise "2x baseline".
MIN_EXPECTED_FRAMES = 3.0


def extract_windows(df: pd.DataFrame, baseline: Baseline,
                    window_s: float = 0.5, stride_s: float = 0.25) -> pd.DataFrame:
    """Compute per-window features and per-ID detail.

    Returns one row per window with feature columns plus 'per_id' (a dict)
    and ground-truth 'label' / 'attack_type' when the log is labeled.
    """
    t_end = float(df["timestamp"].max())
    starts = np.arange(0.0, max(window_s, t_end - window_s + stride_s), stride_s)
    ts_all = df["timestamp"].to_numpy()
    rows = []

    for w_start in starts:
        w_end = w_start + window_s
        lo, hi = np.searchsorted(ts_all, [w_start, w_end])
        if hi <= lo:
            continue
        win = df.iloc[lo:hi]
        n = len(win)
        ids_seen = set(int(i) for i in win["can_id"].unique())
        unknown = sorted(ids_seen - baseline.known_ids)
        missing = sorted(i for i in baseline.known_ids
                         if i not in ids_seen
                         and baseline.rate.get(i, 0) * window_s >= MIN_EXPECTED_FRAMES)

        per_id: dict[int, dict] = {}
        max_rate_ratio, max_iat_z, max_entropy_delta, max_flip_delta = 1.0, 0.0, 0.0, 0.0
        for cid, grp in win.groupby("can_id"):
            cid = int(cid)
            ts = grp["timestamp"].to_numpy()
            iats = np.diff(ts)
            obs_rate = len(grp) / window_s
            base_rate = baseline.rate.get(cid, 0.0)
            ratio = (_safe_ratio(len(grp), max(base_rate * window_s, MIN_EXPECTED_FRAMES))
                     if base_rate > 0 else _safe_ratio(obs_rate, base_rate))
            iat_mean = float(iats.mean()) if iats.size else 0.0
            iat_std = float(iats.std()) if iats.size else 0.0
            base_iat = baseline.iat_mean.get(cid, 0.0)
            base_iat_std = max(baseline.iat_std.get(cid, 0.0), 1e-5)
            iat_z = abs(iat_mean - base_iat) / base_iat_std if base_iat > 0 and iats.size else 0.0
            ent = byte_entropy(list(grp["data"]))
            flip = bitflip_rate(list(grp["data"]))
            ent_delta = ent - baseline.entropy.get(cid, 0.0)
            flip_delta = flip - baseline.bitflip.get(cid, 0.0)
            # A frozen signal (std of IAT collapsing to ~0) is the masquerade tell.
            # Relative to the ID's quietest baseline window, so < 1 is already unusual.
            jitter_ratio = _safe_ratio(iat_std, max(baseline.jitter_floor.get(cid, 0.0), 1e-5))

            per_id[cid] = {
                "count": int(len(grp)),
                "rate": round(obs_rate, 2),
                "baseline_rate": round(base_rate, 2),
                "rate_ratio": round(ratio, 3) if np.isfinite(ratio) else None,
                "iat_mean_ms": round(iat_mean * 1000, 3),
                "iat_std_ms": round(iat_std * 1000, 3),
                "baseline_iat_ms": round(base_iat * 1000, 3),
                "iat_z": round(iat_z, 2),
                "jitter_ratio": round(jitter_ratio, 3) if np.isfinite(jitter_ratio) else None,
                "entropy": round(ent, 3),
                "baseline_entropy": round(baseline.entropy.get(cid, 0.0), 3),
                "entropy_delta": round(ent_delta, 3),
                "bitflip_rate": round(flip, 4),
                "bitflip_delta": round(flip_delta, 4),
                "known": cid in baseline.known_ids,
            }
            if cid in baseline.known_ids:
                if np.isfinite(ratio):
                    max_rate_ratio = max(max_rate_ratio, ratio)
                max_iat_z = max(max_iat_z, iat_z)
                max_entropy_delta = max(max_entropy_delta, ent_delta)
                max_flip_delta = max(max_flip_delta, flip_delta)

        rows.append({
            "window": len(rows),
            "start": round(float(w_start), 4),
            "end": round(float(w_end), 4),
            "n_msgs": n,
            "msg_rate": round(n / window_s, 2),
            "rate_ratio_total": round(_safe_ratio(n / window_s, baseline.total_rate), 3),
            "n_ids": len(ids_seen),
            "n_unknown_ids": len(unknown),
            "unknown_ids": unknown,
            "n_missing_ids": len(missing),
            "missing_ids": missing,
            "max_rate_ratio": round(max_rate_ratio, 3),
            "max_iat_z": round(max_iat_z, 2),
            "max_entropy_delta": round(max_entropy_delta, 3),
            "max_bitflip_delta": round(max_flip_delta, 4),
            "mean_entropy": round(byte_entropy(list(win["data"])), 3),
            "label": int(win["label"].max()) if "label" in win else 0,
            "attack_type": (win.loc[win["label"] == 1, "attack_type"].mode().iat[0]
                            if "label" in win and int(win["label"].max()) == 1
                            and not win.loc[win["label"] == 1, "attack_type"].empty
                            else "normal"),
            "per_id": per_id,
        })

    return pd.DataFrame(rows)


FEATURE_COLUMNS = [
    "rate_ratio_total", "n_unknown_ids", "n_missing_ids",
    "max_rate_ratio", "max_iat_z", "max_entropy_delta", "max_bitflip_delta",
]
