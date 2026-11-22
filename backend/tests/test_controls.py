"""Regression coverage for unbiased detector training and control features."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import features, loader
from app.detector import ForestDetector, RuleDetector, get_detector


def normal_capture(duration=20.0):
    ts = np.arange(0, duration, 0.01)
    return pd.DataFrame({"timestamp": ts, "can_id": 0x100, "dlc": 1,
                         "data": [[int(i % 16)] for i in range(len(ts))],
                         "label": 0, "attack_type": "normal"})


@pytest.fixture(scope="module")
def normal_windows():
    df = normal_capture()
    baseline = features.learn_baseline(df, float("inf"))
    return baseline, features.extract_windows(df, baseline)


def test_forest_refuses_implicit_or_insufficient_training(normal_windows):
    baseline, windows = normal_windows
    det = ForestDetector(baseline)
    with pytest.raises(ValueError, match="Fit IsolationForest"):
        det.run(windows)
    with pytest.raises(ValueError, match="normal training"):
        det.run(windows, fit_until=0)
    with pytest.raises(ValueError, match="longer normal"):
        det.fit(windows.iloc[:10])
    attacked = windows.copy()
    attacked.loc[0, "label"] = 1
    with pytest.raises(ValueError, match="labeled attacks"):
        det.fit(attacked)


def test_forest_scores_do_not_depend_on_other_evaluation_windows(normal_windows):
    baseline, windows = normal_windows
    det = ForestDetector(baseline).fit(windows)
    query = windows.iloc[[0]].copy()
    query["max_rate_ratio"] = 3.0
    single, _ = det.run(query)
    extreme = query.copy()
    extreme[features.FEATURE_COLUMNS] = 100000.0
    batch, _ = det.run(pd.concat([query, extreme], ignore_index=True))
    assert single.iloc[0].score == batch.iloc[0].score
    assert single.iloc[0].flagged == batch.iloc[0].flagged
    assert det.calibration["training_end"] <= det.calibration["calibration_start"]


def test_forest_honors_requested_threshold(normal_windows):
    baseline, windows = normal_windows
    det = get_detector("forest", baseline, threshold=1).fit(windows)
    scored, _ = det.run(windows)
    assert not scored.flagged.any()
    det.threshold = 0
    scored, _ = det.run(windows)
    assert scored.flagged.all()


def test_periodic_normal_sender_is_not_jitter_collapse(normal_windows):
    baseline, windows = normal_windows
    scored, _ = RuleDetector(baseline).run(windows)
    assert windows.n_jitter_collapses.sum() == 0
    assert all(row[0x100]["jitter_ratio"] >= 1 for row in windows.per_id)
    assert not scored.flagged.any()
    assert "n_jitter_collapses" in features.FEATURE_COLUMNS


def test_zero_length_payload_has_finite_bitflip():
    assert features.bitflip_rate([[], [], []]) == 0.0


def test_capture_join_does_not_create_interarrival_measurements():
    first = normal_capture(2)
    second = normal_capture(2)
    second["timestamp"] *= 2
    joined = loader.concat_captures([first, second])
    bl = features.learn_baseline(joined, float("inf"))
    expected = np.concatenate([np.diff(first.timestamp), np.diff(second.timestamp)])
    assert bl.iat_mean[0x100] == pytest.approx(expected.mean())
    assert bl.iat_std[0x100] == pytest.approx(expected.std())
    assert bl.total_rate == pytest.approx(len(joined) / (first.timestamp.max() + second.timestamp.max()))
    windows = features.extract_windows(joined, bl)
    boundary = joined[joined._capture_id == 1].timestamp.min()
    assert not ((windows.start < boundary - 0.01) & (windows.end > boundary)).any()


def test_baseline_rejects_attack_contamination():
    df = normal_capture()
    df.loc[0, "label"] = 1
    with pytest.raises(ValueError, match="labeled attack"):
        features.learn_baseline(df, float("inf"))
    with pytest.raises(ValueError, match="labeled attack"):
        loader.concat_captures([df])


def test_feature_order_independent_and_parameters_validated(normal_windows):
    baseline, windows = normal_windows
    shuffled = normal_capture().sample(frac=1, random_state=4)
    actual = features.extract_windows(shuffled, baseline)
    pd.testing.assert_frame_equal(actual, windows)
    for window_s, stride_s in [(0, .25), (.5, 0), (.5, 1), (float("nan"), .25)]:
        with pytest.raises(ValueError):
            features.extract_windows(shuffled, baseline, window_s, stride_s)


def test_loader_respects_dlc_and_rejects_unrecognized_labels():
    import io
    text = "Timestamp,CAN ID,DLC,DATA0,DATA1,Flag\n0,100,1,AB,FF,F\n"
    frame = loader.load_carhacking(io.StringIO(text))
    assert frame.iloc[0].data == [0xAB]
    assert loader.load_carhacking(io.StringIO(text.replace(",F\n", ",R\n"))).label.tolist() == [0]
    with pytest.raises(ValueError, match="traffic label"):
        loader.load_carhacking(io.StringIO(text.replace(",F\n", ",maybe\n")))
    with pytest.raises(ValueError, match="traffic label"):
        loader.load_road(io.StringIO("Label,Time,ID,Data\nunknown,0,100,AB\n"))
    with pytest.raises(ValueError):
        loader.load_road(io.StringIO("Label,Time,ID,Data\n0,0,100,ABC\n"))


def test_loader_rejects_silently_dropped_candump_frames(tmp_path):
    path = tmp_path / "capture.log"
    path.write_text("(0.0) can0 100#AB\n(0.1) can0 100##1AB\n")
    with pytest.raises(ValueError, match="line 2"):
        loader.load_candump(str(path))
    path.write_text("garbage\n(0.0) can0 100#AB\n")
    with pytest.raises(ValueError, match="line 1"):
        loader.load_candump(str(path))
    path.write_text("(0.0) can0 100#\n")
    assert loader.load_candump(str(path)).iloc[0].dlc == 0


def test_sweep_reuses_only_matching_baseline_and_input(tmp_path, monkeypatch):
    from scripts import sweep
    from types import SimpleNamespace
    log = tmp_path / "capture.csv"
    log.write_text("Timestamp,CAN ID,DLC,DATA0,Flag\n0,100,1,AB,F\n.1,100,1,CD,F\n")
    calls = []
    def fake_analysis(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(baseline_end=0, windows=pd.DataFrame({
            "start": [0], "end": [.5], "label": [0], "attack_type": ["normal"],
            "score": [.1], "components": [{}]}))
    monkeypatch.setattr(sweep.pipeline, "run_analysis", fake_analysis)
    baseline = normal_capture(1)
    cache = tmp_path / "cache"
    sweep.score_log(str(log), baseline, cache, "test")
    sweep.score_log(str(log), baseline, cache, "test")
    assert len(calls) == 1
    changed = baseline.copy()
    changed.loc[0, "can_id"] = 0x101
    sweep.score_log(str(log), changed, cache, "test")
    assert len(calls) == 2
    log.write_text(log.read_text().replace("CD", "CE"))
    sweep.score_log(str(log), changed, cache, "test")
    assert len(calls) == 3


def test_explicit_calibration_rejects_overlap_and_attacks(normal_windows):
    baseline, windows = normal_windows
    detector = ForestDetector(baseline)
    with pytest.raises(ValueError, match="overlap"):
        detector.fit(windows.iloc[:50], windows.iloc[40:])
    calibration = windows.iloc[60:].copy()
    calibration.loc[calibration.index[0], "label"] = 1
    with pytest.raises(ValueError, match="labeled attack"):
        detector.fit(windows.iloc[:50], calibration)
    detector.fit(windows.iloc[:50], windows.iloc[60:])
    assert detector.calibration["method"] == "normal_explicit_holdout_sigmoid_v1"


def test_per_capture_split_represents_each_normal_state():
    from scripts.evaluate_detectors import split_by_capture
    normal = loader.concat_captures([normal_capture(), normal_capture()])
    bl = features.learn_baseline(normal, float("inf"))
    windows = features.extract_windows(normal, bl)
    training, calibration = split_by_capture(windows, normal)
    for _, group in normal.groupby("_capture_id"):
        lo, hi = group.timestamp.min(), group.timestamp.max()
        fit = training[(training.start >= lo) & (training.end <= hi)]
        cal = calibration[(calibration.start >= lo) & (calibration.end <= hi)]
        assert len(fit) >= 10 and len(cal) >= 5
        assert fit.end.max() <= cal.start.min()
    ForestDetector(bl).fit(training, calibration)


def test_sweep_report_rejects_unversioned_cached_results(tmp_path):
    from scripts import sweep
    pd.DataFrame({"score": [.5], "label": [0]}).to_csv(tmp_path / "old__log.csv.gz", index=False)
    with pytest.raises(ValueError, match="provenance"):
        sweep.report(tmp_path, [.55])


def test_saved_scores_preserve_threshold_decisions(normal_windows):
    baseline, windows = normal_windows
    row = windows.iloc[[0]].copy()
    row["max_rate_ratio"] = 1.98245  # score .5499565 rounds up to .5500
    scored, _ = RuleDetector(baseline, threshold=.55).run(row)
    assert scored.iloc[0].score < .55
    assert not scored.iloc[0].flagged
    assert (scored.score >= .55).equals(scored.flagged)


def test_full_hcrl_protocol_preserves_normal_split():
    from scripts.evaluate_detectors import protocol
    prefix_baseline, prefix_jobs, _ = protocol("hcrl", "midterm")
    full_baseline, full_jobs, _ = protocol("hcrl", "midterm", full_hcrl=True)
    assert full_baseline == prefix_baseline
    assert full_jobs[-1] == prefix_jobs[-1]
    assert full_jobs[-1][1:3] == (121.0, 241.0)
    assert len(full_jobs) == 5
    assert all(job[1:3] == (0.0, None) for job in full_jobs[:4])
    with pytest.raises(ValueError, match="only to the hcrl"):
        protocol("road", "midterm", full_hcrl=True)
