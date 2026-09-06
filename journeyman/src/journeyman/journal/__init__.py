"""Journal store stub."""

from journeyman.contracts import Journal, JournalEntry, WorkItem


class JournalStore:
    def append(self, entry: JournalEntry) -> Journal:
        raise NotImplementedError

    def list(self) -> Journal:
        raise NotImplementedError

    def persist_postmortem(self, item: WorkItem) -> None:
        raise NotImplementedError
