"""Matched frozen-evidence comparison, with per-request atomic checkpoints.

python -m scripts.benchmark_models --corpus out/frozen_2026-10-30/hcrl.json \
  --model rcd:gemma-4-31b --out out/explanations_corrected_2026-10-30_gemma/hcrl

A model failure is recorded separately and never scored as a model prediction.
Resume verifies corpus, prompt, code and request settings before reusing output.
Costs are unknown unless --prices supplies explicit USD per million token rates.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from app.llm import CONTROL_VERSION, PROMPT_VERSION, SYSTEM_PROMPT, get_explainer, explainer_key


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return round(values[lo] + (values[hi] - values[lo]) * (position - lo), 6)


def summarize(records):
    success = [r for r in records if not r["explanation"].get("fallback", False)]
    attack = [r for r in records if r["true_type"] not in ("normal", "benign", "unknown", "injected", "")]
    normal = [r for r in records if r["true_type"] in ("normal", "benign")]
    def correct(r):
        return not r["explanation"].get("fallback", False) and r["explanation"]["attack_type"] == r["true_type"]
    successful_attacks = [r for r in attack if not r["explanation"].get("fallback", False)]
    latency = [r["explanation"]["latency_s"] for r in success]
    all_latency = [r["explanation"]["latency_s"] for r in records]
    confusion = {}
    for r in attack:
        pred = "request_failed" if r["explanation"].get("fallback") else r["explanation"]["attack_type"]
        row = confusion.setdefault(r["true_type"], {})
        row[pred] = row.get(pred, 0) + 1
    return {
        "attempts": len(records), "successful_responses": len(success), "fallbacks": len(records) - len(success),
        "classification": {"scored_alerts": len(attack), "correct": sum(map(correct, attack)),
                           "accuracy": sum(map(correct, attack)) / len(attack) if attack else None,
                           "successful_only_accuracy": sum(map(correct, successful_attacks)) / len(successful_attacks) if successful_attacks else None,
                           "confusion": confusion},
        "false_alarms": len(normal),
        "false_alarms_labeled_benign": sum(not r["explanation"].get("fallback") and r["explanation"]["attack_type"] == "benign" for r in normal),
        "grounding": {"rate": sum(bool(r["explanation"].get("grounded")) for r in success) / len(success) if success else None,
                      "meaning": "Citation validity only; semantic claim support needs review"},
        "latency_s_median": quantile(latency, .5), "latency_s_p95": quantile(latency, .95),
        "latency_s_max": max(latency) if latency else None,
        "attempt_latency_s_p95": quantile(all_latency, .95),
        "input_tokens": sum(r["explanation"].get("usage", {}).get("input_tokens", 0) for r in records),
        "output_tokens": sum(r["explanation"].get("usage", {}).get("output_tokens", 0) for r in records),
        "estimated_cost_usd": sum(r["estimated_cost_usd"] for r in records) if records and all(r.get("estimated_cost_usd") is not None for r in records) else None,
    }


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--model", required=True, help="mock, rcd:MODEL, openai:MODEL, claude:MODEL")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, help="Smoke-test prefix; part of the manifest, not a final comparison")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--prices", type=Path, help="JSON map selector -> {input_usd_per_million, output_usd_per_million, source, date}")
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8 or (args.limit is not None and args.limit < 1):
        parser.error("workers must be 1..8 and limit positive")
    if args.env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    corpus = json.loads(args.corpus.read_text())
    selected = corpus["alerts"][:args.limit] if args.limit else corpus["alerts"]
    if not selected:
        parser.error("Corpus contains no alerts")
    ex = get_explainer(args.model)
    price = json.loads(args.prices.read_text()).get(args.model) if args.prices else None
    if price and (not price.get("source") or not price.get("date") or any(not isinstance(price.get(k), (int, float)) or not math.isfinite(price[k]) or price[k] < 0 for k in ("input_usd_per_million", "output_usd_per_million"))):
        parser.error("Prices require nonnegative finite rates, source, and date")
    corpus_hash = fingerprint(corpus)
    manifest = {"corpus_sha256": corpus_hash, "selector": args.model, "request_key": explainer_key(ex),
                "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                "llm_code_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "app/llm.py").read_bytes()).hexdigest(),
                "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limit": args.limit, "prices": price, "workers": args.workers,
                "timeout_s": getattr(ex, "timeout_s", None)}
    path = args.out / f"explanations_{ex.name}.json"
    records = {}
    elapsed_before = 0.0
    if path.exists():
        prior = json.loads(path.read_text())
        if prior.get("manifest") != manifest:
            parser.error("Existing run differs in corpus, code, prompt, price, or request settings; choose a new output directory")
        records = {r["corpus_index"]: r for r in prior["alerts"]}
        elapsed_before = prior.get("wall_seconds", 0)
    try:
        git = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git = None
    started = time.perf_counter()
    payload = {"dataset": corpus["dataset"], "corpus_sha256": corpus_hash, "manifest": manifest,
               "model": getattr(ex, "model", "mock"), "explainer": ex.name,
               "temperature": getattr(ex, "temperature", None), "git": git,
               "reasoning_effort": getattr(ex, "reasoning_effort", None),
               "max_tokens": getattr(ex, "max_tokens", None),
               "prompt_version": CONTROL_VERSION if ex.name == "mock" else PROMPT_VERSION,
               "status": "running", "expected_alerts": len(selected), "alerts": [],
               "scoring": "Attack-label accuracy on frozen alerts; failures count as incorrect, never control predictions. Normal alerts scored separately. Development corpus, not an untouched test set."}
    def checkpoint():
        payload["alerts"] = [records[i] for i in sorted(records)]
        payload["summary"] = summarize(payload["alerts"])
        payload["wall_seconds"] = round(elapsed_before + time.perf_counter() - started, 6)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["summary"]["successful_alerts_per_second"] = len([r for r in records.values() if not r["explanation"].get("fallback")]) / max(payload["wall_seconds"], 1e-9)
        atomic_write(path, payload)
    def run(index, row):
        # Each worker owns its client; no mutable shared client/request state.
        worker = get_explainer(args.model)
        t0 = time.perf_counter()
        explanation = worker.explain(row["evidence"]).to_json()
        if explanation["latency_s"] is None:
            explanation["latency_s"] = round(time.perf_counter() - t0, 6)
        usage = explanation.get("usage", {})
        cost = 0.0 if ex.name == "mock" else None
        if price and usage:
            cost = (usage["input_tokens"] * price["input_usd_per_million"] + usage["output_tokens"] * price["output_usd_per_million"]) / 1e6
        record = {k: row[k] for k in ("capture", "role", "alert_id", "start", "end", "true_type", "detector_score") if k in row}
        return {**record, "corpus_index": index, "evidence_sha256": fingerprint(row["evidence"]),
                "explanation": explanation, "estimated_cost_usd": cost}
    checkpoint()
    pending = [(i, row) for i, row in enumerate(selected) if i not in records or (args.retry_failures and records[i]["explanation"].get("fallback"))]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, i, row): i for i, row in pending}
        for future in as_completed(futures):
            index = futures[future]
            records[index] = future.result()
            checkpoint()
            exp = records[index]["explanation"]
            print(f"{len(records)}/{len(selected)} index={index} model={args.model} prediction={exp['attack_type']} fallback={exp['fallback']} latency={exp['latency_s']}", flush=True)
    payload["status"] = "complete" if all(not r["explanation"].get("fallback") for r in records.values()) else "complete_with_failures"
    checkpoint()
    print(json.dumps(payload["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
