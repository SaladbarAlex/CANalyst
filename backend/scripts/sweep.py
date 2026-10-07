"""Threshold sweep for the rule detector on real logs.

Scoring a multi-gigabyte log is the slow part and does not depend on the
threshold, so each log is scored once and its per-window scores are cached
as CSV. The sweep then re-thresholds the cached scores.

The baseline is learned from separate attack-free captures (--baseline),
because the public attack logs inject from their first seconds and have no
clean prefix to learn from. Pass attack-free captures that are not in the
baseline as --logs too: they measure false positives on unseen driving.

Examples (from the backend folder):
    python -m scripts.sweep --group carhacking \
        --baseline "data/9) Car-Hacking Dataset/normal_run_data/normal_run_data.txt" \
        --logs "data/9) Car-Hacking Dataset/DoS_dataset.csv" --cache out/sweep
    python -m scripts.sweep --cache out/sweep --report          # sweep everything cached
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import loader, pipeline  # noqa: E402

COMPONENTS = ["bus_load", "unknown_ids", "rate_inflation", "missing_ids", "timing",
              "payload_entropy"]
DEFAULT_THRESHOLDS = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9]


def score_log(log: str, baseline_df: pd.DataFrame | None, cache: Path, group: str) -> Path:
    out = cache / f"{group}__{Path(log).stem}.csv.gz"
    if out.exists():
        print(f"cached  {out.name}")
        return out
    t0 = time.time()
    df = loader.load_auto(log)
    a = pipeline.run_analysis(df, source=log, params={"log": log},
                              baseline_df=baseline_df, threshold=1.0)
    w = a.windows
    rows = pd.DataFrame({
        "start": w["start"], "end": w["end"], "label": w["label"],
        "attack_type": w["attack_type"], "score": w["score"],
    })
    for c in COMPONENTS:
        rows[c] = [comp.get(c, 0.0) for comp in w["components"]]
    rows = rows[rows["end"] > a.baseline_end]
    rows.to_csv(out, index=False)
    print(f"scored  {out.name}: {len(df):,} frames, {len(rows):,} windows, "
          f"{int(rows['label'].sum()):,} attack windows, {time.time() - t0:.0f}s")
    return out


def metrics_at(w: pd.DataFrame, t: float) -> dict:
    flagged = w["score"].to_numpy() >= t
    lab = w["label"].to_numpy() == 1
    tp, fp = int((flagged & lab).sum()), int((flagged & ~lab).sum())
    fn, tn = int((~flagged & lab).sum()), int((~flagged & ~lab).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f1,
            "fpr": fp / (fp + tn) if fp + tn else 0.0}


def report(cache: Path, thresholds: list[float]) -> None:
    files = sorted(cache.glob("*.csv.gz"))
    if not files:
        sys.exit(f"nothing cached in {cache}")
    data = {f.name[:-7]: pd.read_csv(f) for f in files}
    rows = []
    for name, w in data.items():
        group = name.split("__")[0]
        for t in thresholds:
            rows.append({"group": group, "log": name.split("__")[1], "t": t, **metrics_at(w, t)})
    res = pd.DataFrame(rows)

    pd.set_option("display.width", 200, "display.max_rows", 500)
    print("\nper log (precision / recall / FPR)")
    for t in thresholds:
        sub = res[res["t"] == t]
        print(f"\nthreshold {t}")
        print(sub[["group", "log", "tp", "fp", "fn", "precision", "recall", "f1", "fpr"]]
              .round(3).to_string(index=False))

    print("\npooled by group, then macro-F1 across logs with attacks")
    summary = []
    for t in thresholds:
        sub = res[res["t"] == t]
        line = {"t": t}
        for g, gs in sub.groupby("group"):
            tp, fp, fn, tn = gs[["tp", "fp", "fn", "tn"]].sum()
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else np.nan
            line[f"{g} P"] = p
            line[f"{g} R"] = r
            line[f"{g} FPR"] = fp / (fp + tn) if fp + tn else 0.0
        attacked = sub[sub["tp"] + sub["fn"] > 0]
        line["macro F1"] = attacked["f1"].mean()
        summary.append(line)
    print(pd.DataFrame(summary).round(3).to_string(index=False))

    print("\ncomponent firing rate (>= 0.5) on attack vs normal windows")
    comp_rows = []
    for name, w in data.items():
        lab = w["label"] == 1
        r = {"log": name}
        for c in COMPONENTS:
            r[c] = f"{(w.loc[lab, c] >= 0.5).mean() if lab.any() else float('nan'):.2f}/" \
                   f"{(w.loc[~lab, c] >= 0.5).mean():.2f}"
        comp_rows.append(r)
    print(pd.DataFrame(comp_rows).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", nargs="*", default=[])
    ap.add_argument("--baseline", nargs="*", default=[],
                    help="attack-free capture(s) of the same vehicle to learn the baseline from")
    ap.add_argument("--group", default=None, help="label for these logs in the report")
    ap.add_argument("--cache", default="out/sweep")
    ap.add_argument("--thresholds", type=float, nargs="*", default=DEFAULT_THRESHOLDS)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    if args.logs:
        baseline_df = None
        if args.baseline:
            t0 = time.time()
            baseline_df = loader.concat_captures([loader.load_auto(p) for p in args.baseline])
            print(f"baseline: {len(baseline_df):,} frames from {len(args.baseline)} capture(s), "
                  f"{time.time() - t0:.0f}s")
        group = args.group or (Path(args.baseline[0]).parent.name if args.baseline else "self")
        for log in args.logs:
            score_log(log, baseline_df, cache, group)
    if args.report or not args.logs:
        report(cache, args.thresholds)


if __name__ == "__main__":
    main()
