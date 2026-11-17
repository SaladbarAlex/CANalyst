"""Statistics for the evaluation: intervals, paired tests, agreement.

Small and dependency-free on purpose (numpy only), so every number in the
paper can be recomputed from the saved outputs without a stats package.

    wilson_interval     proportion CI that behaves at 0, 1 and small n
    mcnemar_exact       paired comparison of two explainers on the same alerts
    mcnemar_bounds      the same test when only the two accuracies are known
    cohen_kappa         agreement between two claim-support raters
    bootstrap_detection confidence intervals for window-level detection
                        metrics that respect overlapping windows
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

_Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}


def wilson_interval(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion k/n."""
    if n <= 0:
        return (float("nan"), float("nan"))
    z = _Z[conf]
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value.

    b = cases the first method got right and the second got wrong,
    c = the reverse. Cases both got right or both got wrong carry no
    information about the difference and do not enter.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def mcnemar_bounds(n: int, correct_a: int, correct_b: int) -> dict:
    """What a paired test can and cannot say when only accuracies are known.

    With n shared cases, method A right on correct_a and method B right on
    correct_b, the discordant counts are not determined, but they are
    bounded: every table consistent with the two margins has
    b - c = correct_a - correct_b. This returns the p-value of the most and
    least favorable consistent tables. If even the largest p is below the
    significance level, the conclusion does not depend on the missing
    per-case outcomes.
    """
    if not (0 <= correct_a <= n and 0 <= correct_b <= n):
        raise ValueError("correct counts must lie in [0, n]")
    diff = correct_a - correct_b
    # c = cases only B got right. It cannot exceed B's correct count, the
    # cases A got wrong, or what the difference leaves room for.
    c_min = max(0, -diff)
    c_max = min(correct_b, n - correct_a)
    tables = [(c + diff, c) for c in range(c_min, c_max + 1)]
    ps = [mcnemar_exact(b, c) for b, c in tables]
    return {
        "n": n, "correct_a": correct_a, "correct_b": correct_b,
        "difference": diff / n,
        "tables": len(tables),
        "p_min": min(ps), "p_max": max(ps),
        "table_at_p_min": tables[int(np.argmin(ps))],
        "table_at_p_max": tables[int(np.argmax(ps))],
    }


def cohen_kappa(a: Sequence, b: Sequence) -> dict:
    """Cohen's kappa for two raters over the same items (nominal labels)."""
    if len(a) != len(b):
        raise ValueError("raters must label the same items")
    n = len(a)
    if n == 0:
        return {"n": 0, "kappa": float("nan"), "observed": float("nan"),
                "expected": float("nan")}
    labels = sorted(set(a) | set(b), key=str)
    idx = {lab: i for i, lab in enumerate(labels)}
    table = np.zeros((len(labels), len(labels)))
    for x, y in zip(a, b):
        table[idx[x], idx[y]] += 1
    observed = float(np.trace(table) / n)
    expected = float((table.sum(axis=1) * table.sum(axis=0)).sum() / (n * n))
    kappa = 1.0 if expected == 1.0 else (observed - expected) / (1 - expected)
    return {"n": n, "kappa": float(kappa), "observed": observed, "expected": expected,
            "labels": [str(lab) for lab in labels], "table": table.astype(int).tolist()}


def confusion(label: np.ndarray, flagged: np.ndarray) -> np.ndarray:
    """[TP, FP, FN, TN] for boolean-like arrays."""
    label = np.asarray(label).astype(bool)
    flagged = np.asarray(flagged).astype(bool)
    return np.array([(flagged & label).sum(), (flagged & ~label).sum(),
                     (~flagged & label).sum(), (~flagged & ~label).sum()], dtype=float)


def metrics_from_counts(counts: np.ndarray) -> dict[str, np.ndarray]:
    """Precision, recall, F1 and FPR from [..., 4] arrays of TP, FP, FN, TN."""
    tp, fp, fn, tn = (counts[..., i] for i in range(4))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "precision": np.where(tp + fp > 0, tp / (tp + fp), np.nan),
            "recall": np.where(tp + fn > 0, tp / (tp + fn), np.nan),
            "f1": np.where(2 * tp + fp + fn > 0, 2 * tp / (2 * tp + fp + fn), np.nan),
            "fpr": np.where(fp + tn > 0, fp / (fp + tn), np.nan),
        }


def block_counts(label: np.ndarray, flagged: np.ndarray, block: int) -> np.ndarray:
    """Confusion counts for consecutive blocks of `block` windows: [n_blocks, 4]."""
    n = len(label)
    edges = np.arange(0, n, block)
    return np.array([confusion(label[s:s + block], flagged[s:s + block]) for s in edges]
                    ).reshape(len(edges), 4)


def bootstrap_detection(captures: dict[str, np.ndarray], n_boot: int = 2000,
                        seed: int = 0, resample_captures: bool = True,
                        conf: float = 0.95) -> dict:
    """Bootstrap intervals for pooled window-level detection metrics.

    `captures` maps a capture name to its per-block confusion counts (from
    block_counts). Windows overlap and neighbors are correlated, so single
    windows are not resampled: whole blocks of consecutive windows are.
    With resample_captures=True the captures themselves are resampled
    first, which also carries capture-to-capture variation into the
    interval. Use it when the captures are exchangeable replicates and
    turn it off when each capture is a different condition.
    """
    rng = np.random.default_rng(seed)
    names = list(captures)
    point = metrics_from_counts(sum(c.sum(axis=0) for c in captures.values()))
    draws = np.zeros((n_boot, 4))
    for i in range(n_boot):
        chosen = rng.choice(len(names), size=len(names)) if resample_captures \
            else np.arange(len(names))
        total = np.zeros(4)
        for j in chosen:
            blocks = captures[names[j]]
            total += blocks[rng.integers(0, len(blocks), size=len(blocks))].sum(axis=0)
        draws[i] = total
    boot = metrics_from_counts(draws)
    lo_q, hi_q = (1 - conf) / 2, 1 - (1 - conf) / 2
    out = {}
    for key, values in boot.items():
        finite = values[np.isfinite(values)]
        out[key] = {
            "value": float(point[key]),
            "lo": float(np.quantile(finite, lo_q)) if finite.size else float("nan"),
            "hi": float(np.quantile(finite, hi_q)) if finite.size else float("nan"),
        }
    out["n_boot"] = n_boot
    out["captures"] = len(names)
    out["resample_captures"] = resample_captures
    return out


def bootstrap_proportion_diff(a: Sequence[int], b: Sequence[int], n_boot: int = 10000,
                              seed: int = 0, conf: float = 0.95) -> dict:
    """Paired bootstrap for the accuracy difference of two methods on shared cases."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired outcomes must have the same shape")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n_boot, len(a)))
    diffs = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    lo_q, hi_q = (1 - conf) / 2, 1 - (1 - conf) / 2
    return {"difference": float(a.mean() - b.mean()),
            "lo": float(np.quantile(diffs, lo_q)), "hi": float(np.quantile(diffs, hi_q)),
            "n": int(len(a)), "n_boot": n_boot}
