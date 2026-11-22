import json

from scripts import evaluate_midterm


def test_road_nonzero_slice_preserves_original_attack_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_midterm, "BACKEND", tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "capture.log"
    source.write_text("\n".join(f"({t}) can0 123#0102" for t in [100, 109.7, 110.2, 111.2, 112.5, 114]) + "\n")
    (raw / "capture_metadata.json").write_text(json.dumps({"capture": {
        "injection_interval": [10, 12], "injection_id": "123"}}))
    result, provenance = evaluate_midterm.capture(source, tmp_path / "out/run/road", start=9.5, stop=13)
    assert result.label.tolist() == [0, 1, 1, 0]
    assert abs(provenance["source_relative_selected_origin_s"] - 9.7) < 1e-8
    # Original metadata is immutable; only the derivative slice is rebased.
    assert json.loads((raw / "capture_metadata.json").read_text())["capture"]["injection_interval"] == [10, 12]


def test_open_ended_slice_honors_start(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_midterm, "BACKEND", tmp_path)
    source = tmp_path / "capture.log"
    source.write_text("\n".join(f"({t}) can0 123#0102" for t in [100, 101, 102, 103]) + "\n")
    result, provenance = evaluate_midterm.capture(source, tmp_path / "out/run/road", start=2)
    assert len(result) == 2
    assert result.timestamp.tolist() == [0, 1]
    assert provenance["source_relative_selected_origin_s"] == 2
