"""Neatlogs sink matches current HTTP inject docs."""

from datetime import datetime, timezone

from journeyman.contracts import SpanKind, Stage, TraceEventRow, TraceSpan
from journeyman.partners.sink import INGEST_BASE, NeatlogsTraceSink


def test_flush_posts_bearer_nested_tree() -> None:
    captured: list[tuple[str, dict, dict]] = []

    def transport(url: str, payload: dict, headers: dict) -> dict:
        captured.append((url, payload, headers))
        return {"success": True, "trace_id": "abc123", "spans": 2}

    sink = NeatlogsTraceSink(
        api_key="nlw_test",
        project_id="journeyman",
        transport=transport,
        session_id="demo-run1",
    )
    sink.emit(
        TraceEventRow(
            work_item_id="w",
            stage=Stage.WATCHED,
            title="Router: cheap",
            payload={"node": "Router", "gate_miss": False},
        )
    )
    sink.emit_span(
        TraceSpan(
            span_id="s1",
            trace_id="t",
            project="journeyman",
            started_at=datetime.now(timezone.utc),
            input_text="label issue 12",
            output_text="area:api",
            span_kind=SpanKind.LLM,
            raw={"name": "llm.complete", "model": "glm-4-7-flash", "tokens": 9},
        )
    )
    trace_id = sink.flush()
    assert trace_id == "abc123"
    assert sink.last_status == 200
    assert len(captured) == 1
    url, payload, headers = captured[0]
    assert url == INGEST_BASE + "/v1/trace"
    assert headers["Authorization"] == "Bearer nlw_test"
    assert "x-api-key" not in {k.lower() for k in headers}
    assert payload["name"] == "journeyman-run"
    assert payload["project"] == "journeyman"
    assert payload["kind"] == "WORKFLOW"
    assert payload["attributes"]["neatlogs.session.id"] == "demo-run1"
    assert payload["children"][0]["kind"] == "GUARDRAIL"
    assert payload["children"][1]["kind"] == "LLM"
    assert payload["children"][1]["model"] == "glm-4-7-flash"


def test_cockpit_url_is_traces_path(monkeypatch) -> None:
    from journeyman.partners.sink import dashboard_trace_url

    monkeypatch.delenv("NEATLOGS_ORG_ID", raising=False)
    monkeypatch.delenv("NEATLOGS_DASHBOARD_PROJECT_ID", raising=False)
    assert dashboard_trace_url(None) == "https://app.neatlogs.com"
    assert dashboard_trace_url("abc") == "https://app.neatlogs.com/traces/abc"
    monkeypatch.setenv("NEATLOGS_ORG_ID", "org-1")
    monkeypatch.setenv("NEATLOGS_DASHBOARD_PROJECT_ID", "proj-1")
    assert dashboard_trace_url("abc") == (
        "https://app.neatlogs.com/traces/abc?orgId=org-1&projectId=proj-1"
    )


def test_remap_drops_guessed_hosts() -> None:
    sink = NeatlogsTraceSink(api_key="k", project_id="p", base_url="https://api.neatlogs.com")
    assert sink.base_url == INGEST_BASE
    app = NeatlogsTraceSink(api_key="k", project_id="p", base_url="https://app.neatlogs.com/v1")
    assert app.base_url == INGEST_BASE
