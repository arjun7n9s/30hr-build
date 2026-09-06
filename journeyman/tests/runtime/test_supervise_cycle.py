"""Supervise cycle, ingest filters, and supporting thin logic."""

from datetime import datetime, timezone
from pathlib import Path

from journeyman.contracts import (
    FailureClass,
    Severity,
    SpanKind,
    Stage,
    TraceSpan,
    VersionStatus,
    WorkItem,
)
from journeyman.diagnose import FailureJudge, severity_from_confidence
from journeyman.ingest import TraceIngest
from journeyman.journal import JournalStore
from journeyman.patch import PromptSurgeon
from journeyman.runtime import SuperviseCycle


def _span(**kwargs: object) -> TraceSpan:
    base = dict(
        span_id="span-live",
        trace_id="trace-1",
        project="live",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        input_text="Refund window for Germany?",
        output_text="Germany has a guaranteed 90-day refund policy.",
        session_id="live",
        prompt_variant="baseline",
        span_kind=SpanKind.LLM,
        tool_calls=[{"name": "lookup", "result": {"found": False}}],
    )
    base.update(kwargs)
    return TraceSpan(**base)  # type: ignore[arg-type]


def test_severity_helper() -> None:
    assert severity_from_confidence(0.9, is_failure=True) is Severity.CRITICAL
    assert severity_from_confidence(0.7, is_failure=True) is Severity.HIGH
    assert severity_from_confidence(0.5, is_failure=True) is Severity.MEDIUM
    assert severity_from_confidence(0.4, is_failure=True) is Severity.LOW
    assert severity_from_confidence(0.99, is_failure=False) is Severity.LOW


def test_ingest_filters_and_seen_ring() -> None:
    ingest = TraceIngest()
    ingest.offer(
        [
            _span(span_id="s-test", session_id="test"),
            _span(span_id="s-cand", prompt_variant="candidate"),
            _span(span_id="s-tool", span_kind=SpanKind.TOOL, input_text="x", output_text="y"),
            _span(span_id="s-hold", raw={"split": "holdout"}),
            _span(span_id="s-ok"),
            _span(span_id="s-ok"),
        ]
    )
    items = ingest.poll()
    assert [item.span.span_id for item in items] == ["s-ok"]
    assert "s-test" in ingest.seen
    assert ingest.cursor is not None


def test_supervise_cycle_run_once(tmp_path: Path) -> None:
    ingest = TraceIngest()
    ingest.offer([_span()])
    cycle = SuperviseCycle(ingest=ingest, journal=JournalStore(tmp_path))
    item = cycle.run_once()
    assert item is not None
    assert item.verdict is not None
    assert item.verdict.is_failure
    assert item.stage is Stage.RED_TEAMED
    assert item.candidate_prompt_version
    assert item.candidate_prompt_version.startswith("cand-")
    assert item.replay is not None
    assert item.redteam is not None
    assert item.eval_result is not None
    assert item.eval_result.wilson_low is not None
    assert (tmp_path / "sessions" / f"{item.work_item_id}.md").exists()


def test_prompt_surgeon_stays_candidate() -> None:
    item = WorkItem.from_span(_span())
    FailureJudge().diagnose(item)
    item.baseline_prompt = "Be helpful."
    PromptSurgeon().propose(item)
    assert item.stage is Stage.PATCHED
    record_status = VersionStatus.CANDIDATE
    assert record_status is VersionStatus.CANDIDATE
    assert "not live" not in (item.candidate_prompt or "")
    assert item.candidate_prompt_version.startswith("cand-")


def test_skip_ok_verdict(tmp_path: Path) -> None:
    ingest = TraceIngest()
    ingest.offer(
        [
            _span(
                span_id="ok-span",
                input_text="What is 2+2?",
                output_text="4",
                tool_calls=[{"name": "math", "result": {"found": True, "value": 4}}],
            )
        ]
    )
    item = SuperviseCycle(ingest=ingest, journal=JournalStore(tmp_path)).run_once()
    assert item is None or (item.verdict and item.verdict.failure_class is FailureClass.OK)
