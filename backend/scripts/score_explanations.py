"""Score explainer runs on a frozen alert set and compare them pairwise.

Run from the backend folder:
    python -m scripts.score_explanations --set midterm100
    python -m scripts.score_explanations --set midterm100 --runs control_window control_alert

For every run:
    label accuracy on attack alerts, per dataset and per true attack type,
    with Wilson 95% intervals; what false alarms were called; the share of
    claims whose citations all resolve; reply latency.
For every pair of runs:
    exact McNemar test and a paired bootstrap interval on the accuracy
    difference, over the attack alerts both runs answered.

Writes out/explanations/<set>/scores.json and scores.md.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import stats  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prop(k: int, n: int) -> dict:
    lo, hi = stats.wilson_interval(k, n)
    return {"k": k, "n": n, "value": (k / n if n else None), "lo": lo, "hi": hi}


def score_run(alerts: dict[str, dict], replies: list[dict]) -> dict:
    by_id = {r["id"]: r for r in replies}
    answered = [a for a in alerts.values() if a["id"] in by_id]
    ok = [a for a in answered if not by_id[a["id"]]["error"]]
    attack = [a for a in ok if a["is_attack"]]
    false_alarm = [a for a in ok if not a["is_attack"]]

    def correct(a: dict) -> bool:
        return by_id[a["id"]]["attack_type"] == a["true_type"]

    accuracy = {"all": prop(sum(correct(a) for a in attack), len(attack))}
    for ds in sorted({a["dataset"] for a in attack}):
        rows = [a for a in attack if a["dataset"] == ds]
        accuracy[ds] = prop(sum(correct(a) for a in rows), len(rows))
    by_type = {}
    confusion: dict[str, dict[str, int]] = {}
    for a in attack:
        key = f"{a['dataset']}/{a['true_type']}"
        slot = by_type.setdefault(key, [0, 0])
        slot[0] += correct(a)
        slot[1] += 1
        pred = by_id[a["id"]]["attack_type"]
        confusion.setdefault(key, {}).setdefault(pred, 0)
        confusion[key][pred] += 1
    fa_labels: dict[str, int] = {}
    for a in false_alarm:
        pred = by_id[a["id"]]["attack_type"]
        fa_labels[pred] = fa_labels.get(pred, 0) + 1
    claims = [c for a in ok for c in by_id[a["id"]].get("claims", [])]
    cited_ok = 0
    for a in ok:
        r = by_id[a["id"]]
        valid = set(r.get("evidence_ids", []))
        for c in r.get("claims", []):
            cites = c.get("cites", [])
            cited_ok += bool(cites) and all(x in valid for x in cites)
    latencies = [by_id[a["id"]]["latency_s"] for a in ok]
    return {
        "alerts": len(answered), "errors": len(answered) - len(ok),
        "attack_alerts": len(attack), "false_alarms": len(false_alarm),
        "accuracy": accuracy,
        "accuracy_by_type": {k: prop(v[0], v[1]) for k, v in sorted(by_type.items())},
        "confusion": confusion,
        "false_alarm_labels": fa_labels,
        "false_alarms_called_benign": prop(fa_labels.get("benign", 0), len(false_alarm)),
        "claims": len(claims),
        "claims_with_valid_citations": prop(cited_ok, len(claims)),
        "replies_fully_grounded": prop(sum(bool(by_id[a["id"]].get("grounded")) for a in ok),
                                       len(ok)),
        "latency_s": ({"median": statistics.median(latencies), "max": max(latencies)}
                      if latencies else None),
        "correct_by_id": {a["id"]: bool(correct(a)) for a in attack},
    }


def compare(a: dict, b: dict, alerts: dict[str, dict]) -> dict:
    out = {}
    shared = sorted(set(a["correct_by_id"]) & set(b["correct_by_id"]))
    groups = {"all": shared}
    for ds in sorted({alerts[i]["dataset"] for i in shared}):
        groups[ds] = [i for i in shared if alerts[i]["dataset"] == ds]
    for name, ids in groups.items():
        xa = [int(a["correct_by_id"][i]) for i in ids]
        xb = [int(b["correct_by_id"][i]) for i in ids]
        only_a = sum(1 for x, y in zip(xa, xb) if x and not y)
        only_b = sum(1 for x, y in zip(xa, xb) if y and not x)
        out[name] = {
            "n": len(ids), "a_correct": sum(xa), "b_correct": sum(xb),
            "only_a_correct": only_a, "only_b_correct": only_b,
            "mcnemar_p": stats.mcnemar_exact(only_a, only_b),
            "difference": stats.bootstrap_proportion_diff(xa, xb) if ids else None,
        }
    return out


def pct(p: dict) -> str:
    if not p["n"]:
        return "n/a"
    return f"{100 * p['value']:.0f}% ({p['k']}/{p['n']}; {100 * p['lo']:.0f} to {100 * p['hi']:.0f})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_name", default="midterm100")
    ap.add_argument("--runs", nargs="*", help="run names; default: every run present")
    args = ap.parse_args()

    alerts = {a["id"]: a for a in read_jsonl(BACKEND / "out" / "alerts" / args.set_name
                                            / "alerts.jsonl")}
    root = BACKEND / "out" / "explanations" / args.set_name
    names = args.runs or sorted(p.name for p in root.iterdir() if (p / "replies.jsonl").exists())
    runs = {n: score_run(alerts, read_jsonl(root / n / "replies.jsonl")) for n in names}
    pairs = {f"{x} vs {y}": compare(runs[x], runs[y], alerts) for x, y in combinations(names, 2)}

    report = {"set": args.set_name,
              "runs": {n: {k: v for k, v in r.items() if k != "correct_by_id"}
                       for n, r in runs.items()},
              "pairs": pairs}
    (root / "scores.json").write_text(json.dumps(report, indent=2) + "\n")

    datasets = sorted({a["dataset"] for a in alerts.values()})
    lines = [f"# Explainer scores: {args.set_name}", "",
             "Label accuracy on attack alerts, with Wilson 95% intervals.", "",
             "| run | " + " | ".join(datasets) + " | all | false alarms called benign | "
             "claims with valid citations | median latency |",
             "|---|" + "---|" * (len(datasets) + 4)]
    for n, r in runs.items():
        cells = [pct(r["accuracy"].get(ds, {"n": 0})) for ds in datasets]
        lat = f"{r['latency_s']['median']:.1f}s" if r["latency_s"] else "n/a"
        lines.append(f"| {n} | " + " | ".join(cells) + f" | {pct(r['accuracy']['all'])} | "
                     f"{pct(r['false_alarms_called_benign'])} | "
                     f"{pct(r['claims_with_valid_citations'])} | {lat} |")
    lines += ["", "## By true attack type", ""]
    types = sorted({k for r in runs.values() for k in r["accuracy_by_type"]})
    lines += ["| run | " + " | ".join(types) + " |", "|---|" + "---|" * len(types)]
    for n, r in runs.items():
        lines.append(f"| {n} | " + " | ".join(
            pct(r["accuracy_by_type"].get(t, {"n": 0})) for t in types) + " |")
    if pairs:
        lines += ["", "## Paired comparisons (exact McNemar)", "",
                  "| pair | group | n | first correct | second correct | only first | "
                  "only second | p |", "|---|---|---|---|---|---|---|---|"]
        for name, groups in pairs.items():
            for g, v in groups.items():
                lines.append(f"| {name} | {g} | {v['n']} | {v['a_correct']} | {v['b_correct']} | "
                             f"{v['only_a_correct']} | {v['only_b_correct']} | "
                             f"{v['mcnemar_p']:.4f} |")
    (root / "scores.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
