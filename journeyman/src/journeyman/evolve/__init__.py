"""Budgeted evolver: stop on budget, no_improve>=3, or max rounds. Promote best only."""

from __future__ import annotations

from collections.abc import Sequence

from journeyman.contracts import (
    EvolveRunJournal,
    JournalEntry,
    JournalKind,
    PatchBudgetCounters,
    VersionAction,
    VersionChange,
    VersionPointer,
    WorkItem,
)


class BudgetedEvolver:
    def run(
        self,
        budget: PatchBudgetCounters,
        scores: Sequence[float] | None = None,
        item: WorkItem | None = None,
    ) -> EvolveRunJournal:
        series = list(scores) if scores is not None else _scores_from_item(item)
        best_round: int | None = None
        entries: list[JournalEntry] = []
        stop_reason = "complete"
        for index, score in enumerate(series, start=1):
            if budget.should_stop():
                stop_reason = _stop_reason(budget)
                break
            budget.used_cycles += 1
            budget.last_accuracy = score
            if budget.best_accuracy is None or score > budget.best_accuracy:
                budget.best_accuracy = score
                budget.no_improve = 0
                best_round = budget.used_cycles
            else:
                budget.no_improve += 1
            entries.append(
                JournalEntry(
                    id=f"evolve-{budget.used_cycles}",
                    kind=JournalKind.INSIGHT,
                    text=f"round {budget.used_cycles} accuracy {score}",
                    session_id=item.span.session_id if item else "evolve",
                )
            )
        else:
            if budget.should_stop():
                stop_reason = _stop_reason(budget)
        promoted: str | None = None
        if best_round is not None:
            promoted = (
                item.candidate_prompt_version
                if item and item.candidate_prompt_version
                else f"best-r{best_round}"
            )
            VersionChange(
                action=VersionAction.PROMOTE,
                pointer=VersionPointer(active=promoted, candidate=None, prior=None),
                reason="best accuracy only",
            )
        return EvolveRunJournal(
            rounds=budget.used_cycles,
            spent=budget.used_cost_units,
            best_accuracy=budget.best_accuracy,
            promoted_version=promoted,
            stop_reason=stop_reason,
            entries=entries,
        )


def _scores_from_item(item: WorkItem | None) -> list[float]:
    if item is None or item.eval_result is None:
        return []
    cand = item.eval_result.candidate_pass_rate
    return [item.eval_result.baseline_pass_rate] + ([cand] if cand is not None else [])


def _stop_reason(budget: PatchBudgetCounters) -> str:
    if budget.used_cycles >= budget.max_cycles:
        return "max_rounds"
    if budget.max_cost_units > 0 and budget.used_cost_units >= budget.max_cost_units:
        return "budget"
    if budget.no_improve >= 3:
        return "no_improve"
    return "complete"
