"""Claim-support review: do explanations say only what their evidence shows?

Citation validity only proves that a claim points at a real evidence item.
This review asks the stronger question, by hand: does the cited evidence
actually support what the claim says?

Run from the backend folder:
    python -m scripts.claim_review sample --set heldout
    #   two people fill in out/claim_review/heldout/rater_A.csv and rater_B.csv
    #   independently, following out/claim_review/heldout/rubric.md
    python -m scripts.claim_review score --set heldout

sample   Draws the same number of claims from every explainer run (default
         10 each) among claims that cite at least one item, spread across
         the alerts' true attack types, and writes:
           sheet.csv      claim text and the full text of every cited item,
                          under an opaque claim id. No run name, no model,
                          no ground truth: raters cannot tell who wrote a
                          claim or whether its alert label was right.
           rater_A.csv,   copies of the sheet with empty label and note
           rater_B.csv    columns, one per rater
           key.json       which run, alert and claim each id came from
           rubric.md      the labels and how to apply them
score    Reads both rater files and reports Cohen's kappa between raters,
         the label distribution per run for claims both raters agree on,
         and every disagreement, for adjudication.

Sampling is seeded and the sheet is written once: rerunning `sample` will
not overwrite rater files that already exist.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import stats  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
LABELS = {"S": "supported", "U": "unsupported", "C": "contradicted"}

RUBRIC = """# Claim-support review rubric

You will see one claim at a time, with the full text of every evidence item
the claim cites. Judge the claim **only against those cited items**. Do not
use what you know about CAN attacks, other items, or other claims.

You will not see which model wrote the claim or what the alert really was.
Please do not try to find out, and do not compare notes with the other rater
until both sheets are complete.

Put exactly one letter in the `label` column:

| label | meaning | example |
|---|---|---|
| **S** supported | Every factual statement in the claim follows from the cited items. Rounding and paraphrase are fine. | Claim: "0x000 sent 3,724 frames." Cited item says 0x000 sent 3724 frames. |
| **U** unsupported | The cited items do not establish the claim, though they do not contradict it either. This includes interpretations the numbers do not force. | Claim: "This targets the brakes." Cited item gives only rates and gaps, no function. |
| **C** contradicted | A cited item says something incompatible with the claim. | Claim: "Bus load more than doubled." Cited item says load was 0.79x baseline. |

Rules for hard cases:

1. **Mixed claims.** If any part of the claim is contradicted, label C. Otherwise,
   if any part is unsupported, label U. Label S only when every part is supported.
2. **Inference.** A claim may draw a conclusion ("consistent with a flood") if the
   cited numbers make it reasonable on their face. A conclusion that needs facts
   not in the cited items is U.
3. **Arithmetic.** Check it. "Twice the baseline" for 1.5x is C. "About 2x" for 1.9x is S.
4. **Hedged claims.** "May indicate" or "could be" still needs the cited numbers to
   point that way. A hedge does not turn an unsupported claim into a supported one.
5. **Every claim here cites something.** Claims with no citation are counted
   separately and are not part of this review.

Use the `note` column for anything that made a label hard. Notes help adjudication.
"""


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sample(args) -> None:
    root = BACKEND / "out"
    out = root / "claim_review" / args.set_name
    if (out / "rater_A.csv").exists() and not args.force:
        sys.exit(f"{out}/rater_A.csv exists; refusing to overwrite rater work (use --force)")
    out.mkdir(parents=True, exist_ok=True)
    alerts = {a["id"]: a for a in read_jsonl(root / "alerts" / args.set_name / "alerts.jsonl")}
    packets = {}
    for scope in ("alert", "window"):
        path = root / "alerts" / args.set_name / f"packets_{scope}.jsonl"
        if path.exists():
            packets[scope] = {r["id"]: r["evidence"] for r in read_jsonl(path)}
    run_root = root / "explanations" / args.set_name
    runs = args.runs or sorted(p.name for p in run_root.iterdir()
                               if (p / "replies.jsonl").exists())
    rng = random.Random(args.seed)
    chosen = []
    for run in runs:
        meta = json.loads((run_root / run / "run.json").read_text())
        scope = meta.get("scope", "alert")
        pool = defaultdict(list)     # true type -> claims
        for r in read_jsonl(run_root / run / "replies.jsonl"):
            if r.get("error"):
                continue
            for k, c in enumerate(r.get("claims") or []):
                # Uncited claims are already counted by the citation-validity
                # metric, and there is nothing to judge them against.
                if isinstance(c, dict) and str(c.get("text", "")).strip() and c.get("cites"):
                    pool[alerts[r["id"]]["true_type"]].append((r["id"], k, c))
        # Round-robin over true types so one dominant class cannot fill the sample.
        for t in pool:
            rng.shuffle(pool[t])
        types = sorted(pool)
        picked = []
        while len(picked) < args.per_run and any(pool[t] for t in types):
            for t in types:
                if pool[t] and len(picked) < args.per_run:
                    picked.append(pool[t].pop())
        for alert_id, k, c in picked:
            chosen.append({"run": run, "scope": scope, "alert": alert_id, "claim_index": k,
                           "text": c["text"], "cites": list(c.get("cites") or [])})
    rng.shuffle(chosen)

    rows, key = [], {}
    for n, c in enumerate(chosen, 1):
        cid = f"C{n:03d}"
        items = {i["id"]: i for i in packets[c["scope"]][c["alert"]]["items"]}
        cited = [f"[{x}] {items[x]['text']}" for x in c["cites"] if x in items]
        rows.append({"claim_id": cid, "claim": c["text"], "cited_items": "\n".join(cited),
                     "label": "", "note": ""})
        key[cid] = {k: c[k] for k in ("run", "scope", "alert", "claim_index")}
        key[cid]["true_type"] = alerts[c["alert"]]["true_type"]

    fields = ["claim_id", "claim", "cited_items", "label", "note"]
    for name in ("sheet.csv", "rater_A.csv", "rater_B.csv"):
        with (out / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    (out / "key.json").write_text(json.dumps({"set": args.set_name, "seed": args.seed,
                                              "per_run": args.per_run, "runs": runs,
                                              "claims": key}, indent=2) + "\n")
    (out / "rubric.md").write_text(RUBRIC)
    counts = Counter(v["run"] for v in key.values())
    print(f"{len(rows)} claims written to {out}")
    for run in runs:
        print(f"  {run}: {counts.get(run, 0)}")


def read_labels(path: Path) -> dict[str, tuple[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {r["claim_id"]: (r["label"].strip().upper()[:1], r.get("note", "").strip())
                for r in csv.DictReader(fh)}


def score(args) -> None:
    out = BACKEND / "out" / "claim_review" / args.set_name
    key = json.loads((out / "key.json").read_text())
    a, b = read_labels(out / "rater_A.csv"), read_labels(out / "rater_B.csv")
    ids = sorted(key["claims"])
    missing = [i for i in ids if a.get(i, ("",))[0] not in LABELS or b.get(i, ("",))[0] not in LABELS]
    if missing:
        sys.exit(f"{len(missing)} claim(s) lack a valid S/U/C label from both raters, "
                 f"for example {', '.join(missing[:5])}")
    kappa = stats.cohen_kappa([a[i][0] for i in ids], [b[i][0] for i in ids])
    agreed = [i for i in ids if a[i][0] == b[i][0]]
    per_run: dict[str, Counter] = defaultdict(Counter)
    for i in agreed:
        per_run[key["claims"][i]["run"]][a[i][0]] += 1
    report = {
        "set": args.set_name, "claims": len(ids), "agreed": len(agreed),
        "kappa": kappa,
        "per_run": {
            run: {LABELS[l]: {"k": per_run[run][l], "n": sum(per_run[run].values()),
                              "ci": list(stats.wilson_interval(per_run[run][l],
                                                               sum(per_run[run].values())))}
                  for l in LABELS}
            for run in key["runs"]},
        "disagreements": [{"claim_id": i, "run": key["claims"][i]["run"],
                           "rater_A": a[i][0], "rater_B": b[i][0],
                           "note_A": a[i][1], "note_B": b[i][1]}
                          for i in ids if a[i][0] != b[i][0]],
    }
    (out / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [f"# Claim-support review: {args.set_name}", "",
             f"{len(ids)} claims, two raters. Cohen's kappa {kappa['kappa']:.3f} "
             f"(observed agreement {kappa['observed']:.1%}). Rates below use the "
             f"{len(agreed)} claims both raters labeled the same; disagreements are listed "
             f"for adjudication.", "",
             "| run | supported | unsupported | contradicted | claims |", "|---|---|---|---|---|"]
    for run, r in report["per_run"].items():
        n = r["supported"]["n"]
        cell = lambda l: f"{r[l]['k']} ({r[l]['k'] / n:.0%})" if n else "n/a"
        lines.append(f"| {run} | {cell('supported')} | {cell('unsupported')} | "
                     f"{cell('contradicted')} | {n} |")
    if report["disagreements"]:
        lines += ["", "## Disagreements", "", "| claim | run | A | B |", "|---|---|---|---|"]
        lines += [f"| {d['claim_id']} | {d['run']} | {d['rater_A']} | {d['rater_B']} |"
                  for d in report["disagreements"]]
    (out / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample", help="draw the claims and write the rating sheets")
    s.add_argument("--set", dest="set_name", default="heldout")
    s.add_argument("--runs", nargs="*", help="run names; default: every run present")
    s.add_argument("--per-run", type=int, default=10)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=sample)
    c = sub.add_parser("score", help="agreement and support rates from both rater files")
    c.add_argument("--set", dest="set_name", default="heldout")
    c.set_defaults(func=score)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
