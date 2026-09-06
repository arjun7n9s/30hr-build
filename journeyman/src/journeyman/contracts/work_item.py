"""Work-item contract. Identity is the offending span."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import Severity, Stage
from journeyman.contracts.eval import (
    EfficiencyReport,
    EvalResult,
    ProbeSpec,
    RedTeamResult,
    ReplayResult,
    RootCause,
    Verdict,
)
from journeyman.contracts.trace import TraceSpan


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: str
    span: TraceSpan
    created_at: datetime = Field(default_factory=_utc_now)
    stage: Stage = Stage.WATCHED
    verdict: Verdict | None = None
    severity: Severity | None = None
    root_cause: RootCause | None = None
    efficiency: EfficiencyReport | None = None
    annotation_id: str | None = None
    dataset_id: str | None = None
    probes: list[ProbeSpec] = Field(default_factory=list)
    eval_result: EvalResult | None = None
    baseline_prompt: str | None = None
    candidate_prompt: str | None = None
    candidate_prompt_version: str | None = None
    prompt_diff: str | None = None
    replay: ReplayResult | None = None
    redteam: RedTeamResult | None = None

    @classmethod
    def from_span(cls, span: TraceSpan) -> "WorkItem":
        return cls(work_item_id=f"work-{span.span_id}", span=span)
