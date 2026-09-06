"""Dual-pass policy stream and shadow-arm contracts."""

from pydantic import BaseModel, ConfigDict, Field

from journeyman.contracts.enums import PolicyArm


class ShadowArm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    policy_version: str
    enabled: bool = True


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    shadow: ShadowArm | None = None


class DualPass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live: PolicyArm = PolicyArm.LIVE
    policy: PolicyDocument
    shadow: ShadowArm | None = None


class DualPassResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live_allowed: bool
    shadow_allowed: bool | None = None
    divergence: bool = False
    tool: str
    policy_version: str
