from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.state_detector import StateDetector, split_frames


def capture(value=1):
    timestamps = np.arange(0, 20, .01)
    return pd.DataFrame({"timestamp": timestamps, "can_id": 0x100, "dlc": 1,
                         "data": [[value] for _ in timestamps], "label": 0, "attack_type": "normal"})


def test_normal_only_split_and_window_scale_profiles():
    normal = [capture(), capture(2)]
    detector = StateDetector().fit(normal)
    assert detector.calibration["normal_profiles"] == 2
    for df in normal:
        windows, _ = detector.run(df)
        assert not windows.flagged.any()
    for fit_count, cal_count in zip(detector.calibration["training_windows_per_capture"],
                                   detector.calibration["calibration_windows_per_capture"]):
        assert fit_count > cal_count >= 5
    bad = normal[0].copy()
    bad.loc[0, "label"] = 1
    with pytest.raises(ValueError, match="normal"):
        split_frames([bad])


def test_persistent_payload_novelty_detected_without_using_labels():
    detector = StateDetector().fit([capture()])
    changed = capture(255)
    unlabeled, _ = detector.run(changed)
    changed["label"], changed["attack_type"] = 1, "masquerade"
    labeled, _ = detector.run(changed)
    assert unlabeled.flagged.all()
    assert unlabeled.score.tolist() == labeled.score.tolist()
    assert unlabeled.components.iloc[0]["payload_novelty"] > .5


def test_unknown_ids_and_fixed_scores():
    detector = StateDetector().fit([capture()])
    unknown = capture()
    unknown["can_id"] = 0x111
    scored, _ = detector.run(unknown)
    assert scored.flagged.all()
    assert scored.components.iloc[0]["unknown_rate"] > .5
