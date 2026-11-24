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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import llm  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    """Rows of a JSON-lines file. A run stopped mid-write can leave one
    truncated last line; it is skipped, and that alert is simply asked again."""
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def run_name(args) -> str:
    if args.run:
        return args.run
    if args.explainer == "control":
        return f"control-{args.rules}_{args.scope}"
    model = (args.model or "model").replace("/", "-")
    return f"{model}_{args.prompt}_{args.scope}"


def answer(explainer, row: dict) -> dict:
    """Ask one explainer about one packet; never raises."""
    evidence = row["evidence"]
    rec = {"id": row["id"], "error": None, "raw": None}
    t0 = time.perf_counter()
    try:
        if isinstance(explainer, llm.MockExplainer):
            exp = explainer.explain(evidence)
        else:
            rec["raw"] = explainer.complete(evidence)
            exp = llm.parse_reply(rec["raw"], evidence, explainer.model)
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
        rec["error"] = f"{type(exc).__name__}: {exc}"[:500]
    rec["latency_s"] = round(time.perf_counter() - t0, 3)
    if getattr(explainer, "last_meta", None):
        rec["meta"] = explainer.last_meta
        explainer.last_meta = {}
    return rec


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
    ap.add_argument("--dataset", choices=["hcrl", "road", "ctt", "tue"], default=None,
                    help="only alerts from one dataset")
    ap.add_argument("--no-retry", dest="retry_errors", action="store_false",
                    help="keep earlier failed attempts as final instead of asking again")
    ap.add_argument("--workers", type=int, default=1,
                    help="requests in flight at once; replies are written as they finish")
    ap.add_argument("--max-tokens", type=int, default=16000,
                    help="reply budget for the chat explainer; reasoning models need room "
                         "to think before they answer")
    args = ap.parse_args()

    packets = read_jsonl(BACKEND / "out" / "alerts" / args.set_name / f"packets_{args.scope}.jsonl")
    if args.dataset:
        alerts = read_jsonl(BACKEND / "out" / "alerts" / args.set_name / "alerts.jsonl")
        keep = {a["id"] for a in alerts if a["dataset"] == args.dataset}
        packets = [p for p in packets if p["id"] in keep]
    if args.limit:
        packets = packets[:args.limit]
    out = BACKEND / "out" / "explanations" / args.set_name / run_name(args)
    out.mkdir(parents=True, exist_ok=True)
    replies_path = out / "replies.jsonl"
    done: set[str] = set()
    if replies_path.exists():
        # Failed attempts move to errors.jsonl and are retried; successful
        # replies stay and are never asked again.
        previous = read_jsonl(replies_path)
        ok = [r for r in previous if not r["error"]]
        failed = [r for r in previous if r["error"]]
        if failed and args.retry_errors:
            with (out / "errors.jsonl").open("a") as err_sink:
                for r in failed:
                    err_sink.write(json.dumps(r) + "\n")
            replies_path.write_text("".join(json.dumps(r) + "\n" for r in ok))
        done = {r["id"] for r in (ok if args.retry_errors else previous)}

    def make_explainer():
        if args.explainer == "control":
            return llm.MockExplainer(rules=args.rules)
        kwargs = {"prompt_version": args.prompt, "strict": True}
        if args.explainer == "chat":
            return llm.ChatExplainer(model=args.model, base_url=args.base_url,
                                     max_tokens=args.max_tokens, **kwargs)
        if args.explainer == "claude":
            return llm.ClaudeExplainer(args.model or "claude-sonnet-4-5", **kwargs)
        return llm.OpenAIExplainer(args.model or "gpt-4o-mini", **kwargs)

    explainer = make_explainer()
    if args.explainer == "control":
        model, prompt_sha = f"rule-based control (rules {args.rules})", None
    else:
        model = explainer.model
        prompt_sha = hashlib.sha256(explainer.system_prompt.encode()).hexdigest()

    todo = [(i, row) for i, row in enumerate(packets, 1) if row["id"] not in done]
    lock = threading.Lock()
    local = threading.local()

    def work(i: int, row: dict, sink) -> None:
        # One explainer per thread: the chat explainer keeps per-call metadata.
        if not hasattr(local, "explainer"):
            local.explainer = make_explainer()
        rec = answer(local.explainer, row)
        with lock:
            sink.write(json.dumps(rec) + "\n")
            sink.flush()
        if args.explainer != "control":
            print(f"[{i}/{len(packets)}] {row['id']} "
                  f"{rec.get('attack_type', 'ERROR')} {rec['latency_s']}s", flush=True)

    with replies_path.open("a") as sink:
        if args.workers <= 1:
            for i, row in todo:
                work(i, row, sink)
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for fut in [pool.submit(work, i, row, sink) for i, row in todo]:
                    fut.result()
    replies = read_jsonl(replies_path)
    (out / "run.json").write_text(json.dumps({
        "set": args.set_name, "run": out.name, "explainer": args.explainer, "model": model,
        "scope": args.scope,
        "control_rules": args.rules if args.explainer == "control" else None,
        "prompt_version": None if args.explainer == "control" else args.prompt,
        "prompt_sha256": prompt_sha,
        "temperature": None if args.explainer == "control" else 0,
        "max_tokens": None if args.explainer == "control" else args.max_tokens,
        "strict": True, "fallbacks": 0,
        "alerts": len(replies), "errors": sum(1 for r in replies if r["error"]),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    print(f"{out.relative_to(BACKEND)}: {len(replies)} replies, "
          f"{sum(1 for r in replies if r['error'])} errors")


if __name__ == "__main__":
    main()
