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
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import synth


def _norm_bytes(row_bytes: list) -> list[int]:
    out = []
    for b in row_bytes:
        if b is None or (isinstance(b, float) and pd.isna(b)) or b == "":
            continue
        out.append(int(str(b), 16) if isinstance(b, str) else int(b))
    return out


def load_carhacking(csv: str | io.StringIO, has_header: bool = True,
                    attack_type: str = "injected") -> pd.DataFrame:
    """Load an HCRL Car-Hacking style CSV.

    Columns: Timestamp, CAN ID, DLC, DATA[0..7], Flag ('T' = injected).
    The published attack files have no header row, so pass has_header=False.
    In those files a frame with DLC < 8 has fewer columns, so the flag sits
    right after the last data byte rather than in a fixed column.
    """
    if not has_header:
        return _load_carhacking_ragged(csv, attack_type)

    raw = pd.read_csv(csv, dtype=str)
    raw.columns = [c.strip() for c in raw.columns]
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
        df["attack_type"] = [attack_type if x else "normal" for x in df["label"]]
    else:
        df["label"] = 0
        df["attack_type"] = "unknown"
    df.attrs["source"] = "car-hacking"
    return df.sort_values("timestamp").reset_index(drop=True)


def _load_carhacking_ragged(csv: str | io.StringIO, attack_type: str) -> pd.DataFrame:
    raw = pd.read_csv(csv, header=None, names=range(12), dtype=str)
    vals = raw.to_numpy()
    dlc = raw[2].astype(int).to_numpy()
    flag = vals[np.arange(len(vals)), 3 + dlc]
    has_flag = pd.notna(flag).any()
    ts = raw[0].astype(float)
    df = pd.DataFrame({
        "timestamp": ts - ts.min(),
        "can_id": [int(v, 16) for v in raw[1]],
        "dlc": dlc,
        "data": [[int(b, 16) for b in row[3:3 + n]] for row, n in zip(vals, dlc)],
    })
    if has_flag:
        df["label"] = (pd.Series(flag).astype(str).str.upper().str.strip() == "T").astype(int)
        df["attack_type"] = np.where(df["label"] == 1, attack_type, "normal")
    else:
        df["label"] = 0
        df["attack_type"] = "unknown"
    df.attrs["source"] = "car-hacking"
    return df.sort_values("timestamp", kind="stable").reset_index(drop=True)


_CH_TXT = re.compile(
    r"Timestamp:\s*([\d.]+)\s+ID:\s*([0-9A-Fa-f]+)\s+\S+\s+DLC:\s*(\d+)\s*([0-9A-Fa-f ]*)")


def load_carhacking_txt(path: str) -> pd.DataFrame:
    """Load the Car-Hacking attack-free capture (normal_run_data.txt).

    Lines look like:
        Timestamp: 1479121434.850202  ID: 0350  000  DLC: 8  05 28 84 66 6d 00 00 a2
    """
    with open(path, "r", errors="replace") as fh:
        lines = pd.Series(fh.read().splitlines())
    m = lines.str.extract(_CH_TXT).dropna(subset=[0])
    ts = m[0].astype(float)
    df = pd.DataFrame({
        "timestamp": (ts - ts.min()).to_numpy(),
        "can_id": [int(v, 16) for v in m[1]],
        "dlc": m[2].astype(int).to_numpy(),
        "data": [[int(b, 16) for b in s.split()] for s in m[3]],
        "label": 0,
        "attack_type": "normal",
    })
    df.attrs["source"] = "car-hacking"
    return df.sort_values("timestamp", kind="stable").reset_index(drop=True)


_CANDUMP = re.compile(r"\(([\d.]+)\)\s+\S+\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]*)")


def road_attack_type(capture: str) -> str:
    """Map a ROAD capture name onto the explainer's attack vocabulary."""
    if capture.startswith("fuzzing"):
        return "fuzzing"
    if capture.endswith("_masquerade"):
        return "masquerade"
    return "spoofing"


def load_candump(path: str, meta: dict | None = None,
                 attack_type: str = "injected") -> pd.DataFrame:
    """Load a candump log, as shipped in ORNL ROAD (`(ts) can0 ID#HEX`).

    `meta` is the capture's entry from ROAD's capture_metadata.json. When it
    has an injection_interval, frames inside it from the injected ID (or any
    ID, for fuzzing, where injection_id is 'XXX') are labeled as attack.
    """
    with open(path, "r", errors="replace") as fh:
        lines = pd.Series(fh.read().splitlines())
    m = lines.str.extract(_CANDUMP).dropna(subset=[0])
    ts = m[0].astype(float).to_numpy()
    payloads = m[2].tolist()
    df = pd.DataFrame({
        "timestamp": ts - ts.min(),
        "can_id": [int(v, 16) for v in m[1]],
        "data": [list(bytes.fromhex(h)) for h in payloads],
    })
    df["dlc"] = df["data"].apply(len)
    df["label"] = 0
    df["attack_type"] = "normal"

    interval = (meta or {}).get("injection_interval")
    if interval:
        lo, hi = interval
        in_iv = (df["timestamp"] >= lo) & (df["timestamp"] <= hi)
        inj = (meta or {}).get("injection_id")
        if inj and inj.upper() != "XXX":
            in_iv &= df["can_id"] == int(inj, 16)
        df.loc[in_iv, "label"] = 1
        df.loc[in_iv, "attack_type"] = attack_type
        attrs = {"attack_intervals": [{"start": lo, "end": hi, "type": attack_type}]}
    else:
        attrs = {}
        if meta is None:
            df["attack_type"] = "unknown"
    df = df[["timestamp", "can_id", "dlc", "data", "label", "attack_type"]]
    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    df.attrs.update(attrs, source="road")
    return df


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


def concat_captures(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """Join several attack-free captures end to end into one baseline log.

    Each capture is shifted to start just after the previous one ends, so
    rates are not diluted by the time between recordings.
    """
    parts, offset = [], 0.0
    for d in dfs:
        part = d.copy()
        part["timestamp"] = part["timestamp"] - part["timestamp"].min() + offset
        offset = float(part["timestamp"].max()) + 0.01
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    out.attrs["source"] = dfs[0].attrs.get("source", "unknown") if dfs else "unknown"
    return out


def load_synthetic(duration_s: float = 120.0, seed: int = 7,
                   attacks: list[str] | None = None) -> pd.DataFrame:
    return synth.generate(duration_s=duration_s, seed=seed, attacks=attacks)


_CH_ATTACK_TYPES = {"dos": "dos", "fuzzy": "fuzzing", "gear": "spoofing", "rpm": "spoofing"}


def load_auto(path: str) -> pd.DataFrame:
    """Guess the format from the first line.

    Known dataset file names also set the ground-truth attack type: the
    Car-Hacking files (DoS_dataset.csv, ...) and ROAD .log captures, whose
    labels come from capture_metadata.json in the same folder.
    """
    with open(path, "r", errors="replace") as fh:
        head = fh.readline()
    low = head.lower()
    p = Path(path)
    if head.startswith("("):
        meta_path = p.parent / "capture_metadata.json"
        meta = None
        if meta_path.exists():
            meta = json.loads(meta_path.read_text()).get(p.stem)
        return load_candump(path, meta=meta, attack_type=road_attack_type(p.stem))
    if low.startswith("timestamp:"):
        return load_carhacking_txt(path)
    if "label" in low and ("time" in low or "timestamp" in low) and "data" in low:
        return load_road(path)
    atype = _CH_ATTACK_TYPES.get(p.stem.split("_")[0].lower(), "injected")
    if "can id" in low or "timestamp" in low:
        return load_carhacking(path, has_header=True, attack_type=atype)
    return load_carhacking(path, has_header=False, attack_type=atype)
