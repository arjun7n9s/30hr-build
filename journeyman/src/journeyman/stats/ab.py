"""A/B comparison signatures. Mechanisms fill these later."""

from collections.abc import Sequence

from journeyman.contracts import WILSON_Z


def wilson_ci(successes: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    raise NotImplementedError


def welch_t(a: Sequence[float], b: Sequence[float]) -> float:
    raise NotImplementedError


def two_prop_z(s1: int, n1: int, s2: int, n2: int) -> float:
    raise NotImplementedError


def cohen_d(a: Sequence[float], b: Sequence[float]) -> float:
    raise NotImplementedError


def mean_ci_95(xs: Sequence[float]) -> tuple[float, float]:
    raise NotImplementedError
