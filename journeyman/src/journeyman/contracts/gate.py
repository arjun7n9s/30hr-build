"""Quality-gate contracts."""

from pydantic import BaseModel, ConfigDict

from journeyman.contracts.constants import REGRESSION_GATE_THRESHOLD


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    score: float
    threshold: float = REGRESSION_GATE_THRESHOLD
    reason: str = ""
    logged: bool = True
