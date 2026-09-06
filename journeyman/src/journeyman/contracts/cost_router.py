"""Cheap-first routing contracts."""

from pydantic import BaseModel, ConfigDict

from journeyman.contracts.enums import RouteChoice


class CostRouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: RouteChoice
    reason: str
    estimated_cost: float = 0.0
    gate_miss: bool = False
