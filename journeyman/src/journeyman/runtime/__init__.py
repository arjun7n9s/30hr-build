"""Context gate and supervise-cycle stubs."""

from typing import Any

from journeyman.contracts import GateDecision, WorkItem


class ContextGate:
    def check(self, name: str, value: float, context: dict[str, Any] | None = None) -> GateDecision:
        raise NotImplementedError


class SuperviseCycle:
    """TraceIngest.poll → FailureJudge.diagnose → skip if not failure → CausalAnalyst.analyze → ProbeFactory.synthesize → resolve baseline → LiveScorer.run_baseline → PromptSurgeon.propose (candidate only) → LiveScorer.run_candidate → ExactReplay.replay → AdversarialProbe.attack → persist postmortem stub"""

    def run(self, item: WorkItem) -> WorkItem:
        raise NotImplementedError
