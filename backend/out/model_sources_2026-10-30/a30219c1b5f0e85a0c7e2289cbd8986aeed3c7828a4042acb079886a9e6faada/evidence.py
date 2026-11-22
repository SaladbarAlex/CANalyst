"""Turn a flagged window into a compact evidence packet.

The packet is what the LLM sees. Raw frames are never sent: a CAN log
holds thousands of frames per second, so the LLM gets measured
deviations plus a handful of sample frames. Every item carries an id
(E1, E2, ...) so an explanation can cite it and the dashboard can link
the claim back to the number behind it. E0 is the alert itself: its
window, frame count and detector score, which models restate often and
would otherwise have nothing to cite. It is numbered 0 so E1 onward keep
the ids earlier runs cited.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .detector import Alert
from .features import JITTER_COLLAPSE, MIN_EXPECTED_FRAMES, Baseline, byte_entropy
from .synth import ID_INFO


def frame_hex(data: list[int]) -> str:
    return " ".join(f"{b:02X}" for b in data)


def build_evidence(alert: Alert, df: pd.DataFrame, windows: pd.DataFrame,
                   baseline: Baseline, max_ids: int = 6, max_frames: int = 6) -> dict[str, Any]:
    # Arbitration IDs do not identify the same signal across vehicles. The
    # generator's function names are only verified for generator output.
    id_info = ID_INFO if df.attrs.get("source") == "synthetic" else {}
    rows = windows[(windows["start"] >= alert.start - 1e-9) & (windows["end"] <= alert.end + 1e-9)]
    if rows.empty:
        rows = windows[windows["window"] == alert.window]

    seg = df[(df["timestamp"] >= alert.start) & (df["timestamp"] < alert.end)]
    alert_counts = seg["can_id"].value_counts()
    duration = max(alert.end - alert.start, 1e-9)
    # Keep peak-window statistics explicitly scoped; overlapping windows must
    # never be summed to obtain frame counts for the merged alert.
    # Merge per-ID detail across the windows this alert spans.
    merged: dict[int, dict] = {}
    for row in rows.itertuples():
        for cid, v in row.per_id.items():
            cur = merged.get(cid)
            if cur is None or (v["rate_ratio"] or 0) > (cur["rate_ratio"] or 0):
                merged[cid] = {**v, "statistics_start": float(row.start),
                               "statistics_end": float(row.end)}

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
        f"Peak scored-window bus rate was {total_rate:.0f} msg/s versus a {baseline.total_rate:.0f} msg/s baseline "
        f"({total_rate / max(baseline.total_rate, 1e-6):.2f}x).",
        {"observed": round(total_rate, 2), "baseline": round(baseline.total_rate, 2)})

    for cid in ranked:
        v = dict(merged[cid])
        v["window_count"] = v["count"]
        v["alert_count"] = int(alert_counts.get(cid, 0))
        v["alert_mean_rate"] = round(v["alert_count"] / duration, 3)
        scope = f"In [{v['statistics_start']:.2f}, {v['statistics_end']:.2f})s, "
        info = id_info.get(cid, {})
        label = f"0x{cid:03X}"
        if v["known"]:
            # Feature rate_ratio guards rare IDs with a minimum expected count;
            # it is a detector score input, not observed_rate / baseline_rate.
            v["detector_rate_ratio"] = v["rate_ratio"]
            actual_baseline_rate = float(baseline.rate.get(cid, 0))
            v["baseline_rate"] = round(actual_baseline_rate, 6)
            v["rate_ratio"] = round(v["rate"] / actual_baseline_rate, 3) if actual_baseline_rate > 0 else None
            v["detector_rate_reference"] = round(max(actual_baseline_rate,
                MIN_EXPECTED_FRAMES / (v["statistics_end"] - v["statistics_start"])), 6)
            v["iat_available"] = v["window_count"] >= 2
            v["jitter_eligible"] = v["window_count"] >= 8
            if not v["iat_available"]:
                for key in ("iat_mean_ms", "iat_std_ms", "iat_z", "jitter_ratio"):
                    v[key] = None
            gap = (f"mean gap {v['iat_mean_ms']} ms versus {v['baseline_iat_ms']} ms "
                   f"({v['iat_z']} sigma); jitter ratio {v['jitter_ratio']} versus the quietest baseline window"
                   if v["iat_available"] else "gap and jitter unavailable: fewer than two frames in the statistics window")
            add("id_stats",
                scope + f"{label} ({info.get('name', 'unknown function')}): {v['rate']} msg/s versus "
                f"{v['baseline_rate']} baseline (raw observed/baseline {v['rate_ratio']}x). "
                f"Detector rate ratio {v['detector_rate_ratio']}x uses a guarded reference "
                f"of {v['detector_rate_reference']} msg/s for sparse IDs. "
                f"{gap}; entropy {v['entropy']} versus {v['baseline_entropy']}. "
                f"Statistics use {v['window_count']} frames; jitter needs at least eight. "
                f"Full alert count: {v['alert_count']} frames.",
                {"can_id": label, "function": info.get("function"), **v})
        else:
            v["count"] = v["alert_count"]
            v["count_scope"] = "full_alert"
            v["alert_entropy"] = round(byte_entropy(list(seg.loc[seg["can_id"] == cid, "data"])), 3)
            add("unknown_id",
                f"{label} is not in the baseline ID set and sent {v['count']} frame(s) "
                f"across the full alert ({v['alert_mean_rate']:.3f} msg/s), "
                f"with full-alert payload entropy {v['alert_entropy']:.3f} bits.",
                {"can_id": label, **v})

    missing = sorted({int(cid) for ids in rows["missing_ids"] for cid in ids})
    for cid in missing[:3]:
        info = id_info.get(int(cid), {})
        absent = rows[rows["missing_ids"].map(lambda ids: cid in ids)]
        first = absent.iloc[0]
        add("missing_id",
            f"0x{int(cid):03X} ({info.get('name', 'unknown')}) was absent in "
            f"{len(absent)} of {len(rows)} scored windows, including "
            f"[{first['start']:.2f}, {first['end']:.2f})s; baseline mean gap "
            f"{baseline.iat_mean.get(cid, 0) * 1000:.3f} ms.",
            {"can_id": f"0x{int(cid):03X}", "function": info.get("function"),
             "missing_windows": len(absent), "scored_windows": len(rows),
             "example_start": float(first["start"]), "example_end": float(first["end"])})

    # Sample frames, spread across the IDs that drew attention rather than
    # taking the first few frames of the window (which are usually one ID).
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
        add("frames", f"{len(frames)} sampled frame(s) from this alert only; no earlier reference sequence is supplied.",
            {"frames": frames})

    components = ", ".join(f"{k} {v:.3f}" for k, v in
                           sorted(alert.components.items(), key=lambda kv: -kv[1]))
    items.insert(0, {
        "id": "E0", "kind": "alert_window",
        "text": (f"Alert window {alert.start:.2f}s to {alert.end:.2f}s "
                 f"({alert.end - alert.start:.2f} s), {len(seg)} frames. Detector score "
                 f"{alert.score:.3f}; components: {components}."),
        "detail": {"window_start": alert.start, "window_end": alert.end,
                   "duration_s": round(alert.end - alert.start, 3), "frame_count": int(len(seg)),
                   "detector_score": alert.score, "components": alert.components},
    })

    return {
        "schema_version": "evidence-v3",
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
