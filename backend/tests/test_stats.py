"""Tests for the statistics helpers. Run with: pytest -q (from backend)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import stats  # noqa: E402


def test_wilson_interval_matches_known_values():
    lo, hi = stats.wilson_interval(7, 20)
    assert lo == pytest.approx(0.1812, abs=1e-4)
    assert hi == pytest.approx(0.5671, abs=1e-4)
    # Unlike the normal approximation it stays inside [0, 1] at the edges.
    assert stats.wilson_interval(0, 16)[0] == 0.0
    assert 0 < stats.wilson_interval(0, 16)[1] < 0.25
    assert stats.wilson_interval(16, 16)[1] == 1.0


def test_mcnemar_exact_known_values():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(5, 5) == 1.0
    assert stats.mcnemar_exact(10, 0) == pytest.approx(2 / 2 ** 10)
    # 2 * P(X <= 3 | n = 16, p = 0.5)
    assert stats.mcnemar_exact(13, 3) == pytest.approx(2 * 697 / 65536)
    assert stats.mcnemar_exact(3, 13) == stats.mcnemar_exact(13, 3)


def test_mcnemar_bounds_enumerates_every_consistent_table():
    """Midterm ROAD result: control 17/20, model 7/20 on the same alerts."""
    r = stats.mcnemar_bounds(20, 17, 7)
    assert r["tables"] == 4
    assert r["table_at_p_min"] == (10, 0)
    assert r["table_at_p_max"] == (13, 3)
    assert r["p_max"] == pytest.approx(2 * 697 / 65536)
    assert r["p_max"] < 0.05          # significant whatever the pairing was

    # Car-Hacking: 53/69 versus 54/69 is a tie under every pairing.
    tie = stats.mcnemar_bounds(69, 53, 54)
    assert tie["p_min"] > 0.5


def test_mcnemar_bounds_agrees_with_brute_force():
    n, ca, cb = 7, 5, 3
    ps = []
    for mask_a in range(2 ** n):
        a = [(mask_a >> i) & 1 for i in range(n)]
        if sum(a) != ca:
            continue
        for mask_b in range(2 ** n):
            b = [(mask_b >> i) & 1 for i in range(n)]
            if sum(b) != cb:
                continue
            bb = sum(1 for x, y in zip(a, b) if x and not y)
            cc = sum(1 for x, y in zip(a, b) if y and not x)
            ps.append(stats.mcnemar_exact(bb, cc))
    r = stats.mcnemar_bounds(n, ca, cb)
    assert r["p_min"] == pytest.approx(min(ps))
    assert r["p_max"] == pytest.approx(max(ps))


def test_cohen_kappa_textbook_example():
    # 50 items: both yes 20, both no 15, A yes / B no 5, A no / B yes 10.
    a = ["y"] * 20 + ["n"] * 15 + ["y"] * 5 + ["n"] * 10
    b = ["y"] * 20 + ["n"] * 15 + ["n"] * 5 + ["y"] * 10
    r = stats.cohen_kappa(a, b)
    assert r["observed"] == pytest.approx(0.70)
    assert r["expected"] == pytest.approx(0.50)
    assert r["kappa"] == pytest.approx(0.40)
    assert stats.cohen_kappa(a, a)["kappa"] == 1.0


def test_cohen_kappa_handles_three_categories_and_disjoint_label_sets():
    a = ["supported", "unsupported", "contradicted", "supported"]
    b = ["supported", "supported", "contradicted", "supported"]
    r = stats.cohen_kappa(a, b)
    assert r["n"] == 4 and 0 < r["kappa"] < 1
    assert len(r["labels"]) == 3


def test_bootstrap_interval_contains_point_and_narrows_with_data():
    rng = np.random.default_rng(1)

    def capture(n):
        label = rng.random(n) < 0.3
        flagged = np.where(label, rng.random(n) < 0.8, rng.random(n) < 0.05)
        return stats.block_counts(label, flagged, block=20)

    small = {f"c{i}": capture(200) for i in range(4)}
    large = {f"c{i}": capture(5000) for i in range(4)}
    rs = stats.bootstrap_detection(small, n_boot=400, seed=0, resample_captures=False)
    rl = stats.bootstrap_detection(large, n_boot=400, seed=0, resample_captures=False)
    for r in (rs, rl):
        assert r["recall"]["lo"] <= r["recall"]["value"] <= r["recall"]["hi"]
        assert r["fpr"]["lo"] <= r["fpr"]["value"] <= r["fpr"]["hi"]
    assert (rl["recall"]["hi"] - rl["recall"]["lo"]) < (rs["recall"]["hi"] - rs["recall"]["lo"])
    assert rl["recall"]["value"] == pytest.approx(0.8, abs=0.03)


def test_block_counts_partition_the_windows():
    label = np.array([1, 1, 0, 0, 1, 0, 0])
    flagged = np.array([1, 0, 1, 0, 1, 0, 0])
    blocks = stats.block_counts(label, flagged, block=3)
    assert blocks.shape == (3, 4)
    assert blocks.sum() == len(label)
    assert blocks.sum(axis=0).tolist() == stats.confusion(label, flagged).tolist()


def test_paired_bootstrap_difference():
    a = [1] * 17 + [0] * 3
    b = [1] * 7 + [0] * 13
    r = stats.bootstrap_proportion_diff(a, b, n_boot=2000, seed=0)
    assert r["difference"] == pytest.approx(0.5)
    assert r["lo"] > 0          # the interval excludes zero
    assert math.isclose(r["n"], 20)
