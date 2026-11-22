"""On-disk cache of measured captures.

Measuring a capture (windowstats.measure) is the slow step, so each
capture is measured once and saved as a compressed .npz next to the
statistics needed to use it as a reference. The cache is derived data: it
is ignored by git and rebuilt by `python -m scripts.build_cache`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .windowstats import BaselineStats

CACHE_VERSION = 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class Measured:
    name: str
    win: pd.DataFrame
    ids: pd.DataFrame
    info: dict
    reference: dict[str, BaselineStats]   # keyed by slice label, e.g. "all" or "0-120"


def _pack_stats(prefix: str, st: BaselineStats, out: dict) -> None:
    cids = np.array(sorted(st.per_id), dtype=np.int64)
    out[f"{prefix}__cids"] = cids
    out[f"{prefix}__scalar"] = np.array([st.n, st.span, st.active_chunks], dtype=float)
    keys = ["n", "n_iat", "sum_iat", "sumsq_iat", "iat_mean", "iat_std", "chunks", "floor",
            "flips", "flip_bits"]
    out[f"{prefix}__num"] = np.array([[st.per_id[c][k] for k in keys] for c in cids],
                                     dtype=float).reshape(len(cids), len(keys))
    for k in ("hist", "bmin", "bmax"):
        width = {"hist": 256}.get(k, 8)
        out[f"{prefix}__{k}"] = (np.vstack([st.per_id[c][k] for c in cids]) if len(cids)
                                 else np.zeros((0, width)))


def _unpack_stats(prefix: str, z, name: str) -> BaselineStats:
    n, span, chunks = z[f"{prefix}__scalar"]
    st = BaselineStats(n=int(n), span=float(span), active_chunks=int(chunks), captures=[name])
    keys = ["n", "n_iat", "sum_iat", "sumsq_iat", "iat_mean", "iat_std", "chunks", "floor",
            "flips", "flip_bits"]
    ints = {"n", "n_iat", "chunks", "flips", "flip_bits"}
    num, hist = z[f"{prefix}__num"], z[f"{prefix}__hist"]
    bmin, bmax = z[f"{prefix}__bmin"], z[f"{prefix}__bmax"]
    for i, cid in enumerate(z[f"{prefix}__cids"].tolist()):
        row = {k: (int(num[i, j]) if k in ints else float(num[i, j])) for j, k in enumerate(keys)}
        row["hist"] = hist[i].astype(np.int64)
        row["bmin"] = bmin[i].astype(np.uint8)
        row["bmax"] = bmax[i].astype(np.uint8)
        st.per_id[int(cid)] = row
    return st


def save(path: Path, m: Measured) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    for col in m.win.columns:
        arrays[f"win__{col}"] = m.win[col].to_numpy(dtype=str if col == "attack_type" else None)
    for col in m.ids.columns:
        arrays[f"ids__{col}"] = m.ids[col].to_numpy()
    for label, st in m.reference.items():
        _pack_stats(f"ref__{label}", st, arrays)
    arrays["info"] = np.array(json.dumps({**m.info, "cache_version": CACHE_VERSION,
                                          "reference_slices": sorted(m.reference)}))
    np.savez_compressed(path, **arrays)


def load(path: Path) -> Measured:
    with np.load(path, allow_pickle=False) as z:
        info = json.loads(str(z["info"]))
        win = pd.DataFrame({k[5:]: z[k] for k in z.files if k.startswith("win__")})
        ids = pd.DataFrame({k[5:]: z[k] for k in z.files if k.startswith("ids__")})
        name = info.get("name", path.stem)
        reference = {label: _unpack_stats(f"ref__{label}", z, f"{name}[{label}]")
                     for label in info.get("reference_slices", [])}
    win["attack_type"] = win["attack_type"].astype(str)
    return Measured(name=name, win=win, ids=ids, info=info, reference=reference)
