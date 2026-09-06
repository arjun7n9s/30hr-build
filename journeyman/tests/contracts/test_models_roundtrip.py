"""Roundtrip, should_stop, WorkItem.from_span, and enum snapshot."""

from datetime import datetime, timezone
from enum import Enum

from journeyman.contracts import (
    AB_MIN_DELTA_PP,
    AB_MIN_RUNS,
    AB_SIGNIFICANT_P,
    DIAGNOSIS_CONFIDENCE_THRESHOLD,
    ENUM_SNAPSHOT,
    EVAL_MAX_CASES,
    NO_IMPROVE_LIMIT,
    REDTEAM_MAX_ATTACKS,
    REGRESSION_GATE_THRESHOLD,
    SEEN_RING_MAX,
    WILSON_Z,
    CostRouterDecision,
    DualPass,
    DualPassResult,
    EscalateReason,
    EvolveRunJournal,
    EfficiencyReport,
    EvalResult,
    FailureClass,
    GateDecision,
    HarnessRef,
    Journal,
    JournalEntry,
    JournalKind,
    PatchBudgetCounters,
    Playbook,
    PlaybookEntry,
    PlaybookIndex,
    PolicyArm,
    PolicyDocument,
    ProbeSpec,
    RedTeamResult,
    ReplayResult,
    RootCause,
    RouteChoice,
    Severity,
    ShadowArm,
    SkillAction,
    SkillEntry,
    SkillHit,
    SkillQuery,
    SpanKind,
    Split,
    Stage,
    StructuredSendoff,
    TraceEventRow,
    TraceSpan,
    Verdict,
    VersionAction,
    VersionStatus,
    VersionChange,
    VersionPointer,
    VersionRecord,
    WorkItem,
)


def _span() -> TraceSpan:
    return TraceSpan(
        span_id="span-1",
        trace_id="trace-1",
        project="live",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        input_text="what failed",
        output_text="a guess",
        session_id="live",
        prompt_variant="baseline",
        span_kind=SpanKind.LLM,
    )


def test_enum_snapshot() -> None:
    lookup = {
        "FailureClass": FailureClass,
        "Severity": Severity,
        "Stage": Stage,
        "SpanKind": SpanKind,
        "Split": Split,
        "RouteChoice": RouteChoice,
        "JournalKind": JournalKind,
        "SkillAction": SkillAction,
        "PolicyArm": PolicyArm,
        "VersionAction": VersionAction,
        "VersionStatus": VersionStatus,
        "EscalateReason": EscalateReason,
    }
    assert set(ENUM_SNAPSHOT) == set(lookup)
    for name, values in ENUM_SNAPSHOT.items():
        enum_cls: type[Enum] = lookup[name]
        assert tuple(member.value for member in enum_cls) == values
        for member in enum_cls:
            assert enum_cls(member.value) is member


def test_constants() -> None:
    assert DIAGNOSIS_CONFIDENCE_THRESHOLD == 0.5
    assert REGRESSION_GATE_THRESHOLD == 0.8
    assert EVAL_MAX_CASES == 4
    assert REDTEAM_MAX_ATTACKS == 6
    assert SEEN_RING_MAX == 500
    assert WILSON_Z == 1.96
    assert AB_MIN_RUNS == 5
    assert AB_SIGNIFICANT_P == 0.05
    assert AB_MIN_DELTA_PP == 3.0
    assert NO_IMPROVE_LIMIT == 3


def test_work_item_from_span() -> None:
    span = _span()
    item = WorkItem.from_span(span)
    assert item.work_item_id == "work-span-1"
    assert item.span == span
    assert item.stage is Stage.WATCHED
    assert item.verdict is None


def test_should_stop() -> None:
    open_budget = PatchBudgetCounters(max_cycles=3, used_cycles=1)
    assert open_budget.should_stop() is False
    cycle_stop = PatchBudgetCounters(max_cycles=3, used_cycles=3)
    assert cycle_stop.should_stop() is True
    cost_stop = PatchBudgetCounters(max_cycles=9, used_cycles=1, max_cost_units=1.0, used_cost_units=1.0)
    assert cost_stop.should_stop() is True
    plateau = PatchBudgetCounters(max_cycles=9, used_cycles=1, no_improve=3)
    assert plateau.should_stop() is True
    not_yet = PatchBudgetCounters(max_cycles=9, used_cycles=1, no_improve=2)
    assert not_yet.should_stop() is False


def test_model_construction_roundtrip() -> None:
    span = _span()
    verdict = Verdict(
        failure_class=FailureClass.HALLUCINATION,
        confidence=0.9,
        rationale="invented a fact",
        expected_behavior="refuse",
    )
    root = RootCause(
        summary="empty tool",
        culprit="lookup",
        causal_chain=["tool empty", "model filled gap"],
        contributing_factors=["thin prompt"],
        fix_strategy="require evidence",
    )
    probe = ProbeSpec(input_text="probe", expected_answer="cite", acceptance_criterion="grounded")
    eval_result = EvalResult(eval_id="e1", baseline_pass_rate=0.25, candidate_pass_rate=0.75)
    replay = ReplayResult(
        original_input="what failed",
        before_output="a guess",
        after_output="I do not know",
        fixed=True,
        judge_rationale="now refuses",
    )
    redteam = RedTeamResult(attacks_run=2, before_pass=0, after_pass=2, examples=[])
    efficiency = EfficiencyReport(
        baseline_avg_tokens=100,
        candidate_avg_tokens=80,
        baseline_avg_latency_ms=50,
        candidate_avg_latency_ms=40,
    )
    item = WorkItem(
        work_item_id="work-span-1",
        span=span,
        verdict=verdict,
        severity=Severity.CRITICAL,
        root_cause=root,
        efficiency=efficiency,
        probes=[probe],
        eval_result=eval_result,
        baseline_prompt="be helpful",
        candidate_prompt="cite sources",
        candidate_prompt_version="1",
        prompt_diff="- be helpful\n+ cite sources",
        replay=replay,
        redteam=redteam,
        stage=Stage.RED_TEAMED,
    )
    event = TraceEventRow(work_item_id=item.work_item_id, stage=Stage.WATCHED, title="observed")
    budget = PatchBudgetCounters(max_cycles=4, used_cycles=1)
    playbook_entry = PlaybookEntry(id="p1", text="search before write", tags=["skill"], version="1")
    playbook = Playbook(version="1", entries=[playbook_entry], empty=False)
    index = PlaybookIndex(harnesses=[])
    journal_entry = JournalEntry(id="j1", kind=JournalKind.LESSON, text="cite first", session_id="s")
    journal = Journal(entries=[journal_entry])
    gate = GateDecision(passed=False, score=0.2, reason="miss")
    route = CostRouterDecision(choice=RouteChoice.CHEAP, reason="seen pattern")
    skill = SkillEntry(id="sk1", name="search-first", body="search before write", version="0")
    hit = SkillHit(skill=skill, score=1.0, action=SkillAction.HIT)
    query = SkillQuery(text="search")
    shadow = ShadowArm(name="shadow", policy_version="0")
    policy = PolicyDocument(version="0", allow=["lookup"], deny=[], shadow=shadow)
    dual = DualPass(live=PolicyArm.LIVE, policy=policy, shadow=shadow)
    dual_result = DualPassResult(
        live_allowed=True,
        shadow_allowed=True,
        divergence=False,
        tool="lookup",
        policy_version="0",
    )
    pointer = VersionPointer(active="0")
    record = VersionRecord(version="0")
    change = VersionChange(action=VersionAction.HOLD, pointer=pointer)
    sendoff = StructuredSendoff(brief="handoff", include=["verdict"], exclude=["draft"], payload={"verdict": "ok"})
    evolve_journal = EvolveRunJournal(rounds=1, stop_reason="max_rounds")

    models = [
        span,
        event,
        verdict,
        root,
        probe,
        eval_result,
        replay,
        redteam,
        efficiency,
        item,
        budget,
        playbook_entry,
        playbook,
        index,
        journal_entry,
        journal,
        gate,
        route,
        skill,
        hit,
        query,
        shadow,
        policy,
        dual,
        dual_result,
        pointer,
        record,
        change,
        sendoff,
        evolve_journal,
        HarnessRef(id="h1", path="playbooks/index.yaml"),
    ]
    for model in models:
        restored = model.__class__.model_validate(model.model_dump())
        assert restored == model
    assert verdict.is_failure is True
    assert eval_result.delta == 0.5
    assert efficiency.token_delta_pct == -0.2


def test_empty_harness_index() -> None:
    index = PlaybookIndex.model_validate({"harnesses": []})
    assert index.harnesses == []
