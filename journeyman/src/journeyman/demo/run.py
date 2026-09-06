"""CLI: one pipeline, --mode offline|live. Promote = Actor re-eval on frozen JSON."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from journeyman.contracts import (
    EvalResult,
    JournalEntry,
    JournalKind,
    PatchBudgetCounters,
    Playbook,
    SkillEntry,
    SpanKind,
    Split,
    Stage,
    VersionPointer,
    VersionStatus,
)
from journeyman.demo.artifacts import write_artifacts
from journeyman.demo.challenge import ChallengeCase, challenges_dir, load_challenge
from journeyman.evalset.frozen import load_frozen_eval
from journeyman.evolve import BudgetedEvolver
from journeyman.ingest import TraceIngest
from journeyman.journal import JournalStore
from journeyman.memory import MemoryStore
from journeyman.partners.chat import ChatClient
from journeyman.partners.mcp import GithubMcp
from journeyman.partners.sink import NeatlogsTraceSink, dashboard_trace_url, emit_node, flush_sink
from journeyman.reflect import Reflect
from journeyman.runtime import SuperviseCycle
from journeyman.runtime.actor import Actor, ActorTurn
from journeyman.runtime.triage import score_frozen
from journeyman.skills import SkillLibrary
from journeyman.spend import CostRouter
from journeyman.stats.ab import fill_eval_result
from journeyman.verify import attack_live

# Test hook: every score_split call records (session_id, split).
SCORE_LOG: list[tuple[str, str]] = []


@dataclass
class SplitScore:
    pass_rate: float
    successes: int
    n: int
    cost: float
    tokens: int
    turns: list[ActorTurn]
    passed: list[bool]
    split: Split = Split.DEV
    speed_ms: float = 0.0
    tool_calls: int = 0


@dataclass
class DemoReport:
    challenge_id: str
    run1: SplitScore
    run_n: SplitScore
    hold_prior: SplitScore | None
    hold_candidate: SplitScore | None
    promoted: bool
    pointer: VersionPointer
    eval_result: EvalResult
    journal_path: Path
    diff_path: Path
    candidate_version: str | None
    score_log: list[tuple[str, str]] = field(default_factory=list)
    mode: str = "offline"
    neatlogs_trace_id: str | None = None
    neatlogs_url: str = ""
    report_path: Path | None = None
    ui_path: Path | None = None
    journal_text: str = ""
    diff_text: str = ""
    playbook_entries: list[dict[str, Any]] = field(default_factory=list)
    playbook_rules: list[dict[str, Any]] = field(default_factory=list)
    redteam: dict[str, Any] | None = None
    children: list[dict[str, Any]] = field(default_factory=list)
    repo: str = "arjun7n9s/journeyman-fixture"


def case_passes(expected: str, output: str) -> bool:
    expected_l = expected.lower().strip()
    output_l = output.lower()
    if expected_l in {"missing", "say so"} or expected_l.startswith("missing"):
        return any(
            token in output_l
            for token in ("missing", "not found", "no evidence", "cannot answer", "do not know", "don't know")
        )
    return expected_l in output_l


def score_split(
    actor: Actor,
    cases: list[ChallengeCase],
    playbook: Playbook,
    session_id: str,
    *,
    split: Split = Split.DEV,
) -> SplitScore:
    """Actor re-run on frozen JSON. This is the promote signal, not LiveScorer."""
    SCORE_LOG.append((session_id, split.value))
    node = "Eval Hold" if split is Split.HOLDOUT else "Eval DEV"
    emit_node(actor.sink, node, title=session_id, payload={"n": len(cases), "split": split.value})
    turns: list[ActorTurn] = []
    passed: list[bool] = []
    cost = 0.0
    tokens = 0
    speed_ms = 0.0
    tool_calls = 0
    for case in cases:
        turn = actor.run(
            case.question,
            playbook=playbook,
            session_id=session_id,
            prompt_variant="baseline",
            split=split,
            task=_task_payload(case),
        )
        turns.append(turn)
        passed.append(_case_passed(case, turn))
        cost += turn.cost
        tokens += turn.tokens
        speed_ms += turn.speed_ms
        tool_calls += len(turn.tool_calls)
    n = len(cases)
    successes = sum(passed)
    return SplitScore(
        pass_rate=round(successes / n, 4) if n else 0.0,
        successes=successes,
        n=n,
        cost=round(cost, 6),
        tokens=tokens,
        turns=turns,
        passed=passed,
        split=split,
        speed_ms=round(speed_ms, 1),
        tool_calls=tool_calls,
    )


def _task_payload(case: ChallengeCase) -> dict | None:
    if not case.task_type:
        return None
    return {"type": case.task_type, "github": case.github, "id": case.id}


def _case_passed(case: ChallengeCase, turn: ActorTurn) -> bool:
    if case.expected_obj:
        return score_frozen(case.expected_obj, turn.text, turn.answer)
    return case_passes(case.expected, turn.text)


def _train_spans(score: SplitScore, cases: list[ChallengeCase] | None = None) -> list:
    """DEV spans from cases the eval scored wrong. Hold-out never reaches here."""
    ids = [case.id for case in cases] if cases else []
    spans = []
    for index, (turn, ok) in enumerate(zip(score.turns, score.passed, strict=True)):
        if ok:
            continue
        for span in turn.spans:
            if span.span_kind is SpanKind.LLM and str(span.raw.get("split") or "") not in {
                "holdout",
                "held_out",
                "held-out",
            }:
                span.raw["eval_failed"] = True
                span.raw["case_id"] = ids[index] if index < len(ids) else ""
                spans.append(span)
    return spans


def _io_clients(challenge: Any, *, live: bool) -> tuple[ChatClient, GithubMcp]:
    """Branch only at Chat / GitHub MCP IO. Pipeline above this is shared."""
    return ChatClient(offline=not live), GithubMcp(challenge.github, offline=not live)


def run_demo(
    challenge_id: str,
    *,
    work_root: Path,
    challenges_path: Path | None = None,
    offline: bool | None = None,
    mode: str = "offline",
) -> DemoReport:
    SCORE_LOG.clear()
    if offline is not None:
        mode = "offline" if offline else "live"
    live = mode == "live"
    if challenge_id in {"frozen", "github_triage_frozen", ""}:
        challenge = load_frozen_eval()
    else:
        challenge = load_challenge(challenge_id, challenges_path)
    work_root.mkdir(parents=True, exist_ok=True)
    journal = JournalStore(work_root / "journal")
    memory = MemoryStore(work_root)
    skills = SkillLibrary(work_root / "skills" / "library.json")
    skills.create_if_missing(
        SkillEntry(
            id="readonly-lookup",
            name="repo.readonly_lookup",
            body="Use issue_read, list_issues, list_label, search_code, get_file_contents. Never write.",
            version="1",
            tags=["github", "readonly"],
        )
    )
    sink = NeatlogsTraceSink.from_env()
    if hasattr(sink, "session_id"):
        sink.session_id = f"journeyman-{mode}-{challenge.id}"
        sink.workflow_name = f"journeyman-{challenge.id}"
    chat, github = _io_clients(challenge, live=live)
    actor = Actor(
        chat=chat,
        github=github,
        skills=skills,
        scripts=memory.scripts,
        sink=sink,
        repo=challenge.repo,
        router=CostRouter(),
    )
    pointer = VersionPointer(active=challenge.weak_playbook.version)
    playbook = challenge.weak_playbook
    memory.save_playbook(playbook)
    memory.save_pointer(pointer)

    run1 = score_split(actor, challenge.dev, playbook, "demo-run1", split=Split.DEV)
    journal.persist_lesson(
        JournalEntry(
            id="lesson-run1",
            kind=JournalKind.LESSON,
            text=f"Run1 DEV {run1.pass_rate} with weak playbook {pointer.active}",
            session_id="demo-run1",
            version=pointer.active,
        )
    )

    ingest = TraceIngest(sink=sink)
    ingest.offer(_train_spans(run1, challenge.dev))
    cycle = SuperviseCycle(ingest=ingest, journal=journal)
    item = cycle.run_once()
    candidate_version = item.candidate_prompt_version if item else None
    candidate_prompt = item.candidate_prompt if item else None
    diff_path = work_root / "journal" / "candidate.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_text = item.prompt_diff if item and item.prompt_diff else ""
    diff_path.write_text(diff_text, encoding="utf-8")

    BudgetedEvolver().run(
        PatchBudgetCounters(max_cycles=2),
        scores=[run1.pass_rate, 1.0 if candidate_prompt else run1.pass_rate],
    )

    promoted = False
    run_n = run1
    hold_prior: SplitScore | None = None
    hold_candidate: SplitScore | None = None
    redteam: dict[str, Any] | None = None
    if candidate_prompt and candidate_version:
        pointer = VersionPointer(active=pointer.active, candidate=candidate_version)
        candidate_book = Reflect().from_failures(
            playbook,
            _train_spans(run1, challenge.dev),
            version=candidate_version,
            candidate_prompt=candidate_prompt,
            chat=chat,
            router=actor.router,
            sink=sink,
            journal=journal,
            tools=actor,
            repo=challenge.repo,
        )
        memory.save_playbook(candidate_book)
        memory.save_pointer(pointer)
        cand_dev = score_split(actor, challenge.dev, candidate_book, "demo-cand-dev", split=Split.DEV)
        improved = cand_dev.pass_rate > run1.pass_rate
        if improved:
            hold_prior = score_split(
                actor, challenge.held_out, playbook, "demo-hold-prior", split=Split.HOLDOUT
            )
            hold_candidate = score_split(
                actor, challenge.held_out, candidate_book, "demo-hold-cand", split=Split.HOLDOUT
            )
            holdout_ok = hold_candidate.pass_rate >= hold_prior.pass_rate
            if holdout_ok:
                pointer = VersionPointer(active=candidate_version, prior=playbook.version, candidate=None)
                playbook = candidate_book
                promoted = True
                run_n = cand_dev
                memory.save_playbook(playbook)
                memory.save_pointer(pointer)
                redteam = attack_live(
                    actor,
                    playbook,
                    challenge.dev,
                    sink=sink,
                    pass_fn=_case_passed,
                )
                if item is not None:
                    item.stage = Stage.RED_TEAMED
                journal.persist_lesson(
                    JournalEntry(
                        id="lesson-promote",
                        kind=JournalKind.LESSON,
                        text=(
                            f"promoted {candidate_version} DEV {cand_dev.pass_rate} "
                            f"holdout prior {hold_prior.pass_rate} candidate {hold_candidate.pass_rate}"
                        ),
                        session_id="demo-promote",
                        version=candidate_version,
                    )
                )
            else:
                journal.persist_lesson(
                    JournalEntry(
                        id="lesson-hold",
                        kind=JournalKind.WARNING,
                        text="candidate held; hold-out collapsed vs prior active",
                        session_id="demo-hold",
                        version=candidate_version,
                    )
                )
                run_n = score_split(actor, challenge.dev, playbook, "demo-runn", split=Split.DEV)
        else:
            journal.persist_lesson(
                JournalEntry(
                    id="lesson-hold",
                    kind=JournalKind.WARNING,
                    text="candidate held; DEV did not improve",
                    session_id="demo-hold",
                    version=candidate_version,
                )
            )
            run_n = score_split(actor, challenge.dev, playbook, "demo-runn", split=Split.DEV)
    else:
        run_n = score_split(actor, challenge.dev, playbook, "demo-runn", split=Split.DEV)

    eval_result = EvalResult(
        eval_id=f"{challenge.id}-demo",
        baseline_pass_rate=run1.pass_rate,
        candidate_pass_rate=run_n.pass_rate,
        n=run1.n,
        baseline_successes=run1.successes,
        candidate_successes=run_n.successes,
    )
    fill_eval_result(eval_result)
    trace_id = flush_sink(sink)
    neatlogs_url = ""
    if hasattr(sink, "cockpit_url"):
        neatlogs_url = sink.cockpit_url()
    elif trace_id:
        neatlogs_url = dashboard_trace_url(trace_id)
    children = []
    payload = getattr(sink, "last_payload", None)
    if isinstance(payload, dict):
        children = list(payload.get("children") or [])
    journal_text = ""
    core = journal.root / "CORE.md"
    if core.exists():
        journal_text = core.read_text(encoding="utf-8")
    report = DemoReport(
        challenge_id=challenge.id,
        run1=run1,
        run_n=run_n,
        hold_prior=hold_prior,
        hold_candidate=hold_candidate,
        promoted=promoted,
        pointer=pointer,
        eval_result=eval_result,
        journal_path=journal.root / "CORE.md",
        diff_path=diff_path,
        candidate_version=candidate_version,
        score_log=list(SCORE_LOG),
        mode=mode,
        neatlogs_trace_id=trace_id or getattr(sink, "last_trace_id", None),
        neatlogs_url=neatlogs_url,
        journal_text=journal_text,
        diff_text=diff_text,
        playbook_entries=[entry.model_dump() for entry in playbook.entries],
        playbook_rules=[_rule_view(rule) for rule in playbook.rules],
        redteam=redteam,
        children=children,
        repo=challenge.repo,
    )
    write_artifacts(report, work_root)
    return report


def render(report: DemoReport) -> str:
    delta_pass = round(report.run_n.pass_rate - report.run1.pass_rate, 4)
    delta_cost = round(report.run_n.cost - report.run1.cost, 6)
    status = "PROMOTED" if report.promoted else "HELD"
    hold_prior = report.hold_prior.pass_rate if report.hold_prior else float("nan")
    hold_cand = report.hold_candidate.pass_rate if report.hold_candidate else float("nan")
    neat = report.neatlogs_trace_id or "(disabled)"
    lines = [
        f"challenge {report.challenge_id} mode={report.mode}",
        f"Run1  DEV pass={report.run1.pass_rate:.2f} cost={report.run1.cost:.4f} tokens={report.run1.tokens} tools={report.run1.tool_calls} ms={report.run1.speed_ms:.0f}",
        f"RunN  DEV pass={report.run_n.pass_rate:.2f} cost={report.run_n.cost:.4f} tokens={report.run_n.tokens} tools={report.run_n.tool_calls} ms={report.run_n.speed_ms:.0f}",
        f"delta pass={delta_pass:+.2f} cost={delta_cost:+.4f} {status}",
        f"holdout (sealed at promote) prior={hold_prior:.2f} candidate={hold_cand:.2f}",
        f"pointer active={report.pointer.active} candidate={report.pointer.candidate}",
        f"eval wilson=({report.eval_result.wilson_low}, {report.eval_result.wilson_high})",
        f"candidate version={report.candidate_version or ''} status={VersionStatus.CANDIDATE.value} until promote",
        f"neatlogs trace_id={neat} {report.neatlogs_url}",
        f"journal {report.journal_path}",
        f"candidate diff {report.diff_path}",
        f"report json {report.report_path}",
        f"ui {report.ui_path}",
    ]
    if report.redteam:
        lines.append(
            f"redteam live pass={report.redteam['pass_rate']:.2f} n={report.redteam['n']}"
        )
    return "\n".join(lines)


def _rule_view(rule: Any) -> dict[str, Any]:
    """Slim human rule for the artifact UI. Not CORE.md telemetry."""
    evidence = getattr(rule, "evidence", None)
    origin = getattr(evidence, "origin", None)
    return {
        "id": rule.id,
        "text": rule.describe(),
        "kind": rule.kind.value if hasattr(rule.kind, "value") else str(rule.kind),
        "status": rule.status.value if hasattr(rule.status, "value") else str(getattr(rule, "status", "")),
        "origin": origin.value if hasattr(origin, "value") else str(origin or ""),
        "source": getattr(evidence, "source", "") or "",
        "refs": list(getattr(evidence, "refs", []) or []),
        "note": getattr(evidence, "note", "") or "",
    }


def rollback_demo(work_root: Path) -> VersionPointer:
    return MemoryStore(work_root).rollback()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Journeyman readonly GitHub demo loop")
    parser.add_argument("--challenge", default="frozen")
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--work-root", default=".")
    parser.add_argument("--challenges", default="", help="override fixtures/challenges directory")
    parser.add_argument("--rollback", action="store_true", help="restore the prior playbook pointer")
    args = parser.parse_args(argv)
    if args.rollback:
        pointer = rollback_demo(Path(args.work_root))
        print(f"rolled back active={pointer.active} prior={pointer.prior}")
        return 0
    report = run_demo(
        args.challenge,
        work_root=Path(args.work_root),
        challenges_path=Path(args.challenges) if args.challenges else challenges_dir(),
        mode=args.mode,
    )
    print(render(report))
    return 0 if report.run_n.pass_rate > report.run1.pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
