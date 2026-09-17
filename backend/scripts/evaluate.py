"""Command-line evaluation harness.

Examples:
    python -m scripts.evaluate --seeds 1 2 3 4 5
    python -m scripts.evaluate --detector forest
    python -m scripts.evaluate --csv data/carhacking_dos.csv

Prints per-run detection metrics and the mean across runs. This is the
script that produces the numbers for the paper, and it imports the same
modules the dashboard uses so the two can never disagree.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import loader, pipeline  # noqa: E402
from app.llm import get_explainer  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--detector", default="rule", choices=["rule", "forest"])
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--explainer", default="mock")
    ap.add_argument("--csv", default=None, help="evaluate a real log instead of synthetic runs")
    ap.add_argument("--out", default=None, help="write the full report as JSON")
    args = ap.parse_args()

    explainer = get_explainer(args.explainer)
    reports = []

    if args.csv:
        df = loader.load_auto(args.csv)
        analysis = pipeline.run_analysis(df, source=args.csv, params={"csv": args.csv},
                                         detector=args.detector, threshold=args.threshold)
        reports.append({"run": args.csv, **pipeline.evaluation_report(analysis, explainer)})
    else:
        for seed in args.seeds:
            analysis = pipeline.run_synthetic(duration_s=args.duration, seed=seed,
                                              detector=args.detector, threshold=args.threshold)
            reports.append({"run": f"seed={seed}", **pipeline.evaluation_report(analysis, explainer)})

    print(f"{'run':<12} {'precision':>9} {'recall':>7} {'f1':>7} {'FPR':>7} {'cls acc':>8} {'grounded':>9}")
    for r in reports:
        d, c, g = r["detection"], r["classification"], r["grounding"]
        print(f"{r['run']:<12} {d['precision']:>9.3f} {d['recall']:>7.3f} {d['f1']:>7.3f} "
              f"{d['false_positive_rate']:>7.3f} "
              f"{(c['accuracy'] if c['accuracy'] is not None else float('nan')):>8.3f} "
              f"{(g['grounded_rate'] if g['grounded_rate'] is not None else float('nan')):>9.3f}")

    if len(reports) > 1:
        for key in ("precision", "recall", "f1"):
            vals = [r["detection"][key] for r in reports]
            print(f"mean {key}: {statistics.mean(vals):.3f} "
                  f"(sd {statistics.pstdev(vals):.3f})")

    per_type: dict[str, list[float]] = {}
    for r in reports:
        for atype, v in r["detection"]["per_attack_type"].items():
            per_type.setdefault(atype, []).append(v["recall"])
    if per_type:
        print("\nrecall by attack type")
        for atype, vals in sorted(per_type.items()):
            print(f"  {atype:<12} {statistics.mean(vals):.3f}")

    if args.out:
        Path(args.out).write_text(json.dumps(reports, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
