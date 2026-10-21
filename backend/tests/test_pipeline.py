"""Smoke and behavior tests. Run with: pytest -q (from the backend folder)."""
from __future__ import annotations

import io
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import features, loader, pipeline, synth  # noqa: E402
from app.llm import MockExplainer  # noqa: E402


@pytest.fixture(scope="module")
def analysis():
    return pipeline.run_synthetic(duration_s=120, seed=1,
                                  attacks=["dos", "fuzzing", "spoofing", "masquerade"])


def test_generator_labels_every_attack():
    df = synth.generate(duration_s=90, seed=3, attacks=["dos", "spoofing"])
    assert df["label"].max() == 1
    assert set(df.loc[df["label"] == 1, "attack_type"]) == {"dos", "spoofing"}
    # The baseline stretch must stay clean or the detector learns the attack.
    prefix = df[df["timestamp"] < df.attrs["benign_prefix_s"]]
    assert prefix["label"].max() == 0


def test_baseline_learns_every_bus_id():
    df = synth.generate(duration_s=90, seed=4, attacks=["dos"])
    bl = features.learn_baseline(df, 30.0)
    assert bl.known_ids == {m.can_id for m in synth.BUS}
    assert bl.total_rate > 100


def test_detection_quality(analysis):
    m = analysis.summary()["metrics"]
    assert m["recall"] >= 0.85, m
    assert m["precision"] >= 0.8, m


def test_every_injected_interval_produces_an_alert(analysis):
    for iv in analysis.df.attrs["attack_intervals"]:
        assert any(a.start < iv["end"] and a.end > iv["start"] for a in analysis.alerts), iv


def test_explanations_are_grounded(analysis):
    ex = MockExplainer()
    for alert in analysis.alerts:
        exp = analysis.explain(alert.alert_id, ex)
        valid = {i["id"] for i in analysis.evidence_for(alert.alert_id)["items"]}
        assert exp.claims, "an explanation with no claims cites nothing"
        for claim in exp.claims:
            assert claim["cites"], claim
            assert set(claim["cites"]) <= valid, claim


def test_evidence_stays_small(analysis):
    """The LLM must never receive a whole log."""
    ev = analysis.evidence_for(0)
    assert len(ev["items"]) <= 12
    assert len(ev["sample_frames"]) <= 6


@pytest.mark.parametrize("source", ["road", "car-hacking", None])
def test_real_or_unverified_ids_do_not_inherit_synthetic_signal_names(analysis, source):
    """A real ID can collide with a generator ID without sharing its meaning."""
    df = analysis.df.copy()
    df.attrs = {**df.attrs, "source": source}
    real = replace(analysis, df=df, evidence_cache={}, explanations={})
    collided = [row for row in real.id_table() if int(row["can_id"], 16) in synth.ID_INFO]
    assert collided, "Fixture must contain a real/synthetic ID collision"
    assert all(row["name"] == "unknown" and row["function"] == "unknown" for row in collided)
    details = [item for alert in real.alerts for item in real.evidence_for(alert.alert_id)["items"]
               if item["kind"] in {"id_stats", "missing_id"}]
    assert details
    assert all(item["detail"]["function"] is None for item in details)
    assert all("unknown" in item["text"] for item in details)


def test_verified_synthetic_ids_keep_generator_signal_names(analysis):
    known = [row for row in analysis.id_table() if int(row["can_id"], 16) in synth.ID_INFO]
    assert known
    for row in known:
        info = synth.ID_INFO[int(row["can_id"], 16)]
        assert row["name"] == info["name"]
        assert row["function"] == info["function"]
    details = [item for alert in analysis.alerts for item in analysis.evidence_for(alert.alert_id)["items"]
               if item["kind"] == "id_stats" and int(item["detail"]["can_id"], 16) in synth.ID_INFO]
    assert details
    for item in details:
        assert item["detail"]["function"] == synth.ID_INFO[int(item["detail"]["can_id"], 16)]["function"]


def test_carhacking_round_trip(tmp_path):
    df = synth.generate(duration_s=60, seed=9, attacks=["dos"])
    path = tmp_path / "log.csv"
    synth.to_carhacking_csv(df, str(path))
    back = loader.load_carhacking(str(path))
    assert len(back) == len(df)
    assert back["label"].sum() == df["label"].sum()
    assert list(back.iloc[0]["data"]) == list(df.iloc[0]["data"])


def test_road_loader_parses_hex_payloads():
    csv = io.StringIO("Label,Time,ID,Data\n0,0.0,0A0,1122334455667788\n1,0.01,2C0,00FF00FF\n")
    df = loader.load_road(csv)
    assert list(df["can_id"]) == [0x0A0, 0x2C0]
    assert list(df.iloc[0]["data"]) == [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]
    assert df["label"].tolist() == [0, 1]


def test_forest_detector_runs():
    a = pipeline.run_synthetic(duration_s=90, seed=2, attacks=["dos", "fuzzing"],
                               detector="forest")
    assert a.detector == "forest"
    assert len(a.alerts) >= 1
