"""Turn a flagged window into a compact evidence packet.

The packet is what the LLM sees. Raw frames are never sent: a CAN log
holds thousands of frames per second, so the LLM gets measured
deviations plus a handful of sample frames. Every item carries an id
(E1, E2, ...) so an explanation can cite it and the dashboard can link
the claim back to the number behind it.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .detector import Alert
from .features import Baseline
from .synth import ID_INFO


def frame_hex(data: list[int]) -> str:
    return " ".join(f"{b:02X}" for b in data)


def build_evidence(alert: Alert, df: pd.DataFrame, windows: pd.DataFrame,
                   baseline: Baseline, max_ids: int = 6, max_frames: int = 6) -> dict[str, Any]:
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
                           and v["jitter_ratio"] < 0.35)
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
        info = ID_INFO.get(cid, {})
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
        info = ID_INFO.get(int(cid), {})
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
