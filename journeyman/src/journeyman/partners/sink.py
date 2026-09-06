"""Trace sink. POST /v1/trace to ingest host when NEATLOGS_API_KEY is set."""

from __future__ import annotations

import os
import sys
from typing import Any

from journeyman.contracts import Stage, TraceEventRow, TraceSpan
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.partners.http import post_json
from journeyman.spend import load_local_env

# Dashboard: https://app.neatlogs.com  Ingest SoR: https://ingest.neatlogs.com
INGEST_BASE = "https://ingest.neatlogs.com"
_DISABLED_LOGGED = False


class NeatlogsTraceSink:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        project_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        load_local_env()
        self.api_key = api_key if api_key is not None else os.environ.get("NEATLOGS_API_KEY", "")
        self.project_id = (
            project_id
            if project_id is not None
            else os.environ.get("NEATLOGS_PROJECT_ID", "journeyman")
        )
        raw_base = base_url or os.environ.get("NEATLOGS_BASE_URL") or INGEST_BASE
        self.base_url = raw_base.rstrip("/")
        if "app.neatlogs.com" in self.base_url:
            self.base_url = INGEST_BASE
        self._fallback: TraceSink = NullTraceSink()
        self.enabled = bool(self.api_key)
        if not self.enabled:
            _log_disabled_once()

    @classmethod
    def from_env(cls) -> TraceSink:
        sink = cls()
        return sink if sink.enabled else sink._fallback

    def emit(self, event: TraceEventRow) -> None:
        if not self.enabled:
            self._fallback.emit(event)
            return
        self._post(
            {
                "name": event.title,
                "project": self.project_id,
                "kind": "EVENT",
                "input": event.detail,
                "output": event.stage.value if event.stage else "",
                "metadata": event.payload,
            }
        )

    def emit_span(self, span: TraceSpan) -> None:
        if not self.enabled:
            self._fallback.emit_span(span)
            return
        self._post(
            {
                "name": span.raw.get("name") or span.span_kind.value,
                "project": self.project_id or span.project,
                "kind": span.span_kind.value,
                "input": span.input_text,
                "output": span.output_text,
                "model": span.raw.get("model") or "",
                "metadata": span.raw,
            }
        )

    def _post(self, payload: dict[str, Any]) -> None:
        url = self.base_url + "/v1/trace"
        try:
            post_json(url, payload, {"x-api-key": self.api_key})
        except RuntimeError as exc:
            print(f"trace sink post failed: {exc}", file=sys.stderr)


def emit_node(
    sink: TraceSink,
    node: str,
    *,
    title: str,
    stage: Stage = Stage.WATCHED,
    work_item_id: str = "node",
    detail: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    sink.emit(
        TraceEventRow(
            work_item_id=work_item_id,
            stage=stage,
            title=f"{node}: {title}",
            detail=detail,
            payload={"node": node, **(payload or {})},
        )
    )


def _log_disabled_once() -> None:
    global _DISABLED_LOGGED
    if _DISABLED_LOGGED:
        return
    _DISABLED_LOGGED = True
    print(
        "trace sink disabled: NEATLOGS_API_KEY unset in local .env",
        file=sys.stderr,
    )
