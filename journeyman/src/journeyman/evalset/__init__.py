"""Probe factory stub."""

from journeyman.contracts import ProbeSpec, WorkItem


class ProbeFactory:
    def synthesize(self, item: WorkItem) -> list[ProbeSpec]:
        raise NotImplementedError
