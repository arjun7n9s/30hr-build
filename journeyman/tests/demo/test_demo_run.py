"""Offline demo runner: sealed hold-out, smoke, and frozen eval."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from journeyman.contracts import Playbook, SpanKind, Split, TraceSpan
from journeyman.demo.run import run_demo
from journeyman.evalset.frozen import load_frozen_eval
from journeyman.ingest import TraceIngest
from journeyman.journal import JournalStore
from journeyman.partners.chat import ChatClient
from journeyman.partners.mcp import REST_FLAG, GithubMcp
from journeyman.reflect import Reflect
from journeyman.spend import load_local_env


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
    assert report.report_path is not None and report.report_path.exists()
    assert report.ui_path is not None and report.ui_path.exists()
    assert report.mode == "offline"
    if report.promoted:
        assert report.hold_candidate is not None
        assert any(split == "holdout" for _, split in report.score_log)
        assert report.redteam is not None
        assert report.redteam["n"] > 0


def test_promote_requires_holdout(tmp_path: Path) -> None:
    report = run_demo("github_triage_v1", work_root=tmp_path, mode="offline")
    assert report.promoted is True
    assert report.hold_prior is not None
    assert report.hold_candidate is not None
    first_hold = next(i for i, (_, split) in enumerate(report.score_log) if split == "holdout")
    cand = next(i for i, (sid, _) in enumerate(report.score_log) if sid == "demo-cand-dev")
    assert first_hold > cand
    assert report.score_log[0][1] == "dev"


def test_reflect_reads_dev_failures(tmp_path: Path) -> None:
    current = Playbook(version="weak-0", empty=True, entries=[])
    span = TraceSpan(
        span_id="fail-1",
        trace_id="t",
        project="demo",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        input_text="What labels should issue 12 get?",
        output_text="guaranteed 90-day refund",
        session_id="demo-run1",
        span_kind=SpanKind.LLM,
        raw={"split": "dev"},
    )
    journal = JournalStore(tmp_path / "journal")
    merged = Reflect().from_failures(
        current,
        [span],
        version="cand-1",
        candidate_prompt="Cite tools. If missing, say so.",
        journal=journal,
    )
    ids = {entry.id for entry in merged.entries}
    assert "candidate-rule" in ids
    assert "taxonomy" in ids
    assert "refund" in merged.entries[0].text or "Cite tools" in merged.entries[0].text
    core = (tmp_path / "journal" / "CORE.md").read_text(encoding="utf-8")
    assert "DEV-fail" in core


def test_live_clients_require_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for key in ("TMX_API_KEY", "TENSOR_MUX_API_KEY", "TENSOR_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv(REST_FLAG, raising=False)
    with pytest.raises(RuntimeError, match="TMX_API_KEY"):
        ChatClient(offline=False)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        GithubMcp({}, offline=False)


def test_live_smoke_one_dev_and_neatlogs(tmp_path: Path) -> None:
    load_local_env()
    import os

    if os.environ.get("JOURNEYMAN_LIVE_SMOKE") != "1":
        pytest.skip("set JOURNEYMAN_LIVE_SMOKE=1 to run live HTTP smoke")
    if not os.environ.get("TMX_API_KEY"):
        pytest.skip("live keys absent from local .env")
    if not os.environ.get("NEATLOGS_API_KEY"):
        pytest.skip("NEATLOGS_API_KEY absent from local .env")
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        pytest.skip("GITHUB_TOKEN absent from local .env")
    from journeyman.evalset.frozen import load_frozen_eval
    from journeyman.partners.sink import NeatlogsTraceSink
    from journeyman.runtime.actor import Actor

    challenge = load_frozen_eval()
    case = challenge.dev[0]
    sink = NeatlogsTraceSink.from_env()
    actor = Actor(
        chat=ChatClient(offline=False),
        github=GithubMcp(challenge.github, offline=False),
        sink=sink,
        repo=challenge.repo,
    )
    turn = actor.run(
        case.question,
        playbook=challenge.weak_playbook,
        session_id="live-smoke",
        task={"type": case.task_type, "github": case.github, "id": case.id},
    )
    assert turn.text
    trace_id = sink.flush() if hasattr(sink, "flush") else None
    assert getattr(sink, "last_status", None) == 200
    assert trace_id


def test_mcp_rest_flag_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv(REST_FLAG, raising=False)
    client = GithubMcp({"issues": [{"number": 1, "title": "x", "body": "y"}]}, offline=True)
    hit = client.call("issue_read", {"issue_number": 1})
    assert hit.get("found") is True
    assert hit.get("title") == "x"
