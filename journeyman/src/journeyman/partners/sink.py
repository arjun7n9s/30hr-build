"""Trace sink. Posts spans when project env is set; otherwise NullTraceSink."""

from __future__ import annotations

import os
import sys
from typing import Any

from journeyman.contracts import TraceEventRow, TraceSpan
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.partners.http import post_json
from journeyman.spend import load_local_env

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
            project_id if project_id is not None else os.environ.get("NEATLOGS_PROJECT_ID", "")
        )
        self.base_url = (
            base_url
            or os.environ.get("NEATLOGS_BASE_URL")
            or "https://api.neatlogs.com/v1"
        ).rstrip("/")
        self._fallback: TraceSink = NullTraceSink()
        self.enabled = bool(self.api_key and self.project_id)
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
        self._post("events", event.model_dump(mode="json"))

    def emit_span(self, span: TraceSpan) -> None:
        if not self.enabled:
            self._fallback.emit_span(span)
            return
        self._post("spans", span.model_dump(mode="json"))

    def _post(self, kind: str, payload: dict[str, Any]) -> None:
        url = f"{self.base_url}/projects/{self.project_id}/{kind}"
        try:
            post_json(
                url,
                payload,
                {"Authorization": f"Bearer {self.api_key}"},
            )
        except RuntimeError as exc:
            print(f"trace sink post failed: {exc}", file=sys.stderr)


def _log_disabled_once() -> None:
    global _DISABLED_LOGGED
    if _DISABLED_LOGGED:
        return
    _DISABLED_LOGGED = True
    print(
        "trace sink disabled: NEATLOGS_API_KEY or NEATLOGS_PROJECT_ID unset in local .env",
        file=sys.stderr,
    )
