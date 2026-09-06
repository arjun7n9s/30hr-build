"""Offline demo runner: sealed hold-out, smoke, and frozen eval."""

from datetime import datetime, timezone
from pathlib import Path

from journeyman.contracts import SpanKind, Split, TraceSpan
from journeyman.demo.run import run_demo
from journeyman.evalset.frozen import load_frozen_eval
from journeyman.ingest import TraceIngest
from journeyman.partners.mcp import REST_FLAG, GithubMcp


def test_demo_runner_offline_improves(tmp_path: Path) -> None:
    report = run_demo("github_triage_v1", work_root=tmp_path, offline=True)
    assert report.run1.pass_rate < report.run_n.pass_rate
    assert report.run_n.pass_rate == 1.0
    assert report.run_n.cost <= report.run1.cost
    assert report.promoted is True
    assert report.pointer.active != "weak-0"
    assert report.journal_path.exists()
    assert report.diff_path.exists()
    assert "Run1" in report.journal_path.read_text(encoding="utf-8")
    assert report.eval_result.delta is not None
    assert report.eval_result.delta > 0
    assert report.eval_result.wilson_low is not None
    assert report.hold_prior is not None
    assert report.hold_candidate is not None
    assert report.hold_candidate.split is Split.HOLDOUT


def test_holdout_not_scored_before_candidate(tmp_path: Path) -> None:
    report = run_demo("github_triage_v1", work_root=tmp_path, offline=True)
    assert report.score_log, "score_split must record calls"
    first_hold = next((i for i, (sid, split) in enumerate(report.score_log) if split == "holdout"), None)
    assert first_hold is not None, "hold-out is scored at promote"
    before = report.score_log[:first_hold]
    assert before, "DEV must be scored before any hold-out"
    assert all(split == "dev" for _, split in before)
    assert report.score_log[0] == ("demo-run1", "dev")
    assert all(not sid.startswith("demo-run1-hold") for sid, _ in report.score_log)
    cand_idx = next(i for i, (sid, _) in enumerate(report.score_log) if sid == "demo-cand-dev")
    assert first_hold > cand_idx
    ingest = TraceIngest()
    ingest.offer(
        [
            TraceSpan(
                span_id="hold-span",
                trace_id="t",
                project="demo",
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                input_text="hold question",
                output_text="hold answer",
                session_id="demo-hold-cand",
                span_kind=SpanKind.LLM,
                raw={"split": "holdout"},
            )
        ]
    )
    assert ingest.poll() == []
    assert "hold-span" in ingest.seen


def test_frozen_eval_counts() -> None:
    challenge = load_frozen_eval()
    assert challenge.repo == "arjun7n9s/journeyman-fixture"
    assert len(challenge.dev) == 10
    assert len(challenge.held_out) == 6
    assert {case.task_type for case in challenge.dev} >= {"label", "duplicate", "owner", "summarize", "fix_pr"}


def test_frozen_demo_offline_improves(tmp_path: Path) -> None:
    report = run_demo("frozen", work_root=tmp_path, offline=True)
    assert report.challenge_id == "frozen"
    assert report.run1.n == 10
    assert report.run1.pass_rate < report.run_n.pass_rate
    assert report.promoted is True
    assert report.hold_prior is not None
    assert report.hold_candidate is not None
    assert report.hold_candidate.n == 6
    assert all(split == "dev" for _, split in report.score_log if split != "holdout")


def test_mcp_rest_flag_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv(REST_FLAG, raising=False)
    client = GithubMcp({"issues": [{"number": 1, "title": "x", "body": "y"}]}, offline=True)
    hit = client.call("issue_read", {"issue_number": 1})
    assert hit.get("found") is True
    assert hit.get("title") == "x"
