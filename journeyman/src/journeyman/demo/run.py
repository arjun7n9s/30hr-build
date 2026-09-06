"""CLI: Run1 DEV only → supervise cycle → sealed hold-out at promote → RunN."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from journeyman.contracts import (
    EvalResult,
    JournalEntry,
    JournalKind,
    PatchBudgetCounters,
    Playbook,
    PlaybookEntry,
    SkillEntry,
    SpanKind,
    Split,
    VersionPointer,
    VersionStatus,
)
from journeyman.demo.challenge import ChallengeCase, challenges_dir, load_challenge
from journeyman.evolve import BudgetedEvolver
from journeyman.ingest import TraceIngest
from journeyman.journal import JournalStore
from journeyman.partners.chat import ChatClient
from journeyman.partners.github import GitHubClient
from journeyman.partners.sink import NeatlogsTraceSink
from journeyman.runtime import SuperviseCycle
from journeyman.runtime.actor import Actor, ActorTurn
from journeyman.skills import SkillLibrary
from journeyman.stats.ab import fill_eval_result

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
    SCORE_LOG.append((session_id, split.value))
    turns: list[ActorTurn] = []
    passed: list[bool] = []
    cost = 0.0
    tokens = 0
    for case in cases:
        turn = actor.run(
            case.question,
            playbook=playbook,
            session_id=session_id,
            prompt_variant="baseline",
            split=split,
        )
        turns.append(turn)
        passed.append(case_passes(case.expected, turn.text))
        cost += turn.cost
        tokens += turn.tokens
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
    )


def playbook_from_candidate(item_prompt: str, version: str) -> Playbook:
    return Playbook(
        version=version,
        empty=False,
        entries=[
            PlaybookEntry(
                id="candidate-rule",
                text=item_prompt,
                tags=["candidate", "evidence"],
                version=version,
            )
        ],
    )


def _train_spans(score: SplitScore) -> list:
    spans = []
    for turn, ok in zip(score.turns, score.passed, strict=True):
        if ok:
            continue
        for span in turn.spans:
            if span.span_kind is SpanKind.LLM and str(span.raw.get("split") or "") not in {
                "holdout",
                "held_out",
                "held-out",
            }:
                spans.append(span)
    return spans


def run_demo(
    challenge_id: str,
    *,
    work_root: Path,
    challenges_path: Path | None = None,
    offline: bool = True,
) -> DemoReport:
    SCORE_LOG.clear()
    challenge = load_challenge(challenge_id, challenges_path)
    work_root.mkdir(parents=True, exist_ok=True)
    journal = JournalStore(work_root / "journal")
    skills = SkillLibrary(work_root / "skills" / "library.json")
    skills.create_if_missing(
        SkillEntry(
            id="readonly-lookup",
            name="repo.readonly_lookup",
            body="Use list_issues, get_issue, search_code, get_file_contents. Never write.",
            version="1",
            tags=["github", "readonly"],
        )
    )
    sink = NeatlogsTraceSink.from_env()
    github = GitHubClient(challenge.github, offline=offline)
    chat = ChatClient(offline=offline)
    actor = Actor(
        chat=chat,
        github=github,
        skills=skills,
        sink=sink,
        repo=challenge.repo,
    )
    pointer = VersionPointer(active=challenge.weak_playbook.version)
    playbook = challenge.weak_playbook

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
    ingest.offer(_train_spans(run1))
    cycle = SuperviseCycle(ingest=ingest, journal=journal)
    item = cycle.run_once()
    candidate_version = item.candidate_prompt_version if item else None
    candidate_prompt = item.candidate_prompt if item else None
    diff_path = work_root / "journal" / "candidate.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text((item.prompt_diff if item and item.prompt_diff else ""), encoding="utf-8")

    BudgetedEvolver().run(
        PatchBudgetCounters(max_cycles=2),
        scores=[run1.pass_rate, 1.0 if candidate_prompt else run1.pass_rate],
    )

    promoted = False
    run_n = run1
    hold_prior: SplitScore | None = None
    hold_candidate: SplitScore | None = None
    if candidate_prompt and candidate_version:
        pointer = VersionPointer(active=pointer.active, candidate=candidate_version)
        candidate_book = playbook_from_candidate(candidate_prompt, candidate_version)
        cand_dev = score_split(actor, challenge.dev, candidate_book, "demo-cand-dev", split=Split.DEV)
        improved = cand_dev.pass_rate > run1.pass_rate
        if improved:
            # Sealed hold-out: scored only at promote, never offered to ingest.
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
    return DemoReport(
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
    )


def render(report: DemoReport) -> str:
    delta_pass = round(report.run_n.pass_rate - report.run1.pass_rate, 4)
    delta_cost = round(report.run_n.cost - report.run1.cost, 6)
    status = "PROMOTED" if report.promoted else "HELD"
    hold_prior = report.hold_prior.pass_rate if report.hold_prior else float("nan")
    hold_cand = report.hold_candidate.pass_rate if report.hold_candidate else float("nan")
    lines = [
        f"challenge {report.challenge_id}",
        f"Run1  DEV pass={report.run1.pass_rate:.2f} cost={report.run1.cost:.4f} tokens={report.run1.tokens}",
        f"RunN  DEV pass={report.run_n.pass_rate:.2f} cost={report.run_n.cost:.4f} tokens={report.run_n.tokens}",
        f"delta pass={delta_pass:+.2f} cost={delta_cost:+.4f} {status}",
        f"holdout (sealed at promote) prior={hold_prior:.2f} candidate={hold_cand:.2f}",
        f"pointer active={report.pointer.active} candidate={report.pointer.candidate}",
        f"eval wilson=({report.eval_result.wilson_low}, {report.eval_result.wilson_high})",
        f"candidate version={report.candidate_version or ''} status={VersionStatus.CANDIDATE.value} until promote",
        f"journal {report.journal_path}",
        f"candidate diff {report.diff_path}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Journeyman readonly GitHub demo loop")
    parser.add_argument("--challenge", default="github_triage_v1")
    parser.add_argument("--work-root", default=".")
    parser.add_argument("--challenges", default="", help="override fixtures/challenges directory")
    args = parser.parse_args(argv)
    report = run_demo(
        args.challenge,
        work_root=Path(args.work_root),
        challenges_path=Path(args.challenges) if args.challenges else challenges_dir(),
        offline=True,
    )
    print(render(report))
    return 0 if report.run_n.pass_rate > report.run1.pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
