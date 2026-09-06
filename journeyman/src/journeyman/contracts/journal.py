"""Journal contracts."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import JournalKind


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: JournalKind
    text: str
    session_id: str
    version: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class Journal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_path: str = "journal/CORE.md"
    entries: list[JournalEntry] = Field(default_factory=list)
