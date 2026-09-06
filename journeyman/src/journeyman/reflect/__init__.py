"""Reflect: merge/supersede a diffable PlaybookEntry list."""

from __future__ import annotations

from journeyman.contracts import Playbook, PlaybookEntry, Stage
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.partners.sink import emit_node


class Reflect:
    def merge(
        self,
        current: Playbook,
        incoming: list[PlaybookEntry],
        *,
        sink: TraceSink | None = None,
        version: str | None = None,
    ) -> Playbook:
        by_id = {entry.id: entry for entry in current.entries}
        superseded: list[str] = []
        for entry in incoming:
            if entry.id in by_id:
                superseded.append(entry.id)
            by_id[entry.id] = entry
        next_version = version or (incoming[0].version if incoming else current.version)
        merged = Playbook(version=next_version, entries=list(by_id.values()), empty=len(by_id) == 0)
        emit_node(
            sink or NullTraceSink(),
            "Reflect",
            title="merge",
            stage=Stage.PATCHED,
            detail=next_version,
            payload={"superseded": superseded, "n": len(merged.entries)},
        )
        return merged
