"""The can-train-and-test loader and its place in the protocol."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import datasets, loader  # noqa: E402
from scripts import evaluate_midterm  # noqa: E402

CSV = """timestamp,arbitration_id,data_field,attack
1672531200.0,1E5,460196E001FE6701,0
1672531200.000023,0C1,0010,1
1672531200.003365,7DF,,0
"""


@pytest.fixture
def ctt_file(tmp_path):
    p = tmp_path / "can-train-and-test" / "set_01" / "test_01_known_vehicle_known_attack" / "DoS-3.csv"
    p.parent.mkdir(parents=True)
    p.write_text(CSV)
    return p


def test_load_ctt_parses_ids_payloads_and_per_frame_labels(ctt_file):
    df = loader.load_ctt(str(ctt_file))
    assert df["can_id"].tolist() == [0x1E5, 0x0C1, 0x7DF]
    assert df["data"].tolist() == [[0x46, 0x01, 0x96, 0xE0, 0x01, 0xFE, 0x67, 0x01], [0x00, 0x10], []]
    assert df["dlc"].tolist() == [8, 2, 0]
    assert df["label"].tolist() == [0, 1, 0]
    assert df["attack_type"].tolist() == ["normal", "dos", "normal"]
    assert df["timestamp"].iloc[0] == 0.0


def test_load_auto_recognizes_the_header(ctt_file):
    assert loader.load_auto(str(ctt_file)).attrs["source"] == "can-train-and-test"


@pytest.mark.parametrize("stem, family, label", [
    ("DoS-3", "DoS", "dos"), ("force-neutral-4", "force-neutral", "spoofing"),
    ("rpm-accessory-1", "rpm-accessory", None), ("fuzzing-2", "fuzzing", "fuzzing"),
    ("standstill-1", "standstill", "spoofing"), ("speed-3", "speed", "spoofing"),
])
def test_file_families_map_to_the_explainer_vocabulary(stem, family, label):
    assert loader.ctt_family(stem) == family
    assert loader.CTT_ATTACK_TYPES.get(family) == label


def test_capture_counts_rows_without_the_header(ctt_file, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_midterm, "BACKEND", tmp_path)
    df, rec = evaluate_midterm.capture(ctt_file, tmp_path / "out" / "ctt")
    assert len(df) == rec["frame_count"] == 3


def test_a_sliced_capture_keeps_the_header_and_a_vehicle_prefix(ctt_file, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_midterm, "BACKEND", tmp_path)
    df, rec = evaluate_midterm.capture(ctt_file, tmp_path / "out" / "ctt", start=0.0, stop=0.001)
    assert len(df) == 2
    assert "set_01_DoS-3_0_0.001" in rec["selected_input"]


def test_every_vehicle_has_one_reference_and_disjoint_roles():
    for vehicle, (set_name, ref, ambient, subsets) in datasets.CTT_VEHICLES.items():
        assert ref != ambient
        assert all(sub.startswith("test_") for sub in subsets), "attacks come from test subsets only"
