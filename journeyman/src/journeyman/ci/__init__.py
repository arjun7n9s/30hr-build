"""Prompt regression gate stub."""

from journeyman.contracts import EvalResult, GateDecision


class PromptRegressionGate:
    def check(self, before: EvalResult, after: EvalResult) -> GateDecision:
        raise NotImplementedError
