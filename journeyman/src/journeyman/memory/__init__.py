"""Durable playbook, scripts, and version pointer. Next run can read what this run learned."""

from __future__ import annotations

import json
from pathlib import Path

from journeyman.contracts import Playbook, PlaybookEntry, Rule, VersionPointer


class ScriptEntry:
    def __init__(self, *, id: str, name: str, body: str, version: str = "1") -> None:
        self.id = id
        self.name = name
        self.body = body
        self.version = version

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "body": self.body, "version": self.version}


class ScriptStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("scripts") / "library.json"
        self._items: dict[str, ScriptEntry] = {}
        self._load()

    def upsert(self, script: ScriptEntry) -> ScriptEntry:
        self._items[script.id] = script
        self._save()
        return script

    def find(self, query: str) -> list[ScriptEntry]:
        needle = query.lower()
        hits = [
            item
            for item in self._items.values()
            if not needle or needle in item.body.lower() or needle in item.name.lower() or item.body
        ]
        return hits[:8] or list(self._items.values())[:8]

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for row in raw.get("scripts") or []:
            self._items[row["id"]] = ScriptEntry(
                id=row["id"],
                name=row.get("name") or row["id"],
                body=row.get("body") or "",
                version=str(row.get("version") or "1"),
            )

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"scripts": [item.as_dict() for item in self._items.values()]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.playbooks = root / "playbooks"
        self.pointer_path = root / "versions" / "pointer.json"
        self.scripts = ScriptStore(root / "scripts" / "library.json")
        self.playbooks.mkdir(parents=True, exist_ok=True)
        (root / "versions").mkdir(parents=True, exist_ok=True)

    def save_playbook(self, playbook: Playbook) -> Path:
        path = self.playbooks / f"{playbook.version}.json"
        path.write_text(playbook.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_playbook(self, version: str) -> Playbook | None:
        path = self.playbooks / f"{version}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [PlaybookEntry(**row) for row in data.get("entries") or []]
        rules = [Rule(**row) for row in data.get("rules") or []]
        return Playbook(
            version=str(data.get("version") or version),
            entries=entries,
            rules=rules,
            empty=bool(data.get("empty", not entries and not rules)),
        )

    def save_pointer(self, pointer: VersionPointer) -> Path:
        self.pointer_path.write_text(pointer.model_dump_json(indent=2), encoding="utf-8")
        return self.pointer_path

    def load_pointer(self) -> VersionPointer | None:
        if not self.pointer_path.exists():
            return None
        data = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        return VersionPointer(
            active=str(data["active"]),
            candidate=data.get("candidate"),
            prior=data.get("prior"),
        )

    def rollback(self) -> VersionPointer:
        pointer = self.load_pointer()
        if pointer is None or not pointer.prior:
            raise RuntimeError("nothing to rollback")
        restored = VersionPointer(active=pointer.prior, prior=pointer.active, candidate=None)
        self.save_pointer(restored)
        return restored
