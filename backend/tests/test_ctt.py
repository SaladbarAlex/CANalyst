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


# --------------------------------------------------------------------------
# TU Eindhoven: labels come from the difference with the benign testing.log
# --------------------------------------------------------------------------

BASE = ["(100.000000) slcan0 0F1#1C01", "(100.010000) slcan0 1A1#0000", "(100.020000) slcan0 0F1#1C02"]


@pytest.fixture
def tue_car(tmp_path):
    car = tmp_path / "tu-eindhoven-can-v2" / "OpelAstra"
    car.mkdir(parents=True)
    (car / "README").write_text("readme")
    (car / "testing.log").write_text("\n".join(BASE) + "\n")
    return car


def test_tue_injected_frames_are_the_lines_missing_from_testing(tue_car):
    lines = BASE[:1] + ["(100.005000) slcan0 111#FFFF"] + BASE[1:]
    (tue_car / "fuzzing_canid.log").write_text("\n".join(lines) + "\n")
    df = loader.load_auto(str(tue_car / "fuzzing_canid.log"))
    assert df["label"].tolist() == [0, 1, 0, 0]
    assert df.loc[df.label == 1, "can_id"].tolist() == [0x111]
    assert set(df.loc[df.label == 1, "attack_type"]) == {"fuzzing"}


def test_tue_changed_payloads_count_as_attack_frames(tue_car):
    lines = [BASE[0], "(100.010000) slcan0 1A1#FFFF", BASE[2]]
    (tue_car / "fuzzing_payload.log").write_text("\n".join(lines) + "\n")
    df = loader.load_auto(str(tue_car / "fuzzing_payload.log"))
    assert df["label"].tolist() == [0, 1, 0]
    assert set(df.loc[df.label == 1, "attack_type"]) == {"masquerade"}


def test_tue_repairs_a_trailing_backslash_and_counts_it(tue_car):
    lines = [BASE[0] + "\\", BASE[1], "(100.015000) slcan0 222#FFFF", BASE[2]]
    (tue_car / "fuzzing_canid.log").write_text("\n".join(lines) + "\n")
    df = loader.load_auto(str(tue_car / "fuzzing_canid.log"))
    assert df.attrs["repaired_lines"] == 1
    assert df["label"].tolist() == [0, 0, 1, 0]


def test_tue_benign_capture_has_no_attack_frames(tue_car):
    df = loader.load_auto(str(tue_car / "testing.log"))
    assert df["label"].sum() == 0 and set(df["attack_type"]) == {"normal"}
