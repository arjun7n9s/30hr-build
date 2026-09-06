"""Trace ingest: seen ring, cursor, feedback-loop filters."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol

from journeyman.contracts import SEEN_RING_MAX, SpanKind, TraceEventRow, TraceSpan, WorkItem


class TraceSink(Protocol):
    """Partner traces later. Implementations must not be required for the cycle."""

    def emit(self, event: TraceEventRow) -> None: ...

    def emit_span(self, span: TraceSpan) -> None: ...

    def flush(self) -> str | None: ...


class NullTraceSink:
    def emit(self, event: TraceEventRow) -> None:
        return None

    def emit_span(self, span: TraceSpan) -> None:
        return None

    def flush(self) -> str | None:
        return None


class TraceIngest:
    """skip session_id=="test", prompt_variant=="candidate", split=held_out, tool-child spans; seen ring max 500"""

    def __init__(self, sink: TraceSink | None = None) -> None:
        self.seen: deque[str] = deque(maxlen=SEEN_RING_MAX)
        self.cursor: datetime | None = None
        self._pending: list[TraceSpan] = []
        self.sink: TraceSink = sink or NullTraceSink()

    def offer(self, spans: Sequence[TraceSpan]) -> None:
        self._pending.extend(spans)

    def poll(self) -> list[WorkItem]:
        items: list[WorkItem] = []
        newest = self.cursor
        pending, self._pending = self._pending, []
        for span in pending:
            if not span.span_id or span.span_id in self.seen:
                continue
            if self._skip(span):
                self._mark(span.span_id)
                continue
            if not (span.input_text and span.output_text):
                self._mark(span.span_id)
                continue
            item = WorkItem.from_span(span)
            self._mark(span.span_id)
            items.append(item)
            self.sink.emit(
                TraceEventRow(
                    work_item_id=item.work_item_id,
                    stage=item.stage,
                    title="span observed",
                    detail=span.input_text[:160],
                )
            )
            if newest is None or span.started_at > newest:
                newest = span.started_at
        self.cursor = newest or datetime.now(timezone.utc)
        return items

    def _skip(self, span: TraceSpan) -> bool:
        if span.session_id == "test":
            return True
        variant = span.prompt_variant or _raw_attr(span.raw, "prompt_variant")
        if variant == "candidate":
            return True
        split = str(span.raw.get("split") or _raw_attr(span.raw, "split") or "").lower()
        if split in {"holdout", "held_out", "held-out"}:
            return True
        if span.span_kind is SpanKind.TOOL:
            return True
        name = str(span.raw.get("name", ""))
        if name.startswith("tool."):
            return True
        return False

    def _mark(self, span_id: str) -> None:
        if span_id not in self.seen:
            self.seen.append(span_id)


def _raw_attr(raw: dict, key: str) -> str:
    attrs = raw.get("attributes", raw)
    if not isinstance(attrs, dict):
        return ""
    val = attrs.get(key)
    return str(val) if val else ""
