"""Playbook entry and harness-index contracts."""

from pydantic import BaseModel, ConfigDict, Field


class PlaybookEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    version: str = "0"


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    entries: list[PlaybookEntry] = Field(default_factory=list)
    empty: bool = True


class HarnessRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str


class PlaybookIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harnesses: list[HarnessRef] = Field(default_factory=list)
