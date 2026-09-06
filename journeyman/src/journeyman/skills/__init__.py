"""Skill library: find → exec → create_if_missing. Persist SkillEntry."""

from __future__ import annotations

import json
from pathlib import Path

from journeyman.contracts import SkillAction, SkillEntry, SkillHit, SkillQuery


class SkillLibrary:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("skills") / "library.json"
        self._skills: dict[str, SkillEntry] = {}
        self._load()

    def find(self, query: SkillQuery) -> list[SkillHit]:
        needle = query.text.lower().strip()
        hits: list[SkillHit] = []
        for skill in self._skills.values():
            blob = " ".join([skill.name, skill.body, *skill.tags]).lower()
            if needle and needle in blob:
                score = 1.0 if skill.name.lower() == needle else 0.6
                hits.append(SkillHit(skill=skill, score=score, action=SkillAction.HIT))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: query.limit]

    def exec(self, name: str, args: dict[str, object] | None = None) -> str:
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(name)
        body = skill.body
        if args:
            try:
                body = body.format(**args)
            except (KeyError, IndexError, ValueError):
                pass
        return body

    def create_if_missing(self, skill: SkillEntry) -> SkillEntry:
        if skill.name.startswith("agent."):
            raise ValueError("namespaces starting with 'agent.' are reserved")
        existing = self._skills.get(skill.name)
        if existing is not None:
            return existing
        self._skills[skill.name] = skill
        self._persist()
        return skill

    def search(self, query: SkillQuery) -> list[SkillHit]:
        return self.find(query)

    def write(self, skill: SkillEntry) -> list[SkillHit]:
        stored = self.create_if_missing(skill)
        return [SkillHit(skill=stored, score=1.0, action=SkillAction.WRITE)]

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for row in raw:
            entry = SkillEntry.model_validate(row)
            self._skills[entry.name] = entry

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [skill.model_dump() for skill in self._skills.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
