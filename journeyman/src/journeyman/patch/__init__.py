"""Prompt surgeon stub."""

from journeyman.contracts import WorkItem


class PromptSurgeon:
    def propose(self, item: WorkItem) -> WorkItem:
        raise NotImplementedError
