"""CANalyst API.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""
from __future__ import annotations

import io
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import loader, pipeline
from .llm import get_explainer
from .pipeline import STORE

app = FastAPI(title="CANalyst API", version="0.1.0",
              description="LLM-assisted analysis of CAN bus attacks")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class SyntheticRequest(BaseModel):
    duration_s: float = Field(120.0, ge=20.0, le=900.0)
    seed: int = 7
    attacks: list[str] = ["dos", "fuzzing", "spoofing", "masquerade"]
    window_s: float = Field(0.5, gt=0.05, le=5.0)
    stride_s: float = Field(0.25, gt=0.01, le=5.0)
    detector: str = "rule"
    threshold: float = Field(0.55, ge=0.05, le=0.99)


class AskRequest(BaseModel):
    question: str


class ExplainRequest(BaseModel):
    explainer: str | None = None
    force: bool = False


def _get(analysis_id: str):
    a = STORE.get(analysis_id)
    if a is None:
        raise HTTPException(404, "Analysis not found. Run a new analysis.")
    return a


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "explainer": get_explainer().name, "analyses": STORE.list()}


@app.post("/api/analyze/synthetic")
def analyze_synthetic(req: SyntheticRequest) -> dict:
    analysis = pipeline.run_synthetic(
        duration_s=req.duration_s, seed=req.seed, attacks=req.attacks,
        window_s=req.window_s, stride_s=req.stride_s,
        detector=req.detector, threshold=req.threshold,
    )
    return analysis.summary()


@app.post("/api/analyze/upload")
async def analyze_upload(file: UploadFile = File(...), detector: str = "rule",
                         window_s: float = 0.5, stride_s: float = 0.25) -> dict:
    raw = (await file.read()).decode("utf-8", errors="replace")
    name = (file.filename or "").lower()
    try:
        if "road" in name:
            df = loader.load_road(io.StringIO(raw))
        else:
            head = raw.split("\n", 1)[0].lower()
            has_header = "timestamp" in head or "can id" in head
            df = loader.load_carhacking(io.StringIO(raw), has_header=has_header)
    except Exception as exc:
        raise HTTPException(400, f"Could not parse {file.filename}: {exc}")
    analysis = pipeline.run_analysis(df, source=file.filename or "upload",
                                     params={"uploaded": True}, detector=detector,
                                     window_s=window_s, stride_s=stride_s)
    return analysis.summary()


@app.get("/api/analysis/{analysis_id}/summary")
def summary(analysis_id: str) -> dict:
    return _get(analysis_id).summary()


@app.get("/api/analysis/{analysis_id}/timeline")
def timeline(analysis_id: str) -> dict:
    return _get(analysis_id).timeline()


@app.get("/api/analysis/{analysis_id}/ids")
def ids(analysis_id: str, limit: int = 80) -> list[dict]:
    return _get(analysis_id).id_table(limit=limit)


@app.get("/api/analysis/{analysis_id}/ids/{can_id}/series")
def id_series(analysis_id: str, can_id: str, bucket_s: float = 0.5) -> dict:
    a = _get(analysis_id)
    try:
        cid = int(can_id, 16) if can_id.lower().startswith("0x") else int(can_id, 16)
    except ValueError:
        raise HTTPException(400, "can_id must be hex, for example 0x2C0")
    return a.id_series(cid, bucket_s=bucket_s)


@app.get("/api/analysis/{analysis_id}/alerts")
def alerts(analysis_id: str) -> list[dict]:
    return _get(analysis_id).alert_list(include_explanations=True)


@app.get("/api/analysis/{analysis_id}/alerts/{alert_id}")
def alert_detail(analysis_id: str, alert_id: int) -> dict:
    a = _get(analysis_id)
    if alert_id < 0 or alert_id >= len(a.alerts):
        raise HTTPException(404, "Alert not found")
    return {
        "alert": a.alert_list(include_explanations=True)[alert_id],
        "evidence": a.evidence_for(alert_id),
        "explanation": (a.explanations[alert_id].to_json()
                        if alert_id in a.explanations else None),
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
    pipeline.explain_all(a, explainer)
    return {"explained": len(a.explanations), "explainer": explainer.name}


@app.get("/api/analysis/{analysis_id}/metrics")
def analysis_metrics(analysis_id: str, explainer: str | None = None) -> dict:
    a = _get(analysis_id)
    return pipeline.evaluation_report(a, get_explainer(explainer))


@app.get("/api/analysis/{analysis_id}/baseline")
def baseline(analysis_id: str) -> dict:
    return _get(analysis_id).baseline.to_json()


@app.post("/api/analysis/{analysis_id}/ask")
def ask(analysis_id: str, req: AskRequest) -> dict:
    a = _get(analysis_id)
    explainer = get_explainer()
    context = {
        "summary": a.summary(),
        "alerts": a.alert_list(include_explanations=True),
        "baseline": a.baseline.to_json(),
    }
    return {"question": req.question, "answer": explainer.answer(req.question, context),
            "explainer": explainer.name}
