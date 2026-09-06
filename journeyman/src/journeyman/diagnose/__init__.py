"""Failure judge and causal analyst stubs."""

from journeyman.contracts import RootCause, Verdict, WorkItem


class FailureJudge:
    def diagnose(self, item: WorkItem) -> Verdict:
        raise NotImplementedError


class CausalAnalyst:
    def analyze(self, item: WorkItem) -> RootCause:
        raise NotImplementedError
