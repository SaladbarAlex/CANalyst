"""Baseline-independent window statistics, measured once per capture.

`features.extract_windows` does two jobs at once: it measures every window
(slow, touches every frame) and compares it with a baseline (cheap). An
evaluation that separates tuning from testing has to re-score the same
windows many times, against different baselines, thresholds and detectors,
so the two jobs are split here:

    measure(df)                 -> raw per-window and per-(window, ID) numbers
    apply_baseline(raw, base)   -> the features extract_windows would produce
    rule_scores(feat)           -> the RuleDetector's components and score

`measure` reproduces the arithmetic of `extract_windows` operation for
operation, and `rule_scores` reproduces `RuleDetector.score_window`, so the
fast path gives the same flags as the reference path. The test suite pins
the two together on synthetic traffic; `scripts/build_cache.py --verify`
does the same against the saved midterm scores on real traffic.

`BaselineStats` holds the sufficient statistics of one attack-free capture.
Unlike a learned `Baseline`, several of them can be pooled, which is how a
reference is built from more than one normal recording.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .features import (ALWAYS_PRESENT, JITTER_COLLAPSE, MIN_EXPECTED_FRAMES,
                       Baseline)

_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.int64)

COMPONENTS = ["bus_load", "unknown_ids", "rate_inflation", "missing_ids", "timing",
              "payload_entropy"]


# --------------------------------------------------------------------------
# Frame arrays
# --------------------------------------------------------------------------

@dataclass
class Frames:
    """A capture as flat arrays; payloads are zero-padded to a fixed width."""

    ts: np.ndarray        # float64 seconds
    cid: np.ndarray       # int64 arbitration IDs
    dlc: np.ndarray       # int64 payload lengths (len of the data list)
    payload: np.ndarray   # uint8 [n, width]
    label: np.ndarray     # int64
    attack_type: np.ndarray  # object

    @classmethod
    def from_df(cls, df: pd.DataFrame) -> "Frames":
        n = len(df)
        data = df["data"].tolist()
        dlc = np.fromiter((len(p) for p in data), dtype=np.int64, count=n)
        width = int(dlc.max()) if n else 0
        if n and int(dlc.min()) == width:
            payload = np.array(data, dtype=np.uint8).reshape(n, width)
        else:
            payload = np.zeros((n, width), dtype=np.uint8)
            for i, p in enumerate(data):
                if p:
                    payload[i, :len(p)] = p
        label = (df["label"].to_numpy(dtype=np.int64) if "label" in df
                 else np.zeros(n, dtype=np.int64))
        atype = (df["attack_type"].to_numpy(dtype=object) if "attack_type" in df
                 else np.full(n, "normal", dtype=object))
        return cls(df["timestamp"].to_numpy(dtype=np.float64),
                   df["can_id"].to_numpy(dtype=np.int64), dlc, payload, label, atype)

    def keys(self) -> np.ndarray:
        """One integer per frame that is equal for equal payloads."""
        n, width = self.payload.shape
        if width == 0:
            return np.zeros(n, dtype=np.uint64)
        if width <= 8:
            padded = np.zeros((n, 8), dtype=np.uint8)
            padded[:, :width] = self.payload
            return padded.view(np.uint64).ravel()
        return np.fromiter((hash(r.tobytes()) & 0xFFFFFFFFFFFFFFFF for r in self.payload),
                           dtype=np.uint64, count=n)


def _entropy(block: np.ndarray, dlc: np.ndarray) -> float:
    """features.byte_entropy on a padded payload block."""
    if block.shape[0] == 0:
        return 0.0
    first = int(dlc[0])
    if (dlc == first).all():
        flat = block[:, :first].ravel()
    else:
        flat = block[np.arange(block.shape[1])[None, :] < dlc[:, None]]
    if flat.size == 0:
        return 0.0
    counts = np.bincount(flat, minlength=256).astype(float)
    p = counts[counts > 0] / flat.size
    return float(-(p * np.log2(p)).sum())


def _bitflip(block: np.ndarray, dlc: np.ndarray) -> float:
    """features.bitflip_rate on a padded payload block."""
    if block.shape[0] < 2:
        return 0.0
    width = int(dlc.max())
    if width == 0:
        return float("nan")   # the reference takes the mean of an empty array here
    xor = np.bitwise_xor(block[1:, :width], block[:-1, :width])
    return float(_POPCOUNT[xor].sum() / (xor.size * 8))


def _bitflip_counts(block: np.ndarray, dlc: np.ndarray) -> tuple[int, int]:
    """Numerator and denominator of the bit-flip rate, for pooling."""
    if block.shape[0] < 2:
        return 0, 0
    width = int(dlc.max())
    if width == 0:
        return 0, 0
    xor = np.bitwise_xor(block[1:, :width], block[:-1, :width])
    return int(_POPCOUNT[xor].sum()), int(xor.size * 8)


# --------------------------------------------------------------------------
# Measuring windows
# --------------------------------------------------------------------------

WIN_COLUMNS = ["window", "start", "end", "n_msgs", "label", "attack_type"]
ID_COLUMNS = ["window", "can_id", "count", "iat_mean", "iat_std", "entropy", "bitflip",
              "n_unique", "top_share", "attack_frames"]
BYTE_POSITIONS = 8
BMIN = [f"bmin{i}" for i in range(BYTE_POSITIONS)]
BMAX = [f"bmax{i}" for i in range(BYTE_POSITIONS)]


def _byte_range(block: np.ndarray, dlc: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per byte position, the lowest and highest value seen in a block.

    Positions no frame reaches keep the sentinels (255, 0), which no
    comparison against a reference range can trip.
    """
    lo = np.full(BYTE_POSITIONS, 255, dtype=np.uint8)
    hi = np.zeros(BYTE_POSITIONS, dtype=np.uint8)
    if block.shape[0] == 0:
        return lo, hi
    first = int(dlc[0])
    if (dlc == first).all():
        d = min(first, BYTE_POSITIONS)
        if d:
            lo[:d] = block[:, :d].min(axis=0)
            hi[:d] = block[:, :d].max(axis=0)
        return lo, hi
    for pos in range(min(block.shape[1], BYTE_POSITIONS)):
        col = block[dlc > pos, pos]
        if col.size:
            lo[pos], hi[pos] = col.min(), col.max()
    return lo, hi


def measure(df: pd.DataFrame, window_s: float = 0.5, stride_s: float = 0.25
            ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw statistics for every non-empty window and every ID inside it.

    Returns (win, ids). `win` has one row per window; `ids` has one row per
    (window, arbitration ID). Nothing here depends on a baseline.
    """
    fr = Frames.from_df(df)
    keys = fr.keys()
    n = len(fr.ts)
    if n == 0:
        return (pd.DataFrame(columns=WIN_COLUMNS),
                pd.DataFrame(columns=ID_COLUMNS + BMIN + BMAX))
    t_end = float(fr.ts.max())
    starts = np.arange(0.0, max(window_s, t_end - window_s + stride_s), stride_s)
    bounds = np.searchsorted(fr.ts, np.column_stack([starts, starts + window_s]))

    w_rows: list[tuple] = []
    cols: dict[str, list] = {c: [] for c in ID_COLUMNS}
    lows: list[np.ndarray] = []
    highs: list[np.ndarray] = []
    w = 0
    for w_start, (lo, hi) in zip(starts, bounds):
        if hi <= lo:
            continue
        ids_w = fr.cid[lo:hi]
        order = np.argsort(ids_w, kind="stable")
        uniq, first, counts = np.unique(ids_w[order], return_index=True, return_counts=True)
        lab_w = fr.label[lo:hi]
        has_attack = bool(lab_w.max() > 0)
        for cid, s, c in zip(uniq.tolist(), first.tolist(), counts.tolist()):
            idx = lo + order[s:s + c]
            iats = np.diff(fr.ts[idx])
            block, dl = fr.payload[idx], fr.dlc[idx]
            _, kc = np.unique(keys[idx], return_counts=True)
            cols["window"].append(w)
            cols["can_id"].append(cid)
            cols["count"].append(c)
            cols["iat_mean"].append(float(iats.mean()) if iats.size else 0.0)
            cols["iat_std"].append(float(iats.std()) if iats.size else 0.0)
            cols["entropy"].append(_entropy(block, dl))
            cols["bitflip"].append(_bitflip(block, dl))
            cols["n_unique"].append(int(kc.size))
            cols["top_share"].append(float(kc.max() / c))
            cols["attack_frames"].append(int(fr.label[idx].sum()) if has_attack else 0)
            b_lo, b_hi = _byte_range(block, dl)
            lows.append(b_lo)
            highs.append(b_hi)
        if has_attack:
            types, tcounts = np.unique(fr.attack_type[lo:hi][lab_w == 1].astype(str),
                                       return_counts=True)
            atype = str(types[np.argmax(tcounts)])   # ties: alphabetical, like Series.mode
        else:
            atype = "normal"
        w_rows.append((w, round(float(w_start), 4), round(float(w_start + window_s), 4),
                       int(hi - lo), int(has_attack), atype))
        w += 1

    win = pd.DataFrame(w_rows, columns=WIN_COLUMNS)
    ids = pd.DataFrame(cols, columns=ID_COLUMNS)
    lo_arr = np.vstack(lows) if lows else np.zeros((0, BYTE_POSITIONS), dtype=np.uint8)
    hi_arr = np.vstack(highs) if highs else np.zeros((0, BYTE_POSITIONS), dtype=np.uint8)
    for i in range(BYTE_POSITIONS):
        ids[BMIN[i]] = lo_arr[:, i]
        ids[BMAX[i]] = hi_arr[:, i]
    return win, ids


# --------------------------------------------------------------------------
# Poolable baseline statistics
# --------------------------------------------------------------------------

@dataclass
class BaselineStats:
    """Sufficient statistics of one attack-free capture (or several pooled)."""

    n: int = 0
    span: float = 0.0
    active_chunks: int = 0
    captures: list[str] = field(default_factory=list)
    # per ID: n, n_iat, sum_iat, sumsq_iat, chunks, floor (nan if no window
    # had enough frames), flips, flip_bits, hist (256 byte counts),
    # bmin / bmax (per byte position, lowest and highest value seen)
    per_id: dict[int, dict] = field(default_factory=dict)

    @classmethod
    def from_df(cls, df: pd.DataFrame, window_s: float = 0.5, name: str = "") -> "BaselineStats":
        fr = Frames.from_df(df)
        out = cls(n=len(fr.ts), captures=[name] if name else [])
        if out.n == 0:
            return out
        out.span = max(1e-6, float(fr.ts.max() - fr.ts.min()))
        chunk_all = (fr.ts // window_s).astype(np.int64)
        out.active_chunks = max(1, len(np.unique(chunk_all)))
        order = np.argsort(fr.cid, kind="stable")
        uniq, first, counts = np.unique(fr.cid[order], return_index=True, return_counts=True)
        for cid, s, c in zip(uniq.tolist(), first.tolist(), counts.tolist()):
            idx = order[s:s + c]
            ts = fr.ts[idx]
            iats = np.diff(ts)
            floor = float("nan")
            if iats.size >= 7:
                chunks = pd.Series(iats).groupby((ts[1:] // window_s).astype(np.int64))
                per_chunk = chunks.std(ddof=0)[chunks.count() >= 7]
                if not per_chunk.empty:
                    floor = float(per_chunk.min())
            block, dl = fr.payload[idx], fr.dlc[idx]
            flips, flip_bits = _bitflip_counts(block, dl)
            mask = np.arange(block.shape[1])[None, :] < dl[:, None]
            b_lo, b_hi = _byte_range(block, dl)
            out.per_id[int(cid)] = {
                "n": int(c),
                "n_iat": int(iats.size),
                "sum_iat": float(iats.sum()),
                "sumsq_iat": float(np.square(iats).sum()),
                "iat_mean": float(iats.mean()) if iats.size else 0.0,
                "iat_std": float(iats.std()) if iats.size else 0.0,
                "chunks": int(len(np.unique(chunk_all[idx]))),
                "floor": floor,
                "flips": flips,
                "flip_bits": flip_bits,
                "hist": np.bincount(block[mask], minlength=256).astype(np.int64),
                "bmin": b_lo,
                "bmax": b_hi,
            }
        return out

    @classmethod
    def pool(cls, parts: list["BaselineStats"]) -> "BaselineStats":
        """Combine captures as if their traffic were one longer recording.

        Counts, spans, byte histograms and bit-flip counts add exactly. The
        inter-arrival gap that would join two recordings is not counted.
        """
        if len(parts) == 1:
            return parts[0]
        out = cls()
        for p in parts:
            out.n += p.n
            out.span += p.span
            out.active_chunks += p.active_chunks
            out.captures += p.captures
            for cid, v in p.per_id.items():
                cur = out.per_id.get(cid)
                if cur is None:
                    out.per_id[cid] = {**v, "hist": v["hist"].copy(), "bmin": v["bmin"].copy(),
                                       "bmax": v["bmax"].copy(), "pooled": False}
                    continue
                for k in ("n", "n_iat", "sum_iat", "sumsq_iat", "chunks", "flips", "flip_bits"):
                    cur[k] += v[k]
                cur["hist"] += v["hist"]
                cur["bmin"] = np.minimum(cur["bmin"], v["bmin"])
                cur["bmax"] = np.maximum(cur["bmax"], v["bmax"])
                cur["floor"] = float(np.fmin(cur["floor"], v["floor"]))
                cur["pooled"] = True
        for v in out.per_id.values():
            if v.pop("pooled", False):
                m = v["sum_iat"] / v["n_iat"] if v["n_iat"] else 0.0
                var = v["sumsq_iat"] / v["n_iat"] - m * m if v["n_iat"] else 0.0
                v["iat_mean"], v["iat_std"] = m, float(np.sqrt(max(var, 0.0)))
        return out

    def to_baseline(self) -> Baseline:
        bl = Baseline(known_ids=set(self.per_id))
        bl.total_rate = self.n / self.span if self.span else 0.0
        for cid, v in self.per_id.items():
            bl.rate[cid] = v["n"] / self.span
            bl.iat_mean[cid] = v["iat_mean"]
            bl.iat_std[cid] = v["iat_std"]
            bl.jitter_floor[cid] = v["iat_std"] if np.isnan(v["floor"]) else v["floor"]
            bl.presence[cid] = v["chunks"] / max(1, self.active_chunks)
            total = int(v["hist"].sum())
            if total:
                p = v["hist"][v["hist"] > 0].astype(float) / total
                bl.entropy[cid] = float(-(p * np.log2(p)).sum())
            else:
                bl.entropy[cid] = 0.0
            bl.bitflip[cid] = v["flips"] / v["flip_bits"] if v["flip_bits"] else 0.0
        return bl


# --------------------------------------------------------------------------
# Applying a baseline and scoring
# --------------------------------------------------------------------------

def _pyround(values: np.ndarray, digits: int) -> np.ndarray:
    """Round like the reference path does (Python's round, not numpy's)."""
    return np.array([round(float(v), digits) for v in values], dtype=float)


def apply_baseline(win: pd.DataFrame, ids: pd.DataFrame, baseline: Baseline,
                   window_s: float = 0.5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The baseline-relative features of extract_windows, without the loops.

    Returns (wf, idf): `wf` adds the window-level feature columns to `win`;
    `idf` adds the per-ID comparison columns to `ids`.
    """
    cid = ids["can_id"].to_numpy()
    known_ids = np.fromiter(baseline.known_ids, dtype=np.int64,
                            count=len(baseline.known_ids))
    known = np.isin(cid, known_ids)

    def lookup(table: dict[int, float], default: float = 0.0) -> np.ndarray:
        return ids["can_id"].map(table).fillna(default).to_numpy(dtype=float)

    count = ids["count"].to_numpy(dtype=float)
    base_rate = lookup(baseline.rate)
    obs_rate = count / window_s
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(base_rate > 0,
                         count / np.maximum(base_rate * window_s, MIN_EXPECTED_FRAMES),
                         np.where(obs_rate > 0, np.inf, 1.0))
    base_iat = lookup(baseline.iat_mean)
    base_iat_std = np.maximum(lookup(baseline.iat_std), 1e-5)
    has_iat = ids["count"].to_numpy() >= 2
    iat_z = np.where((base_iat > 0) & has_iat,
                     np.abs(ids["iat_mean"].to_numpy() - base_iat) / base_iat_std, 0.0)
    ent_delta = ids["entropy"].to_numpy() - lookup(baseline.entropy)
    flip_delta = ids["bitflip"].to_numpy() - lookup(baseline.bitflip)
    jitter_floor = lookup(baseline.jitter_floor)
    jitter_std = ids["iat_std"].to_numpy()
    jitter_ratio = np.where(jitter_floor > 1e-5,
                            jitter_std / np.maximum(jitter_floor, 1e-5),
                            np.maximum(1.0, jitter_std / 1e-5))

    idf = ids.copy()
    idf["known"] = known
    idf["baseline_rate"] = base_rate
    idf["rate_ratio"] = ratio
    idf["iat_z"] = iat_z
    idf["entropy_delta"] = ent_delta
    idf["bitflip_delta"] = flip_delta
    idf["jitter_ratio"] = jitter_ratio

    # The detector's jitter test reads the rounded per-ID values.
    finite = np.isfinite(ratio)
    r_ratio = np.zeros(len(ids))
    r_ratio[finite] = _pyround(ratio[finite], 3)
    r_jitter = _pyround(jitter_ratio, 3)
    r_base_iat_ms = _pyround(base_iat * 1000, 3)
    idf["jitter_flag"] = (known & (ids["count"].to_numpy() >= 8) & (r_jitter < JITTER_COLLAPSE)
                          & (r_base_iat_ms > 0) & (r_ratio >= 0.8) & (r_ratio <= 1.25))

    n_win = len(win)
    widx = ids["window"].to_numpy()

    def wmax(values: np.ndarray, mask: np.ndarray, init: float) -> np.ndarray:
        out = np.full(n_win, init)
        ok = mask & ~np.isnan(values)
        np.maximum.at(out, widx[ok], values[ok])
        return out

    max_rate_ratio = wmax(ratio, known & finite, 1.0)
    max_iat_z = wmax(iat_z, known, 0.0)
    max_ent = wmax(ent_delta, known, 0.0)
    max_flip = wmax(flip_delta, known, 0.0)
    n_unknown = np.bincount(widx[~known], minlength=n_win)
    n_jitter = np.bincount(widx[idf["jitter_flag"].to_numpy()], minlength=n_win)
    any_jitter = n_jitter > 0

    # Missing: IDs the baseline always shows, at a countable rate, absent here.
    expected = np.array(sorted(
        i for i in baseline.known_ids
        if baseline.rate.get(i, 0) * window_s >= MIN_EXPECTED_FRAMES
        and baseline.presence.get(i, 1.0) >= ALWAYS_PRESENT), dtype=np.int64)
    seen_expected = np.bincount(widx[np.isin(cid, expected)], minlength=n_win)
    n_missing = len(expected) - seen_expected

    n_msgs = win["n_msgs"].to_numpy(dtype=float)
    total = baseline.total_rate
    with np.errstate(divide="ignore", invalid="ignore"):
        load = (n_msgs / window_s) / total if total > 1e-9 else np.where(n_msgs > 0, np.inf, 1.0)

    wf = win.copy()
    wf["rate_ratio_total"] = _pyround(load, 3)
    wf["n_ids"] = np.bincount(widx, minlength=n_win)
    wf["n_unknown_ids"] = n_unknown
    wf["n_missing_ids"] = n_missing
    wf["max_rate_ratio"] = _pyround(max_rate_ratio, 3)
    wf["max_iat_z"] = _pyround(max_iat_z, 2)
    wf["max_entropy_delta"] = _pyround(max_ent, 3)
    wf["max_bitflip_delta"] = _pyround(max_flip, 4)
    wf["jitter_collapse"] = any_jitter
    wf["n_jitter_collapses"] = n_jitter
    return wf, idf


def rule_scores(wf: pd.DataFrame, threshold: float = 0.55,
                alert_components: tuple[str, ...] | list[str] | None = None) -> pd.DataFrame:
    """RuleDetector.score_window for every row of `wf` at once.

    `alert_components` names the components that count toward the score
    (detector.ALERT_PROFILES); the default is all six.
    """
    clip = lambda x: np.clip(x, 0.0, 1.0)
    comp = pd.DataFrame(index=wf.index)
    comp["bus_load"] = clip((wf["rate_ratio_total"].to_numpy() - 1.25) / 1.75)
    n_unknown = wf["n_unknown_ids"].to_numpy()
    comp["unknown_ids"] = np.where(n_unknown > 0, np.maximum(clip(n_unknown / 8.0), 0.6), 0.0)
    comp["rate_inflation"] = clip((wf["max_rate_ratio"].to_numpy() - 1.35) / 1.15)
    comp["missing_ids"] = clip(wf["n_missing_ids"].to_numpy() / 3.0)
    timing = np.minimum(0.45, clip((wf["max_iat_z"].to_numpy() - 3.0) / 9.0))
    comp["timing"] = np.where(wf["jitter_collapse"].to_numpy(), np.maximum(timing, 0.6), timing)
    comp["payload_entropy"] = clip(wf["max_entropy_delta"].to_numpy() / 2.5)
    out = wf.copy()
    raw = comp[list(alert_components or COMPONENTS)].to_numpy().max(axis=1)
    for c in COMPONENTS:
        out[c] = _pyround(comp[c].to_numpy(), 3)
    out["score"] = raw
    out["flagged"] = raw >= threshold
    return out


def alert_spans(win: pd.DataFrame, flagged: np.ndarray, gap_s: float = 0.26
                ) -> list[tuple[float, float]]:
    """Merge consecutive flagged windows the way detector.merge_adjacent does."""
    spans: list[tuple[float, float]] = []
    starts = win["start"].to_numpy()[flagged]
    ends = win["end"].to_numpy()[flagged]
    for s, e in zip(starts, ends):
        if spans and s - spans[-1][1] <= gap_s:
            spans[-1] = (spans[-1][0], max(spans[-1][1], float(e)))
        else:
            spans.append((float(s), float(e)))
    return spans
