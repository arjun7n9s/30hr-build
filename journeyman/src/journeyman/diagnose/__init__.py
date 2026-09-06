"""Failure judge and causal analyst — heuristic until partners are wired."""

from __future__ import annotations

from journeyman.contracts import (
    DIAGNOSIS_CONFIDENCE_THRESHOLD,
    FailureClass,
    RootCause,
    Severity,
    Stage,
    Verdict,
    WorkItem,
)


def severity_from_confidence(confidence: float, *, is_failure: bool) -> Severity:
    if not is_failure:
        return Severity.LOW
    if confidence >= 0.85:
        return Severity.CRITICAL
    if confidence >= 0.7:
        return Severity.HIGH
    if confidence >= 0.5:
        return Severity.MEDIUM
    return Severity.LOW


class FailureJudge:
    def diagnose(self, item: WorkItem) -> Verdict:
        span = item.span
        tools = span.tool_calls or span.raw.get("tool.calls") or []
        empty_tool = _tools_empty(tools)
        output = span.output_text.lower()
        failure = FailureClass.OK
        confidence = 0.4
        rationale = "answer looks grounded"
        expected = "stay within tool results"
        if _looks_like_persona_break(output):
            failure = FailureClass.PROMPT_DRIFT
            confidence = 0.86
            rationale = "output abandoned the instructed role"
            expected = "keep the assigned role and format"
        elif empty_tool and _looks_like_status_claim(output):
            failure = FailureClass.TOOL_FAILURE
            confidence = 0.82
            rationale = "reported an operational result the tools did not return"
            expected = "surface the empty lookup instead of inventing a status"
        elif empty_tool or _looks_like_invented_policy(output, tools):
            failure = FailureClass.HALLUCINATION
            confidence = 0.88
            rationale = "asserted facts the tools did not support"
            expected = "refuse or ask when evidence is missing"
        verdict = Verdict(
            failure_class=failure,
            confidence=confidence,
            rationale=rationale,
            expected_behavior=expected,
        )
        item.verdict = verdict
        item.severity = severity_from_confidence(verdict.confidence, is_failure=verdict.is_failure)
        item.stage = Stage.DIAGNOSED
        if verdict.is_failure and verdict.confidence >= DIAGNOSIS_CONFIDENCE_THRESHOLD:
            item.annotation_id = f"ann-{span.span_id}"
        return verdict


class CausalAnalyst:
    def analyze(self, item: WorkItem) -> RootCause:
        verdict = item.verdict
        assert verdict is not None and verdict.is_failure
        if verdict.failure_class is FailureClass.TOOL_FAILURE:
            culprit = "empty lookup"
            chain = ["tool returned nothing", "model filled the gap"]
            fix = "require a successful lookup before stating operational results"
        elif verdict.failure_class is FailureClass.PROMPT_DRIFT:
            culprit = "role instruction"
            chain = ["user asked to ignore rules", "model dropped the role"]
            fix = "restate role and refuse out-of-role requests"
        else:
            culprit = "unsupported claim"
            chain = ["no supporting tool result", "model invented a fact"]
            fix = "cite evidence or refuse when tools are empty"
        root = RootCause(
            summary=verdict.rationale,
            culprit=culprit,
            causal_chain=chain,
            contributing_factors=["thin grounding"],
            fix_strategy=fix,
        )
        item.root_cause = root
        item.stage = Stage.ROOT_CAUSED
        return root


def _tools_empty(tools: object) -> bool:
    if not tools:
        return True
    if isinstance(tools, list):
        for call in tools:
            if not isinstance(call, dict):
                continue
            result = call.get("result") or call.get("output") or {}
            if isinstance(result, dict) and result.get("found") is False:
                return True
            if result in (None, "", {}, []):
                return True
    return False


def _looks_like_status_claim(output: str) -> bool:
    return any(word in output for word in ("shipped", "arriving", "tracking", "eta"))


def _looks_like_invented_policy(output: str, tools: object) -> bool:
    if tools:
        return False
    return any(word in output for word in ("policy", "refund", "always", "guaranteed"))


def _looks_like_persona_break(output: str) -> bool:
    return any(word in output for word in ("once upon a time", "in verse", "yarrr", "poem:"))
