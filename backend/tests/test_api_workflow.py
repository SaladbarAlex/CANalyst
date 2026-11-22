"""Regression coverage for dashboard side effects, upload parity and leakage."""
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app import loader, main, metrics, pipeline, synth
from app.llm import MockExplainer


@pytest.fixture(scope="module")
def analysis():
    return pipeline.run_synthetic(duration_s=40)


def test_metrics_get_never_generates_model_calls(analysis, monkeypatch):
    class NoCalls(MockExplainer):
        name = "no_calls"

        def explain(self, evidence):
            pytest.fail("GET metrics must not call a model")

    monkeypatch.setattr(main, "get_explainer", lambda _: NoCalls())
    result = main.analysis_metrics(analysis.analysis_id)
    assert result["explained_alerts"] == 0
    assert result["classification"]["accuracy"] is None
    assert result["total_alerts"] == len(analysis.alerts)


def test_concurrent_cache_requests_make_one_call(analysis):
    class Counting(MockExplainer):
        name = "counting"
        calls = 0

        def explain(self, evidence):
            self.calls += 1
            return super().explain(evidence)

    ex = Counting()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: analysis.explain(0, ex), range(4)))
    assert ex.calls == 1
    assert all(r is results[0] for r in results)


def test_upload_sniffs_candump_and_road_metadata():
    file = UploadFile(filename="attack.log", file=io.BytesIO(
        b"(100.0) can0 123#0102\n(100.5) can0 123#0203\n(101.0) can0 124#0203\n"))
    df = main._parse_upload(file, {"attack": {"injection_interval": [0.4, 0.6], "injection_id": "123"}})
    assert df.label.tolist() == [0, 1, 0]
    assert df.attrs["source"] == "road"


def test_upload_sniffs_normal_hcrl_txt():
    file = UploadFile(filename="normal.txt", file=io.BytesIO(
        b"Timestamp: 100.0 ID: 0350 000 DLC: 2 05 28\nTimestamp: 100.2 ID: 0350 000 DLC: 2 06 28\n"))
    assert main._parse_upload(file).data.tolist() == [[5, 40], [6, 40]]


def test_same_road_capture_cannot_train_itself_when_metadata_changes_labels():
    raw = b"(100.0) can0 123#0102\n(101.0) can0 123#0203\n(102.0) can0 123#0304\n(103.0) can0 123#0405\n"
    response = TestClient(main.app).post("/api/analyze/upload", files={
        "file": ("capture.log", raw), "baseline_file": ("normal.log", raw),
        "metadata_file": ("capture_metadata.json", json.dumps({"capture": {
            "injection_interval": [1, 2], "injection_id": "123"}})),
    })
    assert response.status_code == 400
    assert "must be separate traffic" in response.json()["detail"]


def test_metrics_exclude_baseline_crossing_window():
    windows = pd.DataFrame({"start": [0., .75, 1.], "end": [.5, 1.25, 1.5],
                            "flagged": [True, True, False], "label": [0, 0, 0], "attack_type": ["normal"] * 3})
    result = metrics.detection_metrics(windows, skip_until=1.)
    assert result["windows_evaluated"] == 1
    assert result["false_positive"] == 0


def test_ask_params_hide_filename_labels(analysis):
    analysis.params["csv"] = "/data/DoS_dataset.csv"
    analysis.params["baseline_path"] = "/private/normal.txt"
    assert "csv" not in analysis.ask_context()["summary"]["params"]
    assert "baseline_path" not in analysis.ask_context()["summary"]["params"]


def test_contaminated_baseline_rejected():
    normal = loader.load_synthetic(duration_s=20, attacks=[])
    normal.loc[0, "label"] = 1
    with pytest.raises(ValueError, match="attack-free"):
        pipeline.run_analysis(normal, source="test", params={}, baseline_df=normal)


def test_normal_only_capture_is_labeled():
    result = pipeline.run_synthetic(duration_s=20, attacks=[])
    assert result.summary()["labeled"]
    assert result.summary()["metrics"]["labeled"]
    assert result.summary()["params"]["attacks"] == []


def test_cli_pipeline_cannot_evaluate_its_external_training_capture():
    normal = loader.load_synthetic(duration_s=20, attacks=[])
    with pytest.raises(ValueError, match="must be separate traffic"):
        pipeline.run_analysis(normal, source="normal", params={}, baseline_df=normal.copy())


def test_short_demo_really_injects_every_selected_attack():
    data = synth.generate(duration_s=20, attacks=synth.ATTACK_TYPES)
    assert set(data.loc[data.label == 1, "attack_type"]) == set(synth.ATTACK_TYPES)
    assert not data.loc[data.timestamp < data.attrs["benign_prefix_s"], "label"].any()
    assert all(0 <= iv["start"] < iv["end"] <= 20 for iv in data.attrs["attack_intervals"])


@pytest.mark.parametrize("settings", [
    {"duration_s": 20, "window_s": 5, "detector": "rule"},
    {"duration_s": 20, "window_s": 1, "stride_s": 1, "detector": "forest"},
])
def test_incompatible_demo_settings_return_actionable_validation(settings):
    response = TestClient(main.app).post("/api/analyze/synthetic", json=settings)
    assert response.status_code == 422
    assert "baseline" in response.json()["detail"].lower()


def test_timeline_keeps_brief_extreme_and_bounds_response(analysis):
    from dataclasses import replace
    windows = pd.concat([analysis.windows] * 100, ignore_index=True)
    windows["score"] = 0.1
    windows.loc[1234, "score"] = 0.99
    view = replace(analysis, windows=windows).timeline(max_points=100)
    assert len(view["points"]) <= 100
    assert view["downsampled"]
    assert max(p["score"] for p in view["points"]) == 0.99
