"""Statistics: Wilson intervals, paired bootstrap, McNemar's exact test, Holm, non-inferiority."""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import binomtest, norm


def wilson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return (0.0, 1.0)
    z = norm.ppf(1 - (1 - conf) / 2)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired_bootstrap(a, b, n_resamples: int = 2000, seed: int = 0) -> np.ndarray:
    """Bootstrap distribution of mean(a) - mean(b) over paired items (a, b are 0/1 arrays)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired arrays must have the same length")
    rng = np.random.default_rng(seed)
    n = len(a)
    idx = rng.integers(0, n, size=(n_resamples, n))
    d = a - b
    return d[idx].mean(axis=1)


def diff_ci(a, b, n_resamples: int = 2000, seed: int = 0, conf: float = 0.95) -> dict:
    """Two-sided percentile interval and one-sided lower bound for mean(a) - mean(b)."""
    boots = paired_bootstrap(a, b, n_resamples, seed)
    alpha = 1 - conf
    return {"diff": float(np.mean(a) - np.mean(b)),
            "ci_low": float(np.percentile(boots, 100 * alpha / 2)),
            "ci_high": float(np.percentile(boots, 100 * (1 - alpha / 2))),
            "one_sided_low": float(np.percentile(boots, 100 * alpha)),
            "boots": boots}


def noninferiority(a, b, margin: float = 0.03, n_resamples: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict:
    """H0: mean(a) - mean(b) <= -margin. Non-inferior when the one-sided (1-alpha) lower bound > -margin.

    The bootstrap p-value is the share of resampled differences at or below -margin; it is what Holm adjusts.
    """
    r = diff_ci(a, b, n_resamples, seed, conf=1 - alpha)
    boots = r.pop("boots")
    p = float((np.sum(boots <= -margin) + 1) / (len(boots) + 1))
    lower = float(np.percentile(boots, 100 * alpha))
    return {**r, "lower_bound": lower, "p_value": p, "noninferior": lower > -margin, "margin": margin}


def mcnemar_exact(cand, cur) -> dict:
    """Exact (binomial) McNemar test on paired pass/fail arrays.

    b = items the candidate passes and the current prompt fails; c = the reverse.
    Two-sided p-value; the candidate is favoured only when b > c and p < alpha.
    """
    cand = np.asarray(cand, dtype=bool)
    cur = np.asarray(cur, dtype=bool)
    b = int(np.sum(cand & ~cur))
    c = int(np.sum(~cand & cur))
    if b + c == 0:
        return {"b": b, "c": c, "p_value": 1.0}
    p = binomtest(b, b + c, 0.5, alternative="two-sided").pvalue
    return {"b": b, "c": c, "p_value": float(p)}


def holm(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * pvalues[i])
        running = max(running, val)
        adj[i] = running
    return adj


def flip_rate(pass_matrix) -> float:
    """Share of items whose pass/fail differs across repeated runs (rows = repeats, cols = items)."""
    m = np.asarray(pass_matrix, dtype=bool)
    if m.ndim != 2 or m.shape[0] < 2:
        return 0.0
    return float(np.mean(m.any(axis=0) & ~m.all(axis=0)))
