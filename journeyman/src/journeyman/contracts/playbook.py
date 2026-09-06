"""Playbook entry and harness-index contracts."""

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.rule import Rule


class PlaybookEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    version: str = "0"


class Playbook(BaseModel):
    """One version of memory: prose entries the actor reads, plus executable rules.

    Rules live here rather than in a side store so that promote and rollback move
    beliefs and prompt text together — a version pointer is the whole mind.
    """

    model_config = ConfigDict(extra="forbid")

    version: str
    entries: list[PlaybookEntry] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    empty: bool = True


class HarnessRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str


class PlaybookIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harnesses: list[HarnessRef] = Field(default_factory=list)
