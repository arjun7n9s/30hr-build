"""Skill-library contracts (search-before-write)."""

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import SkillAction


class SkillEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    body: str
    version: str
    tags: list[str] = Field(default_factory=list)


class SkillQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    limit: int = 5


class SkillHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: SkillEntry
    score: float
    action: SkillAction = SkillAction.HIT
