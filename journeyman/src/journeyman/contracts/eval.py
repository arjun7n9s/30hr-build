"""Verdict, root-cause, probe, eval, replay, and red-team contracts."""

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import FailureClass


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_class: FailureClass
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    expected_behavior: str = ""

    @property
    def is_failure(self) -> bool:
        return self.failure_class is not FailureClass.OK


class RootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    culprit: str
    causal_chain: list[str] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    fix_strategy: str = ""


class ProbeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_text: str
    expected_answer: str
    acceptance_criterion: str


class EvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_id: str
    baseline_pass_rate: float
    candidate_pass_rate: float | None = None

    @property
    def delta(self) -> float | None:
        if self.candidate_pass_rate is None:
            return None
        return round(self.candidate_pass_rate - self.baseline_pass_rate, 4)


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_input: str
    before_output: str
    after_output: str
    fixed: bool
    judge_rationale: str = ""


class RedTeamResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attacks_run: int
    before_pass: int
    after_pass: int
    examples: list[dict] = Field(default_factory=list)


class EfficiencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_avg_tokens: float = 0.0
    candidate_avg_tokens: float = 0.0
    baseline_avg_latency_ms: float = 0.0
    candidate_avg_latency_ms: float = 0.0

    @staticmethod
    def _pct(base: float, cand: float) -> float | None:
        if not base:
            return None
        return round((cand - base) / base, 4)

    @property
    def token_delta_pct(self) -> float | None:
        return self._pct(self.baseline_avg_tokens, self.candidate_avg_tokens)

    @property
    def latency_delta_pct(self) -> float | None:
        return self._pct(self.baseline_avg_latency_ms, self.candidate_avg_latency_ms)
