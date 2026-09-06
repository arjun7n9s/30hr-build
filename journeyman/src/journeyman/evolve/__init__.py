"""Budgeted evolver stub."""

from journeyman.contracts import PatchBudgetCounters, WorkItem


class BudgetedEvolver:
    def step(self, budget: PatchBudgetCounters, item: WorkItem) -> PatchBudgetCounters:
        raise NotImplementedError
