"""Rule schema, engine, derivation, and the guard that keeps taxonomy out of code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from journeyman.contracts import (
    OutcomeMode,
    Predicate,
    PredicateOp,
    Rule,
    RuleEvidence,
    RuleKind,
    RuleOrigin,
    RuleOutcome,
    RuleStats,
    RuleStatus,
)
from journeyman.evalset.frozen import CODEOWNERS, CONTRIBUTING
from journeyman.rules import (
    apply_rules,
    collect_evidence,
    derive_codeowners,
    derive_contributing,
    holds,
    issue_features,
    path_features,
)
from journeyman.runtime import triage


def _rule(
    when: Predicate,
    then: RuleOutcome,
    *,
    kind: RuleKind = RuleKind.LABEL,
    status: RuleStatus = RuleStatus.ACTIVE,
    confidence: float = 1.0,
) -> Rule:
    return Rule(
        id=f"r-{abs(hash((when.describe(), then.describe(), confidence)))%10**8}",
        kind=kind,
        when=when,
        then=then,
        evidence=RuleEvidence(origin=RuleOrigin.MINED, source="test", refs=["issue:1"]),
        stats=RuleStats(coverage=10, support=int(10 * confidence)).recompute(),
        status=status,
    )


def test_predicate_requires_exactly_one_shape() -> None:
    with pytest.raises(ValidationError):
        Predicate()
    with pytest.raises(ValidationError):
        Predicate(
            op=PredicateOp.CONTAINS,
            field="text",
            values=["x"],
            any_of=[Predicate(op=PredicateOp.CONTAINS, field="text", values=["y"])],
        )
    with pytest.raises(ValidationError):
        Predicate(op=PredicateOp.CONTAINS, field="text")  # no values
    with pytest.raises(ValidationError):
        Predicate(op=PredicateOp.CONTAINS, field="text", values=["x" * 500])
    assert Predicate(op=PredicateOp.EXISTS, field="body").describe() == "body exists"


def test_predicate_combinators() -> None:
    features = {"text": ["Stack trace in src/api/routes.py"], "labels": []}
    contains = Predicate(op=PredicateOp.CONTAINS, field="text", values=["stack trace"])
    missing = Predicate(op=PredicateOp.CONTAINS, field="text", values=["nil"])
    assert holds(contains, features)
    assert not holds(missing, features)
    assert holds(Predicate(any_of=[missing, contains]), features)
    assert not holds(Predicate(all_of=[missing, contains]), features)
    assert holds(Predicate(none_of=[missing]), features)
    assert not holds(Predicate(none_of=[contains]), features)
    assert not holds(Predicate(op=PredicateOp.EXISTS, field="labels"), features)


def test_add_unions_and_set_takes_highest_confidence() -> None:
    features = {"text": ["billing retry crash"], "path": ["src/billing/charge.py"]}
    rules = [
        _rule(
            Predicate(op=PredicateOp.CONTAINS, field="text", values=["billing"]),
            RuleOutcome(field="labels", values=["area:billing"]),
        ),
        _rule(
            Predicate(op=PredicateOp.CONTAINS, field="text", values=["crash"]),
            RuleOutcome(field="labels", values=["priority:p0", "area:billing"]),
        ),
        _rule(
            Predicate(op=PredicateOp.CONTAINS, field="path", values=["src/billing/"]),
            RuleOutcome(field="owner", values=["billing"], mode=OutcomeMode.SET),
            kind=RuleKind.OWNER,
            confidence=0.9,
        ),
        _rule(
            Predicate(op=PredicateOp.CONTAINS, field="path", values=["src/"]),
            RuleOutcome(field="owner", values=["platform"], mode=OutcomeMode.SET),
            kind=RuleKind.OWNER,
            confidence=0.4,
        ),
    ]
    answer, hits = apply_rules(rules, features)
    assert answer["labels"] == ["area:billing", "priority:p0"]
    assert answer["owner"] == ["billing"], "SET resolves to the most confident rule"
    applied = {hit.rule_id for hit in hits}
    assert applied == {rules[0].id, rules[1].id, rules[2].id}
    assert rules[3].id not in applied, "a SET that lost to a higher-confidence rule did not apply"


def test_only_active_rules_change_answers() -> None:
    features = {"text": ["stack trace"]}
    for status in (RuleStatus.CANDIDATE, RuleStatus.SHADOW, RuleStatus.RETIRED):
        rules = [
            _rule(
                Predicate(op=PredicateOp.CONTAINS, field="text", values=["stack trace"]),
                RuleOutcome(field="labels", values=["type:bug"]),
                status=status,
            )
        ]
        answer, hits = apply_rules(rules, features)
        assert answer == {} and hits == [], f"{status.value} rules must not apply"


def test_derives_contributing_including_the_wildcard_template() -> None:
    derived = derive_contributing(CONTRIBUTING, version="v1")
    described = {rule.describe() for rule in derived.rules}
    assert "WHEN text contains ['stack trace'] THEN add labels=type:bug" in described
    # One templated line becomes one rule per alternative.
    areas = {
        rule.then.values[0]
        for rule in derived.rules
        if rule.then.values and rule.then.values[0].startswith("area:")
    }
    assert areas == {"area:api", "area:billing", "area:runtime", "area:ui"}
    assert all(rule.evidence.refs for rule in derived.rules)
    assert all(rule.evidence.origin is RuleOrigin.DERIVED for rule in derived.rules)
    assert all(rule.evidence.note for rule in derived.rules), "keep the source line verbatim"


def test_unparseable_conventions_are_reported_not_guessed() -> None:
    derived = derive_contributing("- be nice → please\n- stack trace → `type:bug`\n", version="v1")
    assert len(derived.rules) == 1
    assert derived.unlearned == ["be nice → please"]


def test_derives_codeowners_logical_owner() -> None:
    rules = derive_codeowners(CODEOWNERS, version="v1")
    mapping = {rule.when.values[0]: rule.then.values[0] for rule in rules}
    assert mapping == {
        "src/api/": "api",
        "src/billing/": "billing",
        "src/runtime/": "runtime",
        "src/ui/": "ui",
    }
    assert all(rule.then.mode is OutcomeMode.SET for rule in rules)
    # Handles are not logical owners; fall back to the directory name.
    handles = derive_codeowners("/src/payments/ @octocat @hubber\n", version="v1")
    assert handles[0].then.values == ["payments"]


def test_rule_ids_are_stable_across_derivations() -> None:
    first = derive_contributing(CONTRIBUTING, version="v1").rules
    second = derive_contributing(CONTRIBUTING, version="v2").rules
    assert [rule.id for rule in first] == [rule.id for rule in second]


def test_empty_rule_set_answers_nothing_rather_than_guessing() -> None:
    """The honest v0 baseline: evidence in hand, no learned rule, no label."""
    tool_calls = [
        {
            "name": "issue_read",
            "result": {
                "found": True,
                "number": 1,
                "title": "API returns 500 on empty payload",
                "body": 'Stack trace:\n  File "src/api/routes.py", line 42',
                "labels": [],
            },
        }
    ]
    answer, hits = triage.answer_task("label", "what labels?", {"issue_number": 1}, tool_calls, rules=[])
    assert "labels" not in answer
    assert hits == []
    derived = derive_contributing(CONTRIBUTING, version="v1").rules
    answer, hits = triage.answer_task(
        "label", "what labels?", {"issue_number": 1}, tool_calls, rules=derived
    )
    assert answer["labels"] == ["area:api", "type:bug"]
    assert hits, "the rules that produced the answer are recorded for attribution"


def test_collect_evidence_reads_structured_results_not_stringified_payloads() -> None:
    evidence = collect_evidence(
        [
            {"name": "list_issues", "result": {"found": True, "items": [{"number": 3, "title": "a"}]}},
            {"name": "issue_read", "result": {"found": True, "number": 4, "title": "b"}},
            {"name": "get_file_contents", "result": {"found": True, "path": "CODEOWNERS", "content": "x"}},
            {"name": "list_label", "result": {"found": True, "items": [{"name": "type:bug"}]}},
            {"name": "push_files", "denied": True, "result": {"found": False, "denied": True}},
        ]
    )
    assert {issue["number"] for issue in evidence.issues} == {3, 4}
    assert evidence.file("CODEOWNERS") == "x"
    assert evidence.labels == ["type:bug"]


def test_issue_and_path_features() -> None:
    features = issue_features(
        {"number": 7, "title": "t", "body": "see src/billing/charge.py", "labels": [{"name": "type:bug"}]},
        task_type="label",
    )
    assert features["path"] == ["src/billing/charge.py"]
    assert features["labels"] == ["type:bug"]
    assert features["task_type"] == ["label"]
    assert path_features("/src/ui/app.tsx")["path"] == ["src/ui/app.tsx"]


# The taxonomy of the workspace under test must live in rules with evidence,
# never in the agent's source. This guard is the whole point of P0: if it fails,
# someone has re-encoded the answer key and the learning claim is void again.
_FORBIDDEN = re.compile(
    r"""(?x)
    type:(bug|feat|docs)
    | area:(api|billing|runtime|ui)\b
    | priority:p[01]
    | src/(api|billing|runtime|ui)
    """
)
_RUNTIME_SOURCES = (
    "runtime/triage.py",
    "runtime/actor.py",
    "runtime/__init__.py",
    "reflect/__init__.py",
    "rules/engine.py",
    "rules/derive.py",
    "rules/features.py",
    "diagnose/__init__.py",
)


def test_no_workspace_taxonomy_is_hardcoded_in_the_agent() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "journeyman"
    offenders: list[str] = []
    for relative in _RUNTIME_SOURCES:
        path = root / relative
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if _FORBIDDEN.search(code):
                offenders.append(f"{relative}:{lineno}: {line.strip()}")
    assert not offenders, "workspace taxonomy belongs in derived/mined rules:\n" + "\n".join(offenders)
