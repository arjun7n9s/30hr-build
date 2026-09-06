"""Replay, adversarial probe, and suite runner stubs."""

from journeyman.contracts import EvalResult, ProbeSpec, RedTeamResult, ReplayResult, WorkItem


class ExactReplay:
    def replay(self, item: WorkItem) -> ReplayResult:
        raise NotImplementedError


class AdversarialProbe:
    def attack(self, item: WorkItem) -> RedTeamResult:
        raise NotImplementedError


class SuiteRunner:
    def run(self, probes: list[ProbeSpec], version: str) -> list[EvalResult]:
        raise NotImplementedError
