"""Cheap-first cost router. Keys come from local .env only."""

from __future__ import annotations

import os
from pathlib import Path

from journeyman.contracts import (
    CHEAP_MODEL,
    CostRouterDecision,
    EMBED_FALLBACK,
    EMBED_MODEL,
    ESCALATE_MODEL,
    EscalateReason,
    GateDecision,
    REGRESSION_GATE_THRESHOLD,
    RouteChoice,
)


_VAGUE = (
    "i don't know",
    "i do not know",
    "i cannot",
    "as an ai",
    "no information",
)


class SpendLedger:
    def __init__(self) -> None:
        self._total = 0.0

    def record(self, run_id: str, cost_units: float) -> None:
        self._total += cost_units

    def total(self) -> float:
        return self._total


class CostRouter:
    def __init__(self, env_file: Path | None = None) -> None:
        _load_dotenv(env_file or Path(".env"))
        self.cheap_model = os.environ.get("TENSOR_MUX_MODEL", CHEAP_MODEL)
        self.escalate_model = os.environ.get("OPENAI_ESCALATE_MODEL", ESCALATE_MODEL)
        self.embed_model = os.environ.get("OPENAI_EMBEDDING_MODEL", EMBED_MODEL)
        self.embed_fallback = os.environ.get("OPENAI_EMBEDDING_FALLBACK", EMBED_FALLBACK)

    def decide(
        self,
        prompt: str,
        cheap_output: str | None = None,
        score: float | None = None,
    ) -> CostRouterDecision:
        if cheap_output is None:
            return self._try_first(prompt)
        return self._after_quality(cheap_output, score)

    def try_first(self, prompt: str) -> CostRouterDecision:
        return self.decide(prompt)

    def after_quality(self, cheap_output: str, score: float | None = None) -> CostRouterDecision:
        return self.decide("", cheap_output, score)

    def _try_first(self, prompt: str) -> CostRouterDecision:
        del prompt
        return CostRouterDecision(
            choice=RouteChoice.CHEAP,
            reason="try cheap first",
            model=self.cheap_model,
            estimated_cost=0.0,
        )

    def _after_quality(self, cheap_output: str, score: float | None = None) -> CostRouterDecision:
        gate = self.quality_gate(cheap_output, score)
        if gate.passed:
            return CostRouterDecision(
                choice=RouteChoice.CHEAP,
                reason="quality gate held",
                model=self.cheap_model,
                estimated_cost=0.0,
            )
        reason = EscalateReason.QUALITY_GATE
        if not (cheap_output or "").strip():
            reason = EscalateReason.EMPTY_OUTPUT
        return CostRouterDecision(
            choice=RouteChoice.ESCALATE,
            reason="quality gate miss",
            model=self.escalate_model,
            estimated_cost=0.0,
            gate_miss=True,
            escalate_reason=reason,
        )

    def quality_gate(self, output: str, score: float | None = None) -> GateDecision:
        text = (output or "").strip().lower()
        if not text:
            return GateDecision(passed=False, score=0.0, reason="empty")
        if any(marker in text for marker in _VAGUE):
            return GateDecision(passed=False, score=0.2, reason="vague")
        value = 1.0 if score is None else score
        passed = value >= REGRESSION_GATE_THRESHOLD
        return GateDecision(passed=passed, score=value, reason="held" if passed else "miss")

    def embed_route(self) -> CostRouterDecision:
        return CostRouterDecision(
            choice=RouteChoice.ESCALATE,
            reason="embeddings are a separate path",
            model=self.embed_model,
            estimated_cost=0.0,
        )


def load_local_env(path: Path | None = None) -> None:
    _load_dotenv(path or Path(".env"))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
