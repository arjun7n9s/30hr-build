"""Spend ledger stub."""


class SpendLedger:
    def record(self, run_id: str, cost_units: float) -> None:
        raise NotImplementedError

    def total(self) -> float:
        raise NotImplementedError
