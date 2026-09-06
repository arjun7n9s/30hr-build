"""Neatlogs JSON ingest. POST one nested /v1/trace tree with Bearer auth."""

from __future__ import annotations

import os
import sys
from typing import Any, Callable

from journeyman.contracts import Stage, TraceEventRow, TraceSpan
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.partners.http import post_json
from journeyman.spend import load_local_env

# Docs: https://docs.neatlogs.com/sdk/http-injection
INGEST_BASE = "https://ingest.neatlogs.com"
DASHBOARD = "https://app.neatlogs.com"
_DISABLED_LOGGED = False

Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class NeatlogsTraceSink:
    """Buffer spans, then flush one WORKFLOW tree to ingest.neatlogs.com."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        project_id: str | None = None,
        base_url: str | None = None,
        transport: Transport | None = None,
        workflow_name: str = "journeyman-run",
        session_id: str = "journeyman",
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
        if "app.neatlogs.com" in self.base_url or "api.neatlogs.com" in self.base_url:
            self.base_url = INGEST_BASE
        self._transport = transport or post_json
        self._fallback: TraceSink = NullTraceSink()
        self.enabled = bool(self.api_key)
        self.workflow_name = workflow_name
        self.session_id = session_id
        self._children: list[dict[str, Any]] = []
        self.last_trace_id: str | None = None
        self.last_status: int | None = None
        self.last_payload: dict[str, Any] | None = None
        self.last_error: str | None = None
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
        node = str((event.payload or {}).get("node") or "")
        child: dict[str, Any] = {
            "name": (event.title or node or "event")[:120],
            "kind": _event_kind(event.title, node, event.payload),
            "input": event.detail,
            "output": event.stage.value if event.stage else "",
            "metadata": event.payload or {},
        }
        if child["kind"] == "GUARDRAIL":
            child["passed"] = not bool((event.payload or {}).get("gate_miss"))
            if "score" in (event.payload or {}):
                child["score"] = event.payload["score"]
        self._children.append(child)

    def emit_span(self, span: TraceSpan) -> None:
        if not self.enabled:
            self._fallback.emit_span(span)
            return
        kind = _span_kind(span)
        child: dict[str, Any] = {
            "name": str(span.raw.get("name") or span.span_kind.value)[:120],
            "kind": kind,
            "input": span.input_text,
            "output": span.output_text,
            "metadata": {k: v for k, v in span.raw.items() if k != "name"},
        }
        model = span.raw.get("model")
        if model:
            child["model"] = model
        tokens = span.raw.get("tokens")
        if tokens:
            child["tokens"] = {"total": int(tokens)} if not isinstance(tokens, dict) else tokens
        if kind in {"TOOL", "MCP_TOOL"}:
            child["tool_name"] = str(span.raw.get("name") or span.input_text or "tool")
        if span.raw.get("denied") or str(span.output_text).startswith("denied"):
            child["status"] = "ERROR"
            child["error"] = str(span.output_text)[:300]
        self._children.append(child)

    def flush(self) -> str | None:
        if not self.enabled:
            return self._fallback.flush()
        payload = {
            "name": self.workflow_name,
            "project": self.project_id,
            "kind": "WORKFLOW",
            "attributes": {"neatlogs.session.id": self.session_id},
            "children": list(self._children),
        }
        self.last_payload = payload
        url = self.base_url + "/v1/trace"
        try:
            body = self._transport(
                url,
                payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            self.last_status = 200
            self.last_trace_id = str(body.get("trace_id") or "") or None
            self.last_error = None
            self._children.clear()
            return self.last_trace_id
        except RuntimeError as exc:
            self.last_status = None
            self.last_error = str(exc)
            print(f"trace sink post failed: {exc}", file=sys.stderr)
            return None

    def cockpit_url(self) -> str:
        if self.last_trace_id:
            return f"{DASHBOARD}/?trace_id={self.last_trace_id}"
        return DASHBOARD


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


def flush_sink(sink: TraceSink) -> str | None:
    return sink.flush()


def _span_kind(span: TraceSpan) -> str:
    kind = span.span_kind.value
    if kind == "TOOL":
        return "MCP_TOOL"
    if kind in {"LLM", "AGENT"}:
        return kind
    return "TASK"


def _event_kind(title: str, node: str, payload: dict[str, Any] | None) -> str:
    blob = f"{title} {node}".lower()
    if "router" in blob or (payload or {}).get("gate_miss") is True:
        return "GUARDRAIL"
    if "eval" in blob:
        return "EVALUATOR"
    if "reflect" in blob:
        return "AGENT"
    if "redteam" in blob:
        return "EVALUATOR"
    if "embed" in blob:
        return "EMBEDDING"
    return "TASK"


def _log_disabled_once() -> None:
    global _DISABLED_LOGGED
    if _DISABLED_LOGGED:
        return
    _DISABLED_LOGGED = True
    print(
        "trace sink disabled: NEATLOGS_API_KEY unset in local .env",
        file=sys.stderr,
    )
