"""Journal store and postmortem persistence."""

from __future__ import annotations

from pathlib import Path

from journeyman.contracts import Journal, JournalEntry, JournalKind, WorkItem


class JournalStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("journal")
        self._entries: list[JournalEntry] = []

    def append(self, entry: JournalEntry) -> Journal:
        self._entries.append(entry)
        return self.list()

    def list(self) -> Journal:
        return Journal(core_path=str(self.root / "CORE.md"), entries=list(self._entries))

    def persist_lesson(self, entry: JournalEntry) -> Path:
        self.append(entry)
        self.root.mkdir(parents=True, exist_ok=True)
        core = self.root / "CORE.md"
        if not core.exists():
            core.write_text("# Journal\n\n## Lessons\n\n", encoding="utf-8")
        with core.open("a", encoding="utf-8") as handle:
            handle.write(f"- {entry.text}\n")
        return core

    def persist_postmortem(self, item: WorkItem) -> None:
        sessions = self.root / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        verdict = item.verdict.failure_class.value if item.verdict else "unknown"
        severity = item.severity.value if item.severity else "low"
        lines = [
            f"# Work item {item.work_item_id}",
            "",
            f"- stage: {item.stage.value}",
            f"- failure: {verdict}",
            f"- severity: {severity}",
            f"- candidate version: {item.candidate_prompt_version or ''} (not live)",
        ]
        if item.root_cause:
            lines.append(f"- root cause: {item.root_cause.summary}")
        if item.eval_result:
            lines.append(
                f"- eval: baseline {item.eval_result.baseline_pass_rate}"
                f" candidate {item.eval_result.candidate_pass_rate}"
            )
        path = sessions / f"{item.work_item_id}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.append(
            JournalEntry(
                id=f"pm-{item.work_item_id}",
                kind=JournalKind.LESSON,
                text=f"postmortem {item.work_item_id}",
                session_id=item.span.session_id,
                version=item.candidate_prompt_version,
            )
        )
