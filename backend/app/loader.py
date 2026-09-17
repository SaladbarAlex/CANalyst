"""Loaders that normalize CAN logs into one internal format.

Internal format (a pandas DataFrame):
    timestamp    float seconds, monotonically increasing, starting near 0
    can_id       int arbitration ID
    dlc          int payload length
    data         list[int] payload bytes
    label        int 1 = attack frame, 0 = normal (0 everywhere if unlabeled)
    attack_type  str ground-truth attack name, or "normal"/"unknown"
"""
from __future__ import annotations

import io

import pandas as pd

from . import synth


def _norm_bytes(row_bytes: list) -> list[int]:
    out = []
    for b in row_bytes:
        if b is None or (isinstance(b, float) and pd.isna(b)) or b == "":
            continue
        out.append(int(str(b), 16) if isinstance(b, str) else int(b))
    return out


def load_carhacking(csv: str | io.StringIO, has_header: bool = True) -> pd.DataFrame:
    """Load an HCRL Car-Hacking style CSV.

    Columns: Timestamp, CAN ID, DLC, DATA[0..7], Flag ('T' = injected).
    The published attack files have no header row, so pass has_header=False.
    """
    names = ["Timestamp", "CAN ID", "DLC"] + [f"DATA[{i}]" for i in range(8)] + ["Flag"]
    if has_header:
        raw = pd.read_csv(csv, dtype=str)
        raw.columns = [c.strip() for c in raw.columns]
    else:
        raw = pd.read_csv(csv, header=None, names=names, dtype=str)

    data_cols = [c for c in raw.columns if c.upper().startswith("DATA")]
    flag_col = next((c for c in raw.columns if c.lower() == "flag"), None)

    ts = raw["Timestamp"].astype(float)
    df = pd.DataFrame({
        "timestamp": ts - ts.min(),
        "can_id": raw["CAN ID"].apply(lambda v: int(str(v).strip(), 16)),
        "dlc": raw["DLC"].astype(float).astype(int),
        "data": raw[data_cols].apply(lambda r: _norm_bytes(list(r)), axis=1),
    })
    if flag_col is not None:
        df["label"] = (raw[flag_col].astype(str).str.upper().str.strip() == "T").astype(int)
        df["attack_type"] = ["injected" if x else "normal" for x in df["label"]]
    else:
        df["label"] = 0
        df["attack_type"] = "unknown"
    df.attrs["source"] = "car-hacking"
    return df.sort_values("timestamp").reset_index(drop=True)


def load_road(csv: str | io.StringIO) -> pd.DataFrame:
    """Load an ORNL ROAD style CSV (Label, Time, ID, Signal columns or raw hex).

    ROAD ships several layouts. This handles the common
    'Label,Time,ID,Data' shape and falls back to positional parsing.
    """
    raw = pd.read_csv(csv, dtype=str)
    cols = {c.lower().strip(): c for c in raw.columns}
    time_col = cols.get("time") or cols.get("timestamp")
    id_col = cols.get("id") or cols.get("can id")
    data_col = cols.get("data") or cols.get("payload")
    label_col = cols.get("label")
    if not (time_col and id_col and data_col):
        raise ValueError(f"Unrecognized ROAD layout: {list(raw.columns)}")

    ts = raw[time_col].astype(float)
    payloads = raw[data_col].astype(str).str.replace(" ", "").str.strip()
    data = payloads.apply(lambda h: [int(h[i:i + 2], 16) for i in range(0, len(h) - 1, 2)])
    df = pd.DataFrame({
        "timestamp": ts - ts.min(),
        "can_id": raw[id_col].apply(lambda v: int(str(v).strip(), 16)),
        "dlc": data.apply(len),
        "data": data,
    })
    if label_col:
        df["label"] = raw[label_col].astype(str).str.lower().isin(["1", "true", "attack"]).astype(int)
        df["attack_type"] = ["injected" if x else "normal" for x in df["label"]]
    else:
        df["label"] = 0
        df["attack_type"] = "unknown"
    df.attrs["source"] = "road"
    return df.sort_values("timestamp").reset_index(drop=True)


def load_synthetic(duration_s: float = 120.0, seed: int = 7,
                   attacks: list[str] | None = None) -> pd.DataFrame:
    return synth.generate(duration_s=duration_s, seed=seed, attacks=attacks)


def load_auto(path: str) -> pd.DataFrame:
    """Guess the format from the header line."""
    with open(path, "r", errors="replace") as fh:
        head = fh.readline()
    low = head.lower()
    if "label" in low and ("time" in low or "timestamp" in low) and "data" in low:
        return load_road(path)
    if "can id" in low or "timestamp" in low:
        return load_carhacking(path, has_header=True)
    return load_carhacking(path, has_header=False)
