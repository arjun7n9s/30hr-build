"""Actor policy, ingest filters, and fallback sink."""

from datetime import datetime, timezone
from pathlib import Path

from journeyman.contracts import Playbook, PlaybookEntry, SpanKind, TraceEventRow, TraceSpan
from journeyman.ingest import NullTraceSink, TraceIngest
from journeyman.partners.github import GitHubClient
from journeyman.partners.sink import NeatlogsTraceSink
from journeyman.runtime.actor import Actor


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[TraceEventRow] = []
        self.spans: list[TraceSpan] = []

    def emit(self, event: TraceEventRow) -> None:
        self.events.append(event)

    def emit_span(self, span: TraceSpan) -> None:
        self.spans.append(span)


def test_actor_refuses_deny_listed_tools() -> None:
    sink = _RecordingSink()
    actor = Actor(
        github=GitHubClient({"issues": [{"number": 1, "title": "secret", "body": "nope"}]}, offline=True),
        sink=sink,
        repo="demo/widget",
    )
    denied = actor.call_tool("push_files", {"path": "README.md"})
    assert denied.get("denied") is True
    assert denied.get("found") is False
    assert "secret" not in str(denied)
    create = actor.call_tool("create_issue", {"title": "nope"})
    assert create.get("denied") is True
    allowed = actor.call_tool("list_issues", {})
    assert allowed.get("denied") is not True
    assert allowed.get("found") is True
    assert sink.spans
    assert sink.events


def test_ingest_still_filters_actor_tool_spans() -> None:
    actor = Actor(github=GitHubClient({"issues": []}, offline=True), sink=NullTraceSink())
    strong = Playbook(
        version="cand-1",
        empty=False,
        entries=[
            PlaybookEntry(
                id="rule",
                text="Cite evidence. Use lookup tools. If missing, say so.",
            )
        ],
    )
    turn = actor.run("What does issue 12 say?", playbook=strong, session_id="demo")
    ingest = TraceIngest()
    ingest.offer(turn.spans)
    ingest.offer(
        [
            TraceSpan(
                span_id="test-skip",
                trace_id="t",
                project="demo",
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                input_text="skip me",
                output_text="nope",
                session_id="test",
                span_kind=SpanKind.LLM,
            )
        ]
    )
    items = ingest.poll()
    kinds = {item.span.span_kind for item in items}
    assert SpanKind.TOOL not in kinds
    assert all(item.span.session_id != "test" for item in items)
    assert all(not str(item.span.raw.get("name", "")).startswith("tool.") for item in items)


def test_trace_sink_falls_back_without_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.delenv("NEATLOGS_PROJECT_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    sink = NeatlogsTraceSink.from_env()
    assert isinstance(sink, NullTraceSink)
    constructed = NeatlogsTraceSink(api_key="", project_id="")
    assert constructed.enabled is False
