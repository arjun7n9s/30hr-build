"""P1 mining: induce rules from labeled corpus issues, then prove it end to end.

The unit half builds its own soil with a made-up token, so it asserts the
*mechanism* (coverage / confidence / lift over labeled third-party objects) and
not the fixture's answer key. The integration half runs the offline demo and
checks the promoted version carries mined rules that came from data, that the
two DEV tasks no document explains now pass, and that the sealed hold-out never
reaches training.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from journeyman.contracts import (
    CORPUS_LABEL,
    MINE_MIN_COVERAGE,
    OutcomeMode,
    Playbook,
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
from journeyman.demo.run import _train_spans, run_demo
from journeyman.evalset.frozen import load_frozen_eval
from journeyman.ingest import TraceIngest
from journeyman.rules import apply_rules, issue_features
from journeyman.rules.mine import activate, mine

TOKEN = "wibble"
"""A word no document in the workspace mentions. Only the labels reveal it."""

MINED_LABELS = ("type:bug", "priority:p1")


def _issue(number: int, title: str, body: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": name} for name in labels],
        "state": "open",
    }


def _synthetic_corpus() -> list[dict]:
    """Six labeled `wibble` issues, unrelated labeled filler, and unlabeled noise."""
    issues = [
        _issue(
            100 + index,
            f"{TOKEN} appears in the nightly run {index}",
            f"Observed on attempt {index}. Nothing else to report.",
            [*MINED_LABELS, CORPUS_LABEL],
        )
        for index in range(6)
    ]
    issues += [
        _issue(
            200 + index,
            f"Spelling slip {index} in the handbook",
            f"Corrected wording {index} belongs in the handbook.",
            ["type:docs", CORPUS_LABEL],
        )
        for index in range(4)
    ]
    issues += [
        _issue(
            300 + index,
            f"Request for a density toggle {index}",
            f"Customers asked for toggle {index} on the panel.",
            ["type:feat", "area:ui", CORPUS_LABEL],
        )
        for index in range(4)
    ]
    # Not soil: the same token with contradicting labels, and an eval-shaped
    # target. Neither carries the corpus marker, so neither may be learned from.
    issues.append(_issue(400, f"{TOKEN} noted in an unlabeled tracker", "", ["type:docs"]))
    issues.append(_issue(401, f"{TOKEN} on the eval target", "", []))
    return issues


def _token_rules(rules: list[Rule], label: str | None = None) -> list[Rule]:
    hits = [
        rule
        for rule in rules
        if rule.when.op is PredicateOp.CONTAINS
        and rule.when.field == "title"
        and rule.when.values == [TOKEN]
    ]
    if label is not None:
        hits = [rule for rule in hits if label in rule.then.values]
    return hits


def _derived(label: str) -> Rule:
    when = Predicate(op=PredicateOp.CONTAINS, field="title", values=[TOKEN])
    then = RuleOutcome(field="labels", values=[label], mode=OutcomeMode.ADD)
    return Rule(
        id=f"derived-{label}",
        kind=RuleKind.LABEL,
        when=when,
        then=then,
        evidence=RuleEvidence(
            origin=RuleOrigin.DERIVED,
            source="CONTRIBUTING.md",
            refs=["CONTRIBUTING.md#L3"],
            note=f"{TOKEN} → {label}",
        ),
        stats=RuleStats(coverage=1, support=1).recompute(),
        status=RuleStatus.ACTIVE,
    )


def test_mine_induces_a_candidate_rule_no_document_states() -> None:
    rules = mine(_synthetic_corpus(), version="cand-1")
    assert rules, "six labeled examples of one token are enough to propose a rule"
    assert all(rule.kind is RuleKind.LABEL for rule in rules)
    assert all(rule.status is RuleStatus.CANDIDATE for rule in rules), "mined rules are proposals"
    assert all(rule.evidence.origin is RuleOrigin.MINED for rule in rules)
    assert all(rule.evidence.source == CORPUS_LABEL for rule in rules)
    assert all(rule.evidence.refs for rule in rules), "a rule with no refs cannot be promoted"
    assert all(rule.evidence.note for rule in rules)

    # One rule per label is fine; together they must reproduce the labeling.
    mined_labels: set[str] = set()
    for rule in _token_rules(rules):
        assert rule.then.field == "labels"
        assert rule.then.mode is OutcomeMode.ADD
        mined_labels.update(rule.then.values)
    assert mined_labels == set(MINED_LABELS)

    for label in MINED_LABELS:
        rule = _token_rules(rules, label)[0]
        assert rule.stats.coverage == 6, "only the six soil issues count"
        assert rule.stats.support == 6
        assert rule.stats.confidence == 1.0
        assert rule.stats.lift is not None and rule.stats.lift > 1.0, "must beat the base rate"
        assert all(ref.startswith("issue:") for ref in rule.evidence.refs)


def test_mined_rules_never_predict_the_soil_label() -> None:
    rules = mine(_synthetic_corpus(), version="cand-1")
    assert rules
    for rule in rules:
        assert CORPUS_LABEL not in rule.then.values, "the marker selects soil, it is not a target"


def test_only_labeled_soil_is_mined() -> None:
    corpus = _synthetic_corpus()
    assert mine([issue for issue in corpus if not issue["labels"]], version="cand-1") == []
    stripped = [
        {**issue, "labels": [row for row in issue["labels"] if row["name"] != CORPUS_LABEL]}
        for issue in corpus
    ]
    assert mine(stripped, version="cand-1") == [], "no marker, no mining"


def test_thin_evidence_is_not_promoted_to_a_rule() -> None:
    rules = mine(_synthetic_corpus(), version="cand-1", min_coverage=MINE_MIN_COVERAGE + 2)
    assert _token_rules(rules) == [], "six observations must not clear a coverage-7 bar"
    thin = mine(_synthetic_corpus()[:4], version="cand-1")
    assert thin == []


def test_activate_promotes_candidates_that_cleared_the_filters() -> None:
    candidates = mine(_synthetic_corpus(), version="cand-1")
    live = activate(candidates)
    assert [rule.id for rule in live] == [rule.id for rule in candidates], "activate is a status change"
    token_live = _token_rules(live)
    assert token_live and all(rule.status is RuleStatus.ACTIVE for rule in token_live)
    assert all(rule.is_live() for rule in token_live)
    assert all(rule.status is RuleStatus.CANDIDATE for rule in candidates), "originals are untouched"

    weak = candidates[0].model_copy(update={"stats": RuleStats(coverage=2, support=1).recompute()})
    assert activate([weak])[0].status is RuleStatus.CANDIDATE


def test_activated_rules_label_an_unseen_issue() -> None:
    live = activate(mine(_synthetic_corpus(), version="cand-1"))
    unseen = _issue(999, f"{TOKEN} on a brand new report", "", [])
    answer, hits = apply_rules(live, issue_features(unseen, task_type="label"), kind=RuleKind.LABEL)
    assert set(answer["labels"]) >= set(MINED_LABELS)
    assert hits, "the rules that produced the labels are recorded for attribution"


def test_a_mined_rule_that_fights_a_documented_one_is_dropped() -> None:
    corpus = _synthetic_corpus()
    derived = [_derived("priority:p0")]
    rules = mine(corpus, version="cand-1", derived=derived)
    assert _token_rules(rules, "priority:p1") == [], "documented priority wins over induced priority"
    assert _token_rules(rules, "type:bug"), "a non-conflicting label is still mined"


def test_the_miner_reads_issues_not_files() -> None:
    """Mining is induction from third-party objects, not a peek at the answer key."""
    source = (
        Path(__file__).resolve().parents[2] / "src" / "journeyman" / "rules" / "mine.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("read_text", "open(", "Path(", "requests", "urllib"):
        assert forbidden not in source, f"the miner must not use {forbidden}"


@pytest.fixture(scope="module")
def frozen_work_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("mine-demo")


@pytest.fixture(scope="module")
def frozen_report(frozen_work_root: Path):
    return run_demo("frozen", work_root=frozen_work_root, offline=True)


def _promoted_playbook(report, work_root: Path) -> Playbook:
    path = work_root / "playbooks" / f"{report.pointer.active}.json"
    assert path.exists(), "the promoted version is persisted"
    return Playbook.model_validate_json(path.read_text(encoding="utf-8"))


def test_promoted_version_carries_mined_rules(frozen_report, frozen_work_root: Path) -> None:
    assert frozen_report.promoted is True
    book = _promoted_playbook(frozen_report, frozen_work_root)
    mined = [rule for rule in book.rules if rule.evidence.origin is RuleOrigin.MINED]
    assert mined, "the promoted playbook must contain at least one mined rule"
    assert any(rule.is_live() for rule in mined), "a mined rule that never applies proves nothing"
    for rule in mined:
        assert rule.evidence.refs, "mined rules cite the issues they came from"
        assert rule.stats.coverage >= MINE_MIN_COVERAGE
    live = [rule for rule in mined if rule.is_live()]
    assert all(_predicate_values(rule.when) for rule in live), "the token came from the data"


def _predicate_values(predicate: Predicate) -> list[str]:
    values = list(predicate.values)
    for child in list(predicate.all_of) + list(predicate.any_of) + list(predicate.none_of):
        values.extend(_predicate_values(child))
    return values


def test_mining_makes_the_undocumented_dev_tasks_pass(frozen_report) -> None:
    challenge = load_frozen_eval()
    failed = {
        case.id
        for case, ok in zip(challenge.dev, frozen_report.run_n.passed, strict=True)
        if not ok
    }
    assert not {"dev-13", "dev-14"} & failed, "P1 mining is what makes these two pass"


def test_holdout_never_reaches_training(frozen_report) -> None:
    """hold-07 is the sealed proof of the same convention. Training must not see it."""
    challenge = load_frozen_eval()
    hold_ids = {case.id for case in challenge.held_out}
    assert "hold-07" in hold_ids

    dev_spans = _train_spans(frozen_report.run1, challenge.dev)
    trained_ids = {str(span.raw.get("case_id") or "") for span in dev_spans}
    assert not trained_ids & hold_ids, f"training saw hold-out cases: {trained_ids & hold_ids}"
    assert all(str(span.raw.get("split")) == "dev" for span in dev_spans)
    assert all(span.session_id.startswith("demo-run1") for span in dev_spans)

    for score in (frozen_report.hold_prior, frozen_report.hold_candidate):
        assert score is not None
        assert _train_spans(score, challenge.held_out) == [], "hold-out yields no train spans"
        ingest = TraceIngest()
        ingest.offer([span for turn in score.turns for span in turn.spans])
        assert ingest.poll() == [], "ingest skips every hold-out span"

    holdout_sessions = {sid for sid, split in frozen_report.score_log if split == "holdout"}
    assert holdout_sessions, "hold-out is scored once, at promote"
    assert all(sid.startswith("demo-hold") for sid in holdout_sessions)
    first_hold = next(i for i, (_, split) in enumerate(frozen_report.score_log) if split == "holdout")
    assert all(split == "dev" for _, split in frozen_report.score_log[:first_hold])


def test_the_hidden_convention_is_only_in_the_corpus(frozen_report, frozen_work_root: Path) -> None:
    """The marker may appear in mined rules (it came from issues), never in src."""
    root = Path(__file__).resolve().parents[2]
    hidden = (root.parent / "corpus" / "HIDDEN.md").read_text(encoding="utf-8")
    marker = re.search(r"^marker:\s*(\S+)", hidden, re.M)
    assert marker, "corpus/HIDDEN.md must declare marker: <token>"
    token = marker.group(1)
    offenders = [
        path.relative_to(root).as_posix()
        for path in (root / "src" / "journeyman").rglob("*.py")
        if "evalset" not in path.parts and re.search(re.escape(token), path.read_text(encoding="utf-8"), re.I)
    ]
    assert not offenders, f"hidden marker {token!r} baked into {offenders}"

    book = _promoted_playbook(frozen_report, frozen_work_root)
    mined_values = [
        value.lower()
        for rule in book.rules
        if rule.evidence.origin is RuleOrigin.MINED
        for value in _predicate_values(rule.when)
    ]
    assert any(token.lower() in value for value in mined_values), (
        "the agent learned the undocumented token from labeled issues"
    )


def test_manifest_marks_the_tasks_mining_must_unlock() -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[3] / "corpus" / "MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["expects_p1"] == ["dev-13", "dev-14", "hold-07"]
