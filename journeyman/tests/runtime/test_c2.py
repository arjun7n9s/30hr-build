"""Evolve, stats, skills, policy, cost router, context gate."""

from pathlib import Path

from journeyman.contracts import (
    CHEAP_MODEL,
    ESCALATE_MODEL,
    EMBED_MODEL,
    EscalateReason,
    PatchBudgetCounters,
    RouteChoice,
    SkillEntry,
    SkillQuery,
)
from journeyman.evolve import BudgetedEvolver
from journeyman.policy import PolicyStream, ToolGateway
from journeyman.runtime import ContextGate
from journeyman.skills import SkillLibrary
from journeyman.spend import CostRouter
from journeyman.stats.ab import cohen_d, fill_eval_result, two_prop_z, welch_t, wilson_ci
from journeyman.contracts import EvalResult


def test_wilson_and_friends() -> None:
    lo, hi = wilson_ci(8, 10)
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0
    t = welch_t([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    assert t < 0
    z = two_prop_z(8, 10, 3, 10)
    assert z > 0
    d = cohen_d([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    assert d < 0
    result = EvalResult(eval_id="e", baseline_pass_rate=0.5, n=10, baseline_successes=5)
    fill_eval_result(result)
    assert result.wilson_low is not None


def test_evolver_promotes_best_only() -> None:
    budget = PatchBudgetCounters(max_cycles=6, max_cost_units=0)
    journal = BudgetedEvolver().run(budget, scores=[0.2, 0.4, 0.4, 0.4, 0.4])
    assert journal.promoted_version == "best-r2"
    assert journal.best_accuracy == 0.4
    assert journal.stop_reason == "no_improve"
    assert budget.no_improve >= 3


def test_evolver_stops_on_max_rounds() -> None:
    budget = PatchBudgetCounters(max_cycles=2)
    journal = BudgetedEvolver().run(budget, scores=[0.1, 0.2, 0.9])
    assert journal.rounds == 2
    assert journal.stop_reason == "max_rounds"
    assert journal.promoted_version == "best-r2"


def test_skill_library_find_exec_create(tmp_path: Path) -> None:
    lib = SkillLibrary(tmp_path / "library.json")
    created = lib.create_if_missing(
        SkillEntry(id="s1", name="repo.labels", body="list labels for {repo}", version="1")
    )
    hits = lib.find(SkillQuery(text="labels"))
    assert hits and hits[0].skill.name == "repo.labels"
    assert "fixture" in lib.exec("repo.labels", {"repo": "fixture"})
    again = lib.create_if_missing(created)
    assert again.name == created.name
    try:
        lib.create_if_missing(SkillEntry(id="bad", name="agent.secret", body="nope", version="1"))
        raise AssertionError("reserved namespace must fail")
    except ValueError:
        pass
    persisted = SkillLibrary(tmp_path / "library.json")
    assert persisted.find(SkillQuery(text="repo.labels"))


def test_policy_shadow_does_not_mutate_state() -> None:
    stream = PolicyStream()
    gateway = ToolGateway(stream)
    live = gateway.allow("list_issues", {})
    assert live.live_allowed is True
    before = stream.live_state.get("push_files", 0)
    denied = gateway.allow("push_files", {})
    assert denied.live_allowed is False
    shadow = stream.shadow_decide("push_files")
    assert shadow is not None
    assert stream.live_state.get("push_files", 0) == before + 1
    # second shadow call must not increment
    stream.shadow_decide("push_files")
    assert stream.live_state.get("push_files", 0) == before + 1


def test_cost_router_try_first_then_escalate(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("TMX_API_KEY=tmx_test\nOPENAI_API_KEY=sk-test\n", encoding="utf-8")
    router = CostRouter(env)
    first = router.try_first("summarize the issue")
    assert first.choice is RouteChoice.CHEAP
    assert first.model == CHEAP_MODEL
    miss = router.after_quality("")
    assert miss.choice is RouteChoice.ESCALATE
    assert miss.gate_miss is True
    assert miss.escalate_reason is EscalateReason.EMPTY_OUTPUT
    assert miss.model == ESCALATE_MODEL
    embed = router.embed_route()
    assert embed.model == EMBED_MODEL
    assert embed.reason == "embeddings are a separate path"


def test_context_gate_enter_exit() -> None:
    gate = ContextGate()
    sendoff = gate.enter(
        "reflect",
        {"draft": "old", "verdict": "fail", "brief": "original"},
        include=["verdict", "brief"],
        exclude=["draft"],
        brief="pass only verdict",
    )
    assert "draft" not in sendoff.payload
    assert sendoff.payload["verdict"] == "fail"
    hook = gate.exit(sendoff)
    assert hook.live_allowed is True
    assert hook.divergence is False
    decision = gate.check("quality", 0.9)
    assert decision.passed is True
