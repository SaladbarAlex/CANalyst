"""Turn a flagged window into a compact evidence packet.

The packet is what the LLM sees. Raw frames are never sent: a CAN log
holds thousands of frames per second, so the LLM gets measured
deviations plus a handful of sample frames. Every item carries an id
(E1, E2, ...) so an explanation can cite it and the dashboard can link
the claim back to the number behind it.

Scope. An alert merges adjacent flagged windows, so it can span many
seconds. Through the October 21 run the per-ID numbers in a packet came
from one 0.5 s window of the alert (for each ID, the window with its
highest rate ratio), while the packet presented them as describing the
alert: a flood alert holding 2,806 injected frames reported 176. With
scope="alert" (the default) every per-ID number is measured over the whole
alert span, the peak single-window ratio is kept under an explicit
*_peak_window key, and an E0 item carries the alert-level facts so they can
be cited. scope="window" keeps the earlier behavior, byte for byte, so the
effect of the change can be measured on the same alerts.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .detector import Alert
from .features import ALWAYS_PRESENT, JITTER_COLLAPSE, MIN_EXPECTED_FRAMES, Baseline
from .synth import ID_INFO
from .windowstats import Frames, _bitflip, _entropy

SCOPES = ("alert", "window")
SUPPRESSED_BELOW = 0.7   # a known ID under 70% of its baseline rate counts as suppressed


def frame_hex(data: list[int]) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _span_stats(seg: pd.DataFrame, span_s: float, baseline: Baseline) -> dict[int, dict]:
    """The per-ID detail of features.extract_windows, over an arbitrary span.

    Same definitions as the per-window detail, with the alert's duration in
    place of the window length, so a rate ratio means the same thing in
    both. Uses the array routines the cached benchmark path is tested with.
    """
    if seg.empty:
        return {}
    fr = Frames.from_df(seg)
    order = np.argsort(fr.cid, kind="stable")
    uniq, first, counts = np.unique(fr.cid[order], return_index=True, return_counts=True)
    out: dict[int, dict] = {}
    for cid, s0, c in zip(uniq.tolist(), first.tolist(), counts.tolist()):
        idx = order[s0:s0 + c]
        iats = np.diff(fr.ts[idx])
        block, dl = fr.payload[idx], fr.dlc[idx]
        obs_rate = c / span_s
        base_rate = baseline.rate.get(cid, 0.0)
        if base_rate > 0:
            ratio = c / max(base_rate * span_s, MIN_EXPECTED_FRAMES)
        else:
            ratio = float("inf")
        iat_mean = float(iats.mean()) if iats.size else 0.0
        iat_std = float(iats.std()) if iats.size else 0.0
        base_iat = baseline.iat_mean.get(cid, 0.0)
        base_iat_std = max(baseline.iat_std.get(cid, 0.0), 1e-5)
        iat_z = abs(iat_mean - base_iat) / base_iat_std if base_iat > 0 and iats.size else 0.0
        ent, flip = _entropy(block, dl), _bitflip(block, dl)
        jitter_ratio = iat_std / max(baseline.jitter_floor.get(cid, 0.0), 1e-5)
        out[int(cid)] = {
            "count": int(c),
            "rate": round(obs_rate, 2),
            "baseline_rate": round(base_rate, 2),
            # rate_ratio is the detector's ratio: counts against the expected
            # count, with the expected count floored at MIN_EXPECTED_FRAMES so
            # one extra frame of a slow ID is not a doubling. rate_ratio_plain
            # is observed rate over baseline rate, with no floor.
            "rate_ratio": round(ratio, 3) if np.isfinite(ratio) else None,
            "rate_ratio_plain": round(obs_rate / base_rate, 3) if base_rate > 0 else None,
            "expected_frames": round(base_rate * span_s, 2),
            "iat_mean_ms": round(iat_mean * 1000, 3),
            "iat_std_ms": round(iat_std * 1000, 3),
            "baseline_iat_ms": round(base_iat * 1000, 3),
            "iat_z": round(iat_z, 2),
            "jitter_ratio": round(jitter_ratio, 3) if np.isfinite(jitter_ratio) else None,
            "entropy": round(ent, 3) + 0.0,
            "baseline_entropy": round(baseline.entropy.get(cid, 0.0), 3) + 0.0,
            "entropy_delta": round(ent - baseline.entropy.get(cid, 0.0), 3) + 0.0,
            "bitflip_rate": round(flip, 4),
            "bitflip_delta": round(flip - baseline.bitflip.get(cid, 0.0), 4),
            "known": cid in baseline.known_ids,
        }
    return out


def _ratio_text(v: dict) -> str:
    """'2.0x' or, when the low-rate floor changed it, both ratios spelled out."""
    plain, det = v.get("rate_ratio_plain"), v.get("rate_ratio")
    if plain is None:
        return f"{det}x"
    if det is not None and abs(plain - det) > 0.05 * max(plain, det, 1e-9):
        return (f"{plain}x; about {v['expected_frames']} frames were expected in this span, "
                f"so the detector floors that at {MIN_EXPECTED_FRAMES:g} and scores it {det}x")
    return f"{plain}x"


def build_evidence(alert: Alert, df: pd.DataFrame, windows: pd.DataFrame,
                   baseline: Baseline, max_ids: int = 6, max_frames: int = 6,
                   scope: str = "alert") -> dict[str, Any]:
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}")
    if scope == "window":
        return _build_evidence_window(alert, df, windows, baseline, max_ids, max_frames)

    # Arbitration IDs do not identify the same signal across vehicles. The
    # generator's function names are only verified for generator output.
    id_info = ID_INFO if df.attrs.get("source") == "synthetic" else {}
    rows = windows[(windows["start"] >= alert.start - 1e-9) & (windows["end"] <= alert.end + 1e-9)]
    if rows.empty:
        rows = windows[windows["window"] == alert.window]
    seg = df[(df["timestamp"] >= alert.start) & (df["timestamp"] < alert.end)]
    span_s = max(float(alert.end - alert.start), 1e-9)

    merged = _span_stats(seg, span_s, baseline)
    # Peak single-window ratio: a short burst inside a long alert shows here
    # even when the span average hides it.
    for per_id in rows["per_id"]:
        for cid, v in per_id.items():
            if cid in merged and v["rate_ratio"] is not None:
                peak = merged[cid].get("rate_ratio_peak_window")
                if peak is None or v["rate_ratio"] > peak:
                    merged[cid]["rate_ratio_peak_window"] = v["rate_ratio"]

    def interest(cid: int) -> tuple:
        v = merged[cid]
        jitter_collapse = (v["count"] >= 8 and v["jitter_ratio"] is not None
                           and v["jitter_ratio"] < JITTER_COLLAPSE)
        peak = v.get("rate_ratio_peak_window") or v["rate_ratio"] or 1
        return (
            not v["known"],                     # unknown IDs first
            cid in alert.top_ids,               # then whatever the detector ranked
            jitter_collapse,                    # then the masquerade tell
            max(abs((v["rate_ratio"] or 1) - 1), abs(peak - 1)),   # then rate deviation
            abs(v["iat_z"]),
            abs(v["entropy_delta"]),
        )

    ranked = sorted(merged, key=interest, reverse=True)[:max_ids]

    items: list[dict] = []

    def add(kind: str, text: str, detail: dict) -> dict:
        item = {"id": f"E{len(items)}", "kind": kind, "text": text, "detail": detail}
        items.append(item)
        return item

    n_unknown = sum(1 for v in merged.values() if not v["known"])
    add("alert",
        f"The alert spans {alert.start:.2f}s to {alert.end:.2f}s ({span_s:.2f}s, "
        f"{len(rows)} flagged window(s) merged) and holds {len(seg)} frames from "
        f"{len(merged)} arbitration IDs, {n_unknown} of them absent from the baseline. "
        f"Detector score {alert.score:.2f}.",
        {"start": alert.start, "end": alert.end, "span_s": round(span_s, 3),
         "frames": int(len(seg)), "ids": len(merged), "unknown_ids": n_unknown,
         "windows": int(len(rows)), "score": alert.score, "components": alert.components})

    unknown_frames = sum(v["count"] for v in merged.values() if not v["known"])
    # Known IDs the baseline expects at a countable rate, and how many of them
    # ran well below it. A flood on a real bus shows here, not in the total.
    countable = [v for v in merged.values()
                 if v["known"] and v["expected_frames"] >= MIN_EXPECTED_FRAMES]
    starved = [v for v in countable if (v["rate_ratio_plain"] or 0) < SUPPRESSED_BELOW]
    span_rate = len(seg) / span_s
    peak_rate = float(rows["msg_rate"].max()) if len(rows) else span_rate
    add("bus_load",
        f"Over the whole alert the bus carried {span_rate:.0f} msg/s on average versus a "
        f"{baseline.total_rate:.0f} msg/s baseline "
        f"({span_rate / max(baseline.total_rate, 1e-6):.2f}x); its busiest 0.5s window "
        f"reached {peak_rate:.0f} msg/s "
        f"({peak_rate / max(baseline.total_rate, 1e-6):.2f}x).",
        {"observed": round(span_rate, 2), "baseline": round(baseline.total_rate, 2),
         "observed_peak_window": round(peak_rate, 2), "scope": "whole_alert"})
    add("traffic_mix",
        f"Frames from IDs absent from the baseline make up {unknown_frames} of the {len(seg)} "
        f"frames in the alert ({unknown_frames / max(len(seg), 1):.0%}). Of {len(countable)} "
        f"baseline IDs expected at a countable rate, {len(starved)} ran below "
        f"{SUPPRESSED_BELOW:.0%} of their baseline rate.",
        {"unknown_frames": int(unknown_frames), "frames": int(len(seg)),
         "unknown_share": round(unknown_frames / max(len(seg), 1), 4),
         "countable_ids": len(countable), "suppressed_ids": len(starved),
         "suppressed_below": SUPPRESSED_BELOW, "scope": "whole_alert"})

    for cid in ranked:
        v = merged[cid]
        info = id_info.get(cid, {})
        label = f"0x{cid:03X}"
        if v["known"]:
            peak = v.get("rate_ratio_peak_window")
            peak_txt = f"; detector ratio in its peak window {peak}x" if peak is not None else ""
            add("id_stats",
                f"{label} ({info.get('name', 'unknown function')}) over the whole alert: "
                f"{v['count']} frames, {v['rate']} msg/s versus {v['baseline_rate']} baseline "
                f"({_ratio_text(v)}{peak_txt}); mean gap {v['iat_mean_ms']} ms versus "
                f"{v['baseline_iat_ms']} ms ({v['iat_z']} sigma); entropy {v['entropy']} "
                f"versus {v['baseline_entropy']}.",
                {"can_id": label, "function": info.get("function"), "scope": "whole_alert", **v})
        else:
            add("unknown_id",
                f"{label} is not in the baseline ID set and sent {v['count']} frame(s) over "
                f"the whole alert ({v['rate']} msg/s) with payload entropy "
                f"{abs(v['entropy']):.3f} bits.",
                {"can_id": label, "scope": "whole_alert", **v})
    if n_unknown > sum(1 for c in ranked if not merged[c]["known"]):
        shown = sum(1 for c in ranked if not merged[c]["known"])
        add("unknown_summary",
            f"{n_unknown} arbitration IDs absent from the baseline appear in the alert "
            f"({unknown_frames} frames in total); {shown} are itemized above.",
            {"unknown_ids": n_unknown, "unknown_frames": int(unknown_frames),
             "itemized": shown, "scope": "whole_alert"})

    # IDs the baseline always shows that are absent from the entire alert,
    # not merely from its first window.
    missing = sorted(i for i in baseline.known_ids
                     if i not in merged
                     and baseline.rate.get(i, 0.0) * span_s >= MIN_EXPECTED_FRAMES
                     and baseline.presence.get(i, 1.0) >= ALWAYS_PRESENT)
    for cid in missing[:3]:
        info = id_info.get(int(cid), {})
        expected = baseline.rate.get(int(cid), 0.0) * span_s
        add("missing_id",
            f"0x{int(cid):03X} ({info.get('name', 'unknown')}) sent nothing during the "
            f"alert although the baseline expects about {expected:.0f} frames in that time.",
            {"can_id": f"0x{int(cid):03X}", "function": info.get("function"),
             "scope": "whole_alert", "expected_frames": round(expected, 1)})

    frames = _sample_frames(seg, ranked, max_frames)
    if frames:
        add("frames",
            f"{len(frames)} representative frame(s) out of the {len(seg)} in the alert.",
            {"frames": frames, "sampled_from": int(len(seg))})

    return {
        "alert_id": alert.alert_id,
        "scope": "alert",
        "window_start": alert.start,
        "window_end": alert.end,
        "duration_s": round(alert.end - alert.start, 3),
        "detector_score": alert.score,
        "detector_components": alert.components,
        "detector_reasons": alert.reasons,
        "frame_count": int(len(seg)),
        "items": items,
        "sample_frames": frames,
        "ids_involved": [f"0x{c:03X}" for c in ranked],
    }


def _sample_frames(seg: pd.DataFrame, ranked: list[int], max_frames: int) -> list[dict]:
    """Sample frames spread across the IDs that drew attention, rather than
    the first few frames of the span (which are usually one ID)."""
    picks: list[pd.DataFrame] = []
    focus_ids = ranked[:3] if ranked else []
    per = max(1, max_frames // max(1, len(focus_ids) or 1))
    for cid in focus_ids:
        picks.append(seg[seg["can_id"] == cid].head(per))
    sample = pd.concat(picks) if picks else seg.head(max_frames)
    if sample.empty:
        sample = seg.head(max_frames)
    sample = sample.sort_values("timestamp").head(max_frames)
    return [
        {
            "timestamp": round(float(r.timestamp), 6),
            "can_id": f"0x{int(r.can_id):03X}",
            "dlc": int(r.dlc),
            "payload": frame_hex(list(r.data)),
        }
        for r in sample.itertuples()
    ]


def _build_evidence_window(alert: Alert, df: pd.DataFrame, windows: pd.DataFrame,
                           baseline: Baseline, max_ids: int = 6,
                           max_frames: int = 6) -> dict[str, Any]:
    """The packet as built through October 21, kept unchanged for comparison.

    Per-ID numbers come from one window of the alert (the one with that
    ID's highest rate ratio) and missing IDs from the alert's first window.
    """
    id_info = ID_INFO if df.attrs.get("source") == "synthetic" else {}
    rows = windows[(windows["start"] >= alert.start - 1e-9) & (windows["end"] <= alert.end + 1e-9)]
    if rows.empty:
        rows = windows[windows["window"] == alert.window]

    # Merge per-ID detail across the windows this alert spans.
    merged: dict[int, dict] = {}
    for per_id in rows["per_id"]:
        for cid, v in per_id.items():
            cur = merged.get(cid)
            if cur is None or (v["rate_ratio"] or 0) > (cur["rate_ratio"] or 0):
                merged[cid] = dict(v)

    def interest(cid: int) -> tuple:
        v = merged[cid]
        jitter_collapse = (v["count"] >= 8 and v["jitter_ratio"] is not None
                           and v["jitter_ratio"] < JITTER_COLLAPSE)
        return (
            not v["known"],                     # unknown IDs first
            cid in alert.top_ids,               # then whatever the detector ranked
            jitter_collapse,                    # then the masquerade tell
            abs((v["rate_ratio"] or 1) - 1),    # then rate deviation
            abs(v["iat_z"]),
            abs(v["entropy_delta"]),
        )

    ranked = sorted(merged, key=interest, reverse=True)[:max_ids]

    items: list[dict] = []
    n = 0

    def add(kind: str, text: str, detail: dict) -> dict:
        nonlocal n
        n += 1
        item = {"id": f"E{n}", "kind": kind, "text": text, "detail": detail}
        items.append(item)
        return item

    total_rate = float(rows["msg_rate"].max())
    add("bus_load",
        f"Bus carried {total_rate:.0f} msg/s versus a {baseline.total_rate:.0f} msg/s baseline "
        f"({total_rate / max(baseline.total_rate, 1e-6):.2f}x).",
        {"observed": round(total_rate, 2), "baseline": round(baseline.total_rate, 2)})

    for cid in ranked:
        v = merged[cid]
        info = id_info.get(cid, {})
        label = f"0x{cid:03X}"
        if v["known"]:
            add("id_stats",
                f"{label} ({info.get('name', 'unknown function')}): {v['rate']} msg/s versus "
                f"{v['baseline_rate']} baseline ({v['rate_ratio']}x); mean gap "
                f"{v['iat_mean_ms']} ms versus {v['baseline_iat_ms']} ms ({v['iat_z']} sigma); "
                f"entropy {v['entropy']} versus {v['baseline_entropy']}.",
                {"can_id": label, "function": info.get("function"), **v})
        else:
            add("unknown_id",
                f"{label} is not in the baseline ID set and sent {v['count']} frame(s) "
                f"with payload entropy {abs(v['entropy']):.3f} bits.",
                {"can_id": label, **v})

    missing = list(rows.iloc[0]["missing_ids"]) if len(rows) else []
    for cid in missing[:3]:
        info = id_info.get(int(cid), {})
        add("missing_id",
            f"0x{int(cid):03X} ({info.get('name', 'unknown')}) stopped transmitting during "
            f"this window although the baseline expects it every "
            f"{info.get('period_ms', '?')} ms.",
            {"can_id": f"0x{int(cid):03X}", "function": info.get("function")})

    # Sample frames, spread across the IDs that drew attention rather than
    # taking the first few frames of the window (which are usually one ID).
    seg = df[(df["timestamp"] >= alert.start) & (df["timestamp"] < alert.end)]
    picks: list[pd.DataFrame] = []
    focus_ids = ranked[:3] if ranked else []
    per = max(1, max_frames // max(1, len(focus_ids) or 1))
    for cid in focus_ids:
        picks.append(seg[seg["can_id"] == cid].head(per))
    sample = pd.concat(picks) if picks else seg.head(max_frames)
    if sample.empty:
        sample = seg.head(max_frames)
    sample = sample.sort_values("timestamp").head(max_frames)
    frames = [
        {
            "timestamp": round(float(r.timestamp), 6),
            "can_id": f"0x{int(r.can_id):03X}",
            "dlc": int(r.dlc),
            "payload": frame_hex(list(r.data)),
        }
        for r in sample.itertuples()
    ]
    if frames:
        add("frames", f"{len(frames)} representative frame(s) from the window.",
            {"frames": frames})

    return {
        "alert_id": alert.alert_id,
        "scope": "window",
        "window_start": alert.start,
        "window_end": alert.end,
        "duration_s": round(alert.end - alert.start, 3),
        "detector_score": alert.score,
        "detector_components": alert.components,
        "detector_reasons": alert.reasons,
        "frame_count": int(len(seg)),
        "items": items,
        "sample_frames": frames,
        "ids_involved": [f"0x{c:03X}" for c in ranked],
    }
