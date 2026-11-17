"""The fast measuring path must agree with the reference path.

features.extract_windows + RuleDetector is the reference implementation.
windowstats measures a capture once and re-scores it without the per-window
loops; these tests pin the two together so they cannot drift apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, features, synth, windowstats as ws  # noqa: E402
from app.detector import RuleDetector  # noqa: E402

ATTACKS = ["dos", "fuzzing", "spoofing", "replay", "masquerade"]


@pytest.fixture(scope="module")
def capture():
    df = synth.generate(duration_s=150, seed=3, attacks=ATTACKS)
    baseline = features.learn_baseline(df, 30.0)
    return df, baseline


@pytest.fixture(scope="module")
def measured(capture):
    df, _ = capture
    return ws.measure(df)


def test_fast_path_reproduces_reference_scores(capture, measured):
    df, baseline = capture
    ref = features.extract_windows(df, baseline)
    ref, alerts = RuleDetector(baseline).run(ref)
    win, ids = measured
    wf, _ = ws.apply_baseline(win, ids, baseline)
    fast = ws.rule_scores(wf)

    assert len(fast) == len(ref)
    for col in ["start", "end", "n_msgs", "label", "rate_ratio_total", "n_unknown_ids",
                "n_missing_ids", "max_rate_ratio", "max_iat_z", "max_entropy_delta",
                "max_bitflip_delta"]:
        assert np.array_equal(ref[col].to_numpy(), fast[col].to_numpy()), col
    assert (ref["attack_type"].to_numpy() == fast["attack_type"].to_numpy()).all()
    for comp in ws.COMPONENTS:
        want = np.array([c[comp] for c in ref["components"]])
        assert np.array_equal(want, fast[comp].to_numpy()), comp
    assert np.array_equal(ref["score"].to_numpy(), fast["score"].to_numpy())
    assert np.array_equal(ref["flagged"].to_numpy(), fast["flagged"].to_numpy())
    assert ref["flagged"].sum() > 0 and ref["label"].sum() > 0
    spans = ws.alert_spans(win, fast["flagged"].to_numpy())
    assert [(a.start, a.end) for a in alerts] == spans


def test_per_id_statistics_match_reference_detail(capture, measured):
    df, baseline = capture
    ref = features.extract_windows(df, baseline)
    win, ids = measured
    _, idf = ws.apply_baseline(win, ids, baseline)
    for w in (10, 150, 300, len(ref) - 2):       # normal and attack windows
        want = ref.iloc[w]["per_id"]
        got = idf[idf["window"] == w].set_index("can_id")
        assert set(want) == set(got.index)
        for cid, v in want.items():
            row = got.loc[cid]
            assert row["count"] == v["count"]
            assert round(row["iat_mean"] * 1000, 3) == v["iat_mean_ms"]
            assert round(row["iat_std"] * 1000, 3) == v["iat_std_ms"]
            assert round(row["entropy"], 3) == v["entropy"]
            assert round(row["bitflip"], 4) == v["bitflip_rate"]
            assert bool(row["known"]) == v["known"]


def test_baseline_stats_equal_learn_baseline():
    df = synth.generate(duration_s=90, seed=8, attacks=[])
    want = features.learn_baseline(df, float("inf"))
    got = ws.BaselineStats.from_df(df, name="normal").to_baseline()
    assert got.known_ids == want.known_ids
    assert got.total_rate == want.total_rate
    for name in ["rate", "iat_mean", "iat_std", "jitter_floor", "presence", "entropy", "bitflip"]:
        assert getattr(got, name) == getattr(want, name), name


def test_pooled_reference_adds_exactly():
    df = synth.generate(duration_s=120, seed=9, attacks=[])
    first = df[df["timestamp"] < 60.0]
    second = df[df["timestamp"] >= 60.0]
    a = ws.BaselineStats.from_df(first, name="a")
    b = ws.BaselineStats.from_df(second, name="b")
    pooled = ws.BaselineStats.pool([a, b])
    whole = ws.BaselineStats.from_df(df, name="whole")
    assert pooled.n == whole.n == len(df)
    assert pooled.captures == ["a", "b"]
    for cid, v in whole.per_id.items():
        p = pooled.per_id[cid]
        assert p["n"] == v["n"]
        assert np.array_equal(p["hist"], v["hist"])        # byte histograms add exactly
        assert np.array_equal(p["bmin"], v["bmin"]) and np.array_equal(p["bmax"], v["bmax"])
        # One inter-arrival gap per ID joins the halves and is not counted.
        assert p["n_iat"] == v["n_iat"] - 1
    pb, wb = pooled.to_baseline(), whole.to_baseline()
    for cid in wb.known_ids:
        assert pb.entropy[cid] == pytest.approx(wb.entropy[cid], abs=1e-12)
        assert pb.iat_mean[cid] == pytest.approx(wb.iat_mean[cid], rel=1e-2)
        assert pb.rate[cid] == pytest.approx(wb.rate[cid], rel=2e-2)
    # Pooling must not disturb its inputs.
    assert a.n == len(first) and b.n == len(second)


def test_byte_ranges_cover_every_frame(measured, capture):
    df, _ = capture
    win, ids = measured
    row = ids[(ids["window"] == 20)].iloc[0]
    w = win.iloc[20]
    frames = df[(df["timestamp"] >= w["start"]) & (df["timestamp"] < w["end"])
                & (df["can_id"] == row["can_id"])]
    payloads = np.array([p + [0] * (8 - len(p)) for p in frames["data"]])
    width = min(len(p) for p in frames["data"])
    for pos in range(width):
        assert row[f"bmin{pos}"] == payloads[:, pos].min()
        assert row[f"bmax{pos}"] == payloads[:, pos].max()
    assert row["n_unique"] == len({tuple(p) for p in frames["data"]})


def test_variable_length_payloads_are_handled():
    df = pd.DataFrame({
        "timestamp": [0.00, 0.01, 0.02, 0.03, 0.04],
        "can_id": [0x10] * 5,
        "dlc": [2, 1, 2, 0, 2],
        "data": [[1, 2], [3], [1, 255], [], [1, 2]],
        "label": 0, "attack_type": "normal",
    })
    win, ids = ws.measure(df)
    row = ids.iloc[0]
    assert row["count"] == 5
    assert row["entropy"] == pytest.approx(features.byte_entropy(list(df["data"])))
    assert row["bitflip"] == pytest.approx(features.bitflip_rate(list(df["data"])))
    assert (row["bmin0"], row["bmax0"]) == (1, 3)
    assert (row["bmin1"], row["bmax1"]) == (2, 255)
    assert (row["bmin2"], row["bmax2"]) == (255, 0)        # no frame reaches byte 2


def test_cache_round_trip(tmp_path, measured):
    win, ids = measured
    ref = ws.BaselineStats.from_df(synth.generate(duration_s=40, seed=2, attacks=[]), name="n")
    path = tmp_path / "capture.npz"
    cache.save(path, cache.Measured("capture", win, ids, {"name": "capture", "frames": 1},
                                    {"all": ref}))
    back = cache.load(path)
    assert back.info["frames"] == 1 and back.name == "capture"
    pd.testing.assert_frame_equal(back.win, win, check_dtype=False)
    pd.testing.assert_frame_equal(back.ids, ids, check_dtype=False)
    got, want = back.reference["all"].to_baseline(), ref.to_baseline()
    assert got.rate == want.rate and got.entropy == want.entropy
    assert got.jitter_floor == want.jitter_floor and got.presence == want.presence
