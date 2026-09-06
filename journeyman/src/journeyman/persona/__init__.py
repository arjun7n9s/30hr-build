"""Persona router and step predictor stubs."""

from journeyman.contracts import CostRouterDecision, WorkItem


class PersonaRouter:
    def route(self, work_item: WorkItem) -> CostRouterDecision:
        raise NotImplementedError


class StepPredictor:
    def predict(self, work_item: WorkItem) -> list[str]:
        raise NotImplementedError
