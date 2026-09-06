"""Context gate and supervise cycle."""

from __future__ import annotations

from typing import Any

from journeyman.contracts import (
    DualPassResult,
    GateDecision,
    REGRESSION_GATE_THRESHOLD,
    StructuredSendoff,
    WorkItem,
)
from journeyman.diagnose import CausalAnalyst, FailureJudge
from journeyman.eval import LiveScorer
from journeyman.evalset import ProbeFactory
from journeyman.ingest import TraceIngest
from journeyman.journal import JournalStore
from journeyman.patch import PromptSurgeon
from journeyman.verify import AdversarialProbe, ExactReplay


class ContextGate:
    def enter(
        self,
        name: str,
        payload: dict[str, Any],
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        brief: str = "",
    ) -> StructuredSendoff:
        include = include or list(payload)
        exclude = exclude or []
        kept = {
            key: value
            for key, value in payload.items()
            if key in include and key not in exclude
        }
        return StructuredSendoff(
            brief=brief or name,
            include=include,
            exclude=exclude,
            payload=kept,
        )

    def exit(self, sendoff: StructuredSendoff, tool: str = "sendoff") -> DualPassResult:
        return DualPassResult(
            live_allowed=True,
            shadow_allowed=True,
            divergence=False,
            tool=tool,
            policy_version=sendoff.brief or "sendoff",
        )

    def check(self, name: str, value: float, context: dict[str, Any] | None = None) -> GateDecision:
        passed = value >= REGRESSION_GATE_THRESHOLD
        return GateDecision(
            passed=passed,
            score=value,
            reason=name if passed else f"{name} below gate",
        )


class SuperviseCycle:
    """TraceIngest.poll → FailureJudge.diagnose → skip if not failure → CausalAnalyst.analyze → ProbeFactory.synthesize → resolve baseline → LiveScorer.run_baseline → PromptSurgeon.propose (candidate only) → LiveScorer.run_candidate → ExactReplay.replay → AdversarialProbe.attack → persist postmortem stub"""

    def __init__(
        self,
        ingest: TraceIngest | None = None,
        judge: FailureJudge | None = None,
        analyst: CausalAnalyst | None = None,
        probes: ProbeFactory | None = None,
        scorer: LiveScorer | None = None,
        surgeon: PromptSurgeon | None = None,
        replay: ExactReplay | None = None,
        redteam: AdversarialProbe | None = None,
        journal: JournalStore | None = None,
    ) -> None:
        self.ingest = ingest or TraceIngest()
        self.judge = judge or FailureJudge()
        self.analyst = analyst or CausalAnalyst()
        self.probes = probes or ProbeFactory()
        self.scorer = scorer or LiveScorer()
        self.surgeon = surgeon or PromptSurgeon()
        self.replay = replay or ExactReplay()
        self.redteam = redteam or AdversarialProbe()
        self.journal = journal or JournalStore()

    def run_once(self) -> WorkItem | None:
        for item in self.ingest.poll():
            self.ingest._mark(item.span.span_id)
            handled = self.run(item)
            if handled.verdict is None or not handled.verdict.is_failure:
                continue
            return handled
        return None

    def run(self, item: WorkItem) -> WorkItem:
        self.judge.diagnose(item)
        if item.verdict is None or not item.verdict.is_failure:
            return item
        self.analyst.analyze(item)
        self.probes.synthesize(item)
        item.baseline_prompt = _resolve_baseline(item)
        self.scorer.run_baseline(item)
        self.surgeon.propose(item)
        self.scorer.run_candidate(item)
        self.replay.replay(item)
        self.redteam.attack(item)
        self.journal.persist_postmortem(item)
        return item


def _resolve_baseline(item: WorkItem) -> str:
    if item.baseline_prompt:
        return item.baseline_prompt
    attrs = item.span.raw.get("attributes", {})
    if isinstance(attrs, dict):
        msgs = attrs.get("llm.input_messages")
        if isinstance(msgs, list):
            for message in msgs:
                inner = message.get("message", message) if isinstance(message, dict) else {}
                if isinstance(inner, dict) and inner.get("role") == "system":
                    content = inner.get("content", "")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
    return "Answer only from retrieved evidence. If evidence is missing, say so."
