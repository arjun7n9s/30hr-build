"""Version pointer contracts."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import VersionAction, VersionStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VersionPointer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: str
    candidate: str | None = None
    prior: str | None = None


class VersionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    parent: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    notes: str = ""
    status: VersionStatus = VersionStatus.CANDIDATE


class VersionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: VersionAction
    pointer: VersionPointer
    reason: str = ""
