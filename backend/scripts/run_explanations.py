"""Run one explainer over a frozen alert set and save every reply.

Run from the backend folder:
    # the rule-based control: either rule version, on either packet scope
    python -m scripts.run_explanations --set midterm100 --explainer control --rules v1 --scope window
    python -m scripts.run_explanations --set midterm100 --explainer control --rules v2 --scope alert

    # a model behind an OpenAI-compatible endpoint
    export CHAT_BASE_URL=https://<host>/v1 CHAT_API_KEY=...
    python -m scripts.run_explanations --set midterm100 --explainer chat \
        --model glm-5.3 --scope alert --prompt v2

Each (set, explainer, model, scope, prompt) is one run, written to
out/explanations/<set>/<run>/:
    replies.jsonl   per alert: predicted label, claims, citation check, the
                    raw reply text, latency, and any error
    run.json        what was run: model, prompt version and hash, scope,
                    temperature, counts

Runs are strict: an API error or an unparseable reply is recorded as an
error for that alert. Nothing falls back to the control. An interrupted
run resumes where it stopped; alerts already answered are not asked again.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import llm  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_name(args) -> str:
    if args.run:
        return args.run
    if args.explainer == "control":
        return f"control-{args.rules}_{args.scope}"
    model = (args.model or "model").replace("/", "-")
    return f"{model}_{args.prompt}_{args.scope}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_name", default="midterm100")
    ap.add_argument("--explainer", choices=["control", "chat", "claude", "openai"],
                    default="control")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--scope", choices=["window", "alert"], default="alert")
    ap.add_argument("--rules", choices=list(llm.CONTROL_RULES), default=llm.DEFAULT_CONTROL_RULES,
                    help="rule version of the control")
    ap.add_argument("--prompt", choices=sorted(llm.SYSTEM_PROMPTS), default=llm.DEFAULT_PROMPT)
    ap.add_argument("--run", default=None, help="run name; default is derived")
    ap.add_argument("--limit", type=int, default=None, help="only the first N alerts")
    args = ap.parse_args()

    packets = read_jsonl(BACKEND / "out" / "alerts" / args.set_name / f"packets_{args.scope}.jsonl")
    if args.limit:
        packets = packets[:args.limit]
    out = BACKEND / "out" / "explanations" / args.set_name / run_name(args)
    out.mkdir(parents=True, exist_ok=True)
    replies_path = out / "replies.jsonl"
    done = {r["id"] for r in read_jsonl(replies_path)} if replies_path.exists() else set()

    if args.explainer == "control":
        explainer = llm.MockExplainer(rules=args.rules)
        model, prompt_sha = f"rule-based control (rules {args.rules})", None
    else:
        kwargs = {"prompt_version": args.prompt, "strict": True}
        if args.explainer == "chat":
            explainer = llm.ChatExplainer(model=args.model, base_url=args.base_url, **kwargs)
        elif args.explainer == "claude":
            explainer = llm.ClaudeExplainer(args.model or "claude-sonnet-4-5", **kwargs)
        else:
            explainer = llm.OpenAIExplainer(args.model or "gpt-4o-mini", **kwargs)
        model = explainer.model
        prompt_sha = hashlib.sha256(explainer.system_prompt.encode()).hexdigest()

    errors = 0
    with replies_path.open("a") as sink:
        for i, row in enumerate(packets, 1):
            if row["id"] in done:
                continue
            evidence = row["evidence"]
            rec = {"id": row["id"], "error": None, "raw": None}
            t0 = time.perf_counter()
            try:
                if args.explainer == "control":
                    exp = explainer.explain(evidence)
                else:
                    rec["raw"] = explainer.complete(evidence)
                    exp = llm.parse_reply(rec["raw"], evidence, model)
                valid = {item["id"] for item in evidence["items"]}
                rec.update({
                    "attack_type": exp.attack_type,
                    "confidence": exp.confidence,
                    "severity": exp.severity,
                    "affected_function": exp.affected_function,
                    "summary": exp.summary,
                    "claims": exp.claims,
                    "grounded": exp.grounded,
                    "evidence_ids": sorted(valid),
                })
            except Exception as exc:
                errors += 1
                rec["error"] = f"{type(exc).__name__}: {exc}"[:500]
            rec["latency_s"] = round(time.perf_counter() - t0, 3)
            sink.write(json.dumps(rec) + "\n")
            sink.flush()
            if args.explainer != "control":
                print(f"[{i}/{len(packets)}] {row['id']} "
                      f"{rec.get('attack_type', 'ERROR')} {rec['latency_s']}s", flush=True)

    replies = read_jsonl(replies_path)
    (out / "run.json").write_text(json.dumps({
        "set": args.set_name, "run": out.name, "explainer": args.explainer, "model": model,
        "scope": args.scope,
        "control_rules": args.rules if args.explainer == "control" else None,
        "prompt_version": None if args.explainer == "control" else args.prompt,
        "prompt_sha256": prompt_sha,
        "temperature": None if args.explainer == "control" else 0,
        "strict": True, "fallbacks": 0,
        "alerts": len(replies), "errors": sum(1 for r in replies if r["error"]),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    print(f"{out.relative_to(BACKEND)}: {len(replies)} replies, "
          f"{sum(1 for r in replies if r['error'])} errors")


if __name__ == "__main__":
    main()
