"""Skill library stub (search-before-write)."""

from journeyman.contracts import SkillEntry, SkillHit, SkillQuery


class SkillLibrary:
    def search(self, query: SkillQuery) -> list[SkillHit]:
        raise NotImplementedError

    def write(self, skill: SkillEntry) -> list[SkillHit]:
        raise NotImplementedError
