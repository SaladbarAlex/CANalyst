"""CANalyst API.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Literal
import os
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

from . import benchmark, benchmarks, loader, pipeline
from .llm import explainer_options, get_explainer as _configured_explainer
from .pipeline import STORE

app = FastAPI(title="CANalyst API", version="0.1.0",
              description="LLM-assisted analysis of CAN bus attacks")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class SyntheticRequest(BaseModel):
    duration_s: float = Field(120.0, ge=20.0, le=900.0)
    seed: int = 7
    attacks: list[Literal["dos", "fuzzing", "spoofing", "replay", "masquerade"]] = ["dos", "fuzzing", "spoofing", "masquerade"]
    window_s: float = Field(0.5, gt=0.05, le=5.0)
    stride_s: float = Field(0.25, gt=0.01, le=5.0)
    detector: Literal["rule", "forest"] = "rule"
    threshold: float = Field(0.55, ge=0.05, le=0.99)


class AskRequest(BaseModel):
    question: str
    explainer: str | None = None


class ExplainRequest(BaseModel):
    explainer: str | None = None
    force: bool = False


def get_explainer(selector: str | None = None):
    try:
        return _configured_explainer(selector)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _get(analysis_id: str):
    a = STORE.get(analysis_id)
    if a is None:
        raise HTTPException(404, "Analysis not found. Run a new analysis.")
    return a


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "explainer": get_explainer().name, "analyses": STORE.list()}


@app.get("/api/explainers")
def explainers() -> dict:
    return explainer_options()


@app.get("/api/benchmark")
def saved_benchmark() -> dict:
    """Saved real-data explanation runs, read from disk. Makes no model calls."""
    return benchmark.load()


@app.get("/api/benchmark/detectors")
def saved_detection_benchmark() -> dict:
    return benchmark.load_detection()


_real_example_lock = threading.Lock()
_real_example_id: str | None = None


@app.post("/api/analyze/real-example")
def analyze_real_example() -> dict:
    """Open the installed ROAD example with its independent normal baseline."""
    global _real_example_id
    with _real_example_lock:
        existing = STORE.get(_real_example_id) if _real_example_id else None
        if existing is not None:
            return existing.summary()
        road = Path(__file__).resolve().parents[1] / "data/raw/road/road"
        capture = road / "attacks/correlated_signal_attack_3.log"
        normal = road / "ambient/ambient_dyno_drive_basic_short.log"
        metadata = capture.parent / "capture_metadata.json"
        if not all(p.is_file() for p in (capture, normal, metadata)):
            raise HTTPException(404, "ROAD example data is not installed. Upload a capture or generate demo traffic in Capture settings.")
        analysis = pipeline.run_analysis(
            loader.load_auto(str(capture)), source=capture.name,
            params={"example": "ROAD correlated-signal attack 3"},
            baseline_df=loader.load_auto(str(normal)), detector="rule",
            window_s=0.5, stride_s=0.25, threshold=0.55,
        )
        _real_example_id = analysis.analysis_id
        return analysis.summary()


@app.post("/api/analyze/synthetic")
def analyze_synthetic(req: SyntheticRequest) -> dict:
    if req.stride_s > req.window_s:
        raise HTTPException(422, "stride_s must not exceed window_s")
    try:
        analysis = pipeline.run_synthetic(
            duration_s=req.duration_s, seed=req.seed, attacks=req.attacks,
            window_s=req.window_s, stride_s=req.stride_s,
            detector=req.detector, threshold=req.threshold,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return analysis.summary()


def _parse_upload(file: UploadFile, metadata: dict | None = None):
    # Reuse the benchmark's content-sniffing parser for CSV, candump, and HCRL TXT.
    with tempfile.TemporaryDirectory(prefix="canalyst-upload-") as directory:
        name = Path(file.filename or "capture.csv").name
        path = Path(directory) / name
        raw = file.file.read()
        if not raw.strip():
            raise ValueError("Capture is empty")
        path.write_bytes(raw)
        if metadata is not None:
            if "injection_interval" in metadata:
                metadata = {path.stem: metadata}
            if raw.lstrip().startswith(b"(") and path.stem not in metadata:
                raise ValueError(f"ROAD metadata has no entry for capture {path.stem}")
            (path.parent / "capture_metadata.json").write_text(json.dumps(metadata))
        return loader.load_auto(str(path))


@app.post("/api/analyze/upload")
def analyze_upload(file: UploadFile = File(...),
                   baseline_file: UploadFile | None = File(None),
                   metadata_file: UploadFile | None = File(None),
                   detector: Literal["rule", "forest"] = "rule",
                   window_s: float = Query(0.5, gt=0.05, le=5),
                   stride_s: float = Query(0.25, gt=0.01, le=5),
                   threshold: float = Query(0.55, ge=0.05, le=0.99),
                   baseline_s: float | None = Query(None, gt=0)) -> dict:
    started = time.perf_counter()
    try:
        metadata = json.loads(metadata_file.file.read()) if metadata_file else None
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("ROAD metadata must be a JSON object")
        df = _parse_upload(file, metadata)
        normal = _parse_upload(baseline_file) if baseline_file else None
        traffic_columns = ["timestamp", "can_id", "dlc", "data"]
        if normal is not None and df[traffic_columns].equals(normal[traffic_columns]):
            raise ValueError("Evaluation capture and baseline must be separate traffic")
        parse_seconds = time.perf_counter() - started
        analysis = pipeline.run_analysis(df, source=file.filename or "upload",
            params={"uploaded": True}, detector=detector, threshold=threshold,
            window_s=window_s, stride_s=stride_s, baseline_s=baseline_s, baseline_df=normal)
        analysis.timing_s["parse"] = round(parse_seconds, 4)
        analysis.timing_s["total"] = round(time.perf_counter() - started, 4)
        return analysis.summary()
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise HTTPException(400, f"Could not analyze capture: {exc}") from exc


@app.get("/api/analysis/{analysis_id}/summary")
def summary(analysis_id: str) -> dict:
    return _get(analysis_id).summary()


@app.get("/api/analysis/{analysis_id}/timeline")
def timeline(analysis_id: str, max_points: int = Query(2000, ge=100, le=20000)) -> dict:
    return _get(analysis_id).timeline(max_points=max_points)


@app.get("/api/analysis/{analysis_id}/ids")
def ids(analysis_id: str, limit: int = Query(80, ge=1, le=1000)) -> list[dict]:
    return _get(analysis_id).id_table(limit=limit)


@app.get("/api/analysis/{analysis_id}/ids/{can_id}/series")
def id_series(analysis_id: str, can_id: str, bucket_s: float = Query(0.5, ge=0.05, le=60)) -> dict:
    a = _get(analysis_id)
    try:
        cid = int(can_id, 16) if can_id.lower().startswith("0x") else int(can_id, 16)
    except ValueError:
        raise HTTPException(400, "can_id must be hex, for example 0x2C0")
    return a.id_series(cid, bucket_s=bucket_s)


@app.get("/api/analysis/{analysis_id}/alerts")
def alerts(analysis_id: str, explainer: str | None = None) -> list[dict]:
    return _get(analysis_id).alert_list(include_explanations=True,
                                        explainer=get_explainer(explainer))


@app.get("/api/analysis/{analysis_id}/alerts/{alert_id}")
def alert_detail(analysis_id: str, alert_id: int, explainer: str | None = None) -> dict:
    a = _get(analysis_id)
    if alert_id < 0 or alert_id >= len(a.alerts):
        raise HTTPException(404, "Alert not found")
    ex = get_explainer(explainer)
    exp = a.cached_explanation(alert_id, ex)
    return {
        "alert": a.alert_item(alert_id, include_explanations=True, explainer=ex),
        "evidence": a.evidence_for(alert_id),
        "explanation": exp.to_json() if exp else None,
    }


@app.post("/api/analysis/{analysis_id}/alerts/{alert_id}/explain")
def explain_alert(analysis_id: str, alert_id: int, req: ExplainRequest) -> dict:
    a = _get(analysis_id)
    if alert_id < 0 or alert_id >= len(a.alerts):
        raise HTTPException(404, "Alert not found")
    explainer = get_explainer(req.explainer)
    exp = a.explain(alert_id, explainer, force=req.force)
    return {"alert_id": alert_id, "explanation": exp.to_json(),
            "evidence": a.evidence_for(alert_id)}


@app.post("/api/analysis/{analysis_id}/explain-all")
def explain_all(analysis_id: str, req: ExplainRequest) -> dict:
    a = _get(analysis_id)
    explainer = get_explainer(req.explainer)
    for alert in a.alerts:
        a.explain(alert.alert_id, explainer, force=req.force)
    return {"explained": len(a.alerts), "explainer": explainer.name}


@app.get("/api/analysis/{analysis_id}/metrics")
def analysis_metrics(analysis_id: str, explainer: str | None = None) -> dict:
    a = _get(analysis_id)
    return pipeline.evaluation_report(a, get_explainer(explainer), generate=False)


@app.get("/api/analysis/{analysis_id}/baseline")
def baseline(analysis_id: str) -> dict:
    return _get(analysis_id).baseline.to_json()


@app.post("/api/analysis/{analysis_id}/ask")
def ask(analysis_id: str, req: AskRequest) -> dict:
    a = _get(analysis_id)
    explainer = get_explainer(req.explainer)
    context = a.ask_context(explainer)
    return {"question": req.question, "answer": explainer.answer(req.question, context),
            "explainer": explainer.name}



# --------------------------------------------------------------------------
# Saved benchmarks (Evaluation tab)
# --------------------------------------------------------------------------

@app.get("/api/benchmark/detection")
def benchmark_detection() -> dict:
    data = benchmarks.detection()
    if data is None:
        raise HTTPException(404, "No detection benchmark saved. Run python -m scripts.benchmark.")
    return data


@app.get("/api/benchmark/explainers")
def benchmark_explainers() -> dict:
    return benchmarks.explainers()


@app.get("/api/benchmark/explainers/{set_name}/compare")
def benchmark_compare(set_name: str, a: str, b: str) -> dict:
    try:
        return benchmarks.compare(set_name, a, b)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]))


@app.get("/api/benchmark/explainers/{set_name}/packets", response_class=PlainTextResponse)
def benchmark_packets(set_name: str) -> str:
    try:
        return benchmarks.packets(set_name)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]))


@app.post("/api/benchmark/explainers/{set_name}/submit")
async def benchmark_submit(set_name: str, name: str = Form(...), description: str = Form(""),
                           file: UploadFile = File(...)) -> dict:
    raw = await file.read(benchmarks.MAX_SUBMISSION_BYTES + 1)
    try:
        return benchmarks.submit(set_name, name, raw, description)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]))
    except benchmarks.SubmissionError as exc:
        raise HTTPException(400, str(exc))
