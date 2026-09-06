"""Versioned patch budget counters."""

from pydantic import BaseModel, ConfigDict


class PatchBudgetCounters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_cycles: int
    used_cycles: int = 0
    max_cost_units: float = 0.0
    used_cost_units: float = 0.0
    last_accuracy: float | None = None
    best_accuracy: float | None = None
    no_improve: bool = False

    def should_stop(self) -> bool:
        if self.used_cycles >= self.max_cycles:
            return True
        if self.max_cost_units > 0 and self.used_cost_units >= self.max_cost_units:
            return True
        return self.no_improve
