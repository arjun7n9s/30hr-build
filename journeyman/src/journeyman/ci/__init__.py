"""Prompt regression gate."""

from journeyman.contracts import EvalResult, GateDecision, REGRESSION_GATE_THRESHOLD


class PromptRegressionGate:
    def check(self, before: EvalResult, after: EvalResult) -> GateDecision:
        rate = after.candidate_pass_rate
        if rate is None:
            rate = after.baseline_pass_rate
        passed = rate >= REGRESSION_GATE_THRESHOLD
        if before.baseline_pass_rate and rate < before.baseline_pass_rate:
            passed = False
        return GateDecision(passed=passed, score=rate, reason="held" if passed else "regression")
