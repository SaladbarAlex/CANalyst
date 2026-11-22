"""Measure every capture once and cache the result.

Run from the backend folder:
    python -m scripts.build_cache --dataset road
    python -m scripts.build_cache --dataset hcrl
    python -m scripts.build_cache --verify      # compare with the saved midterm scores

Each capture is loaded with the same loader the dashboard uses, measured
with windowstats.measure, and written to out/cache/<dataset>/<capture>.npz.
Everything downstream (the split benchmark, the baseline detectors, the
reference-coverage study) reads the cache, so the multi-gigabyte logs are
parsed exactly once.
"""
from __future__ import annotations

import argparse
import gc
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, datasets, loader, windowstats as ws  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
CACHE = BACKEND / "out" / "cache"
WINDOW_S = 0.5
STRIDE_S = 0.25


def cache_path(dataset: str, name: str) -> Path:
    return CACHE / dataset / f"{name}.npz"


def build_one(dataset: str, name: str, force: bool = False) -> dict:
    cap = next(c for c in datasets.catalog(dataset) if c.name == name)
    out = cache_path(dataset, name)
    if out.exists() and not force:
        return {"capture": name, "status": "cached"}
    t0 = time.perf_counter()
    if dataset == "hcrl" and cap.kind == "ambient":
        df = loader.load_carhacking_txt(str(cap.path), allow_truncated_tail=True)
    else:
        df = loader.load_auto(str(cap.path))
    info = {
        "name": name, "dataset": dataset, "kind": cap.kind, "role": cap.role,
        "attack_type": cap.attack_type, "family": cap.family,
        "source": str(cap.path.relative_to(BACKEND)) if cap.path.is_relative_to(BACKEND)
        else cap.path.name,
        "source_sha256": cache.sha256(cap.path),
        "frame_count": int(len(df)),
        "duration_s": float(df["timestamp"].max()),
        "unique_ids": int(df["can_id"].nunique()),
        "attack_labeled_frames": int(df["label"].sum()),
        "attack_intervals": df.attrs.get("attack_intervals", []),
        "window_s": WINDOW_S, "stride_s": STRIDE_S,
    }
    if "truncated_tail_line" in df.attrs:
        info["truncated_tail_line"] = df.attrs["truncated_tail_line"]
    reference: dict[str, ws.BaselineStats] = {}
    if cap.kind == "ambient":
        assert int(df["label"].sum()) == 0, f"{name}: ambient capture has attack labels"
        if dataset == "hcrl":
            lo, hi = datasets.HCRL_REFERENCE_S
            seg = df[(df["timestamp"] >= lo) & (df["timestamp"] < hi)]
            reference[f"{lo:g}-{hi:g}"] = ws.BaselineStats.from_df(seg, WINDOW_S, name)
        else:
            reference["all"] = ws.BaselineStats.from_df(df, WINDOW_S, name)
    win, ids = ws.measure(df, WINDOW_S, STRIDE_S)
    info["windows"] = int(len(win))
    info["seconds"] = round(time.perf_counter() - t0, 2)
    cache.save(out, cache.Measured(name, win, ids, info, reference))
    del df, win, ids
    gc.collect()
    return {"capture": name, "status": "built", "frames": info["frame_count"],
            "windows": info["windows"], "seconds": info["seconds"]}


def verify() -> bool:
    """Re-score cached captures and compare with the saved midterm windows."""
    ok = True
    saved = BACKEND / "out" / "midterm_2026-10-20"
    plans = [
        ("road", saved / "road", "ambient_dyno_drive_basic_short", "all",
         [c.name for c in datasets.catalog("road")
          if c.kind == "attack" and c.role != "excluded"]),
        ("hcrl", saved / "hcrl_full", "normal_run_data", "0-120",
         [c.name for c in datasets.catalog("hcrl") if c.kind == "attack"]),
    ]
    for dataset, folder, ref_name, ref_slice, names in plans:
        ref_file = cache_path(dataset, ref_name)
        if not ref_file.exists():
            print(f"{dataset}: reference not cached, skipping")
            continue
        baseline = cache.load(ref_file).reference[ref_slice].to_baseline()
        mismatched = 0
        windows = 0
        for name in names:
            path = cache_path(dataset, name)
            ref_csv = folder / f"{name}__attack_capture_windows.csv.gz"
            if not path.exists() or not ref_csv.exists():
                continue
            m = cache.load(path)
            wf, _ = ws.apply_baseline(m.win, m.ids, baseline, WINDOW_S)
            sc = ws.rule_scores(wf)
            want = pd.read_csv(ref_csv)
            same = (len(want) == len(sc)
                    and np.array_equal(want["flagged"].to_numpy(), sc["flagged"].to_numpy())
                    and np.allclose(want["score"].to_numpy(), sc["score"].to_numpy(), atol=1e-9)
                    and np.array_equal(want["label"].to_numpy(), sc["label"].to_numpy())
                    and all(np.allclose(want[c].to_numpy(), sc[c].to_numpy(), atol=1e-9)
                            for c in ws.COMPONENTS))
            windows += len(want)
            if not same:
                mismatched += 1
                ok = False
                print(f"  MISMATCH {dataset}/{name}")
        print(f"{dataset}: {len(names)} captures, {windows:,} windows re-scored, "
              f"{mismatched} mismatched against {folder.relative_to(BACKEND)}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=["road", "hcrl", "all"], default="all")
    ap.add_argument("--only", nargs="*", help="capture names to (re)build")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if args.verify:
        sys.exit(0 if verify() else 1)

    kinds = ["road", "hcrl"] if args.dataset == "all" else [args.dataset]
    jobs = []
    for dataset in kinds:
        for cap in datasets.catalog(dataset):
            if args.only and cap.name not in args.only:
                continue
            jobs.append((cap.path.stat().st_size, dataset, cap.name))
    jobs.sort(reverse=True)
    # The largest captures need several gigabytes while they are parsed, so
    # they run alone; the rest share the worker pool.
    big = [j for j in jobs if j[0] > 180e6]
    small = [j for j in jobs if j[0] <= 180e6]
    for _, dataset, name in big:
        print(build_one(dataset, name, args.force), flush=True)
    if args.workers <= 1:
        for _, dataset, name in small:
            print(build_one(dataset, name, args.force), flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(build_one, d, n, args.force) for _, d, n in small]
            for fut in as_completed(futures):
                print(fut.result(), flush=True)


if __name__ == "__main__":
    main()
