"""Trace span and event-row contracts."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import SpanKind, Stage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TraceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str
    trace_id: str
    project: str
    started_at: datetime
    input_text: str = ""
    output_text: str = ""
    session_id: str = "demo"
    prompt_variant: str | None = None
    span_kind: SpanKind = SpanKind.LLM
    parent_span_id: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class TraceEventRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: str
    stage: Stage
    at: datetime = Field(default_factory=_utc_now)
    title: str
    detail: str = ""
    url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
