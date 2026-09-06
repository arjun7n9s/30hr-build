"""A/B comparison statistics (Wilson, Welch, two-proportion z, Cohen's d)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from journeyman.contracts import WILSON_Z, EvalResult


def wilson_ci(successes: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1.0 + (z * z) / n
    center = (phat + (z * z) / (2.0 * n)) / denom
    margin = (z * math.sqrt((phat * (1.0 - phat)) / n + (z * z) / (4.0 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _stddev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def welch_t(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    va = _stddev(a) ** 2 or 0.0
    vb = _stddev(b) ** 2 or 0.0
    denom = math.sqrt(va / len(a) + vb / len(b) or 1e-12)
    return (_mean(a) - _mean(b)) / denom


def two_prop_z(s1: int, n1: int, s2: int, n2: int) -> float:
    if n1 <= 0 or n2 <= 0:
        return float("nan")
    p_pool = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return float("nan")
    return (s1 / n1 - s2 / n2) / se


def cohen_d(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled = math.sqrt(((_stddev(a) ** 2 + _stddev(b) ** 2) / 2) or 1e-12)
    return (_mean(a) - _mean(b)) / pooled


def fill_eval_result(
    result: EvalResult,
    baseline_scores: Sequence[float] | None = None,
    candidate_scores: Sequence[float] | None = None,
) -> EvalResult:
    n = result.n or (len(baseline_scores) if baseline_scores else 0)
    if n:
        lo, hi = wilson_ci(result.baseline_successes, n)
        result.wilson_low = lo
        result.wilson_high = hi
    if (
        baseline_scores
        and candidate_scores
        and result.candidate_successes is not None
        and n
    ):
        result.welch_t = welch_t(baseline_scores, candidate_scores)
        result.two_prop_z = two_prop_z(
            result.baseline_successes, n, result.candidate_successes, n
        )
        result.cohen_d = cohen_d(baseline_scores, candidate_scores)
    return result


def mean_ci_95(xs: Sequence[float]) -> tuple[float, float]:
    if len(xs) < 2:
        m = _mean(xs)
        return (m, m)
    se = _stddev(xs) / math.sqrt(len(xs))
    m = _mean(xs)
    return (m - WILSON_Z * se, m + WILSON_Z * se)
