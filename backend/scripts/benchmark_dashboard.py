"""Measure in-process API latency and response size without any model calls.

This measures application work, not browser rendering or internet round trips.
Requires httpx (pip install -r requirements-dev.txt).
"""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import platform
import statistics
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def run(repeats=10, capture=None, baseline=None, metadata=None):
    client = TestClient(app)
    started = time.perf_counter()
    if capture:
        files = {"file": (capture.name, capture.read_bytes())}
        if baseline:
            files["baseline_file"] = (baseline.name, baseline.read_bytes())
        if metadata:
            files["metadata_file"] = (metadata.name, metadata.read_bytes())
        response = client.post("/api/analyze/upload", files=files)
    else:
        response = client.post("/api/analyze/synthetic", json={"duration_s": 120, "seed": 7})
    response.raise_for_status()
    summary = response.json()
    elapsed = time.perf_counter() - started
    backend = Path(__file__).resolve().parents[1]
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "code_sha256": {n: hashlib.sha256((backend / n).read_bytes()).hexdigest() for n in ("app/main.py", "app/pipeline.py", "scripts/benchmark_dashboard.py")},
              "scope": "in-process FastAPI TestClient; no network or browser rendering; no model calls",
              "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (capture, baseline, metadata) if p},
              "python": platform.python_version(), "frame_count": summary["frame_count"],
              "analyze_s": elapsed, "evaluation_frames_per_second_including_baseline_setup": summary["frame_count"] / elapsed,
              "stage_timing_s": summary["timing_s"], "endpoints": {}}
    for route in ("summary", "timeline", "alerts", "metrics", "ids"):
        times = []
        for _ in range(repeats + 1):
            start = time.perf_counter()
            response = client.get(f"/api/analysis/{summary['analysis_id']}/{route}", params={"explainer": "mock"})
            response.raise_for_status()
            times.append((time.perf_counter() - start) * 1000)
        warm = sorted(times[1:])
        result["endpoints"][route] = {"cold_ms": times[0], "warm_median_ms": statistics.median(warm),
                                       "warm_p95_ms": warm[min(len(warm) - 1, int(len(warm) * .95))],
                                       "response_bytes": len(response.content), "warm_requests": repeats}
        result["endpoints"][route]["transfer_bytes"] = int(response.headers.get("content-length", len(response.content)))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("repeats must be at least two")
    if args.out.exists():
        parser.error("Choose a new output file; existing measurements are preserved")
    payload = run(args.repeats, args.capture, args.baseline, args.metadata)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
