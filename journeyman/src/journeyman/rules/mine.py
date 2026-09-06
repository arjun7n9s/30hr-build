"""Induce rules from labeled corpus issues. No documented convention names live here.

The miner sees third-party objects (issues with a soil label, plus derived rules
to avoid contradicting the workspace's own docs). It never opens HIDDEN.md.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from journeyman.contracts import (
    CORPUS_LABEL,
    MINE_MIN_CONFIDENCE,
    MINE_MIN_COVERAGE,
    MINE_MIN_LIFT,
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
from journeyman.rules.derive import rule_id
from journeyman.rules.engine import holds
from journeyman.rules.features import Features, issue_features

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "for", "from", "with", "this", "that",
        "when", "after", "into", "over", "under", "near", "onto", "have", "has",
        "had", "been", "will", "your", "their", "about", "there", "which",
        "while", "where", "issue", "issues", "title", "body", "are", "was",
        "were", "but", "not", "all", "any", "can", "does", "did", "its",
        "on", "in", "to", "of", "at", "by", "is", "it", "as", "be",
    }
)
_SOIL_LABELS = frozenset({CORPUS_LABEL})


def mine(
    issues: Iterable[dict[str, Any]],
    *,
    version: str,
    derived: list[Rule] | None = None,
    min_coverage: int = MINE_MIN_COVERAGE,
    min_confidence: float = MINE_MIN_CONFIDENCE,
    min_lift: float = MINE_MIN_LIFT,
) -> list[Rule]:
    """Propose label rules from title/body tokens vs labels on corpus:mine issues."""
    rows = [_row(issue) for issue in issues if _is_corpus(issue)]
    if not rows:
        return []
    n = len(rows)
    label_base = Counter(label for row in rows for label in row["labels"])
    candidates: list[Rule] = []
    seen: set[str] = set()
    for field in ("title", "body"):
        postings: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            for token in row["tokens"][field]:
                postings[token].append(index)
        for token, indexes in postings.items():
            coverage = len(indexes)
            if coverage < min_coverage:
                continue
            support_by_label: Counter[str] = Counter()
            for index in indexes:
                support_by_label.update(rows[index]["labels"])
            for label, support in support_by_label.items():
                confidence = support / coverage
                base = label_base[label] / n
                lift = (confidence / base) if base else 0.0
                if confidence < min_confidence or lift <= min_lift:
                    continue
                refs = [f"issue:{rows[index]['number']}" for index in indexes[:8] if rows[index]["number"]]
                when = Predicate(op=PredicateOp.CONTAINS, field=field, values=[token])
                then = RuleOutcome(field="labels", values=[label], mode=OutcomeMode.ADD)
                ident = rule_id(RuleKind.LABEL, when, then)
                if ident in seen:
                    continue
                seen.add(ident)
                stats = RuleStats(
                    coverage=coverage,
                    support=support,
                    lift=round(lift, 4),
                ).recompute()
                candidates.append(
                    Rule(
                        id=ident,
                        kind=RuleKind.LABEL,
                        when=when,
                        then=then,
                        evidence=RuleEvidence(
                            origin=RuleOrigin.MINED,
                            source="corpus:mine",
                            refs=refs,
                            note=f"{field} contains {token!r} → {label} "
                            f"(coverage={coverage} support={support} lift={lift:.2f})",
                        ),
                        stats=stats,
                        status=RuleStatus.CANDIDATE,
                        version=version,
                    )
                )
    kept = [rule for rule in candidates if not _contradicts(rule, derived or [], rows)]
    kept.sort(key=lambda rule: (rule.stats.lift or 0, rule.stats.confidence), reverse=True)
    return kept


def activate(rules: list[Rule]) -> list[Rule]:
    """CANDIDATE → ACTIVE when stats already cleared the mine filters."""
    live: list[Rule] = []
    for rule in rules:
        if (
            rule.stats.coverage >= MINE_MIN_COVERAGE
            and rule.stats.confidence >= MINE_MIN_CONFIDENCE
            and (rule.stats.lift or 0) > MINE_MIN_LIFT
        ):
            live.append(rule.model_copy(update={"status": RuleStatus.ACTIVE}))
        else:
            live.append(rule)
    return live


def _is_corpus(issue: dict[str, Any]) -> bool:
    return CORPUS_LABEL in _label_names(issue)


def _labels(issue: dict[str, Any]) -> list[str]:
    """Labels the miner may predict: the soil marker is a selector, not a target."""
    return [name for name in _label_names(issue) if name not in _SOIL_LABELS]


def _label_names(issue: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for raw in issue.get("labels") or []:
        name = str(raw.get("name") if isinstance(raw, dict) else raw)
        if name:
            out.append(name)
    return out


def _row(issue: dict[str, Any]) -> dict[str, Any]:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    return {
        "number": issue.get("number") or issue.get("key") or "",
        "title": title,
        "labels": _labels(issue),
        "features": issue_features(issue, task_type="label"),
        "tokens": {"title": _tokens(title), "body": _tokens(body)},
    }


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if len(token) > 3 and token not in _STOP}


def _contradicts(rule: Rule, derived: list[Rule], rows: list[dict[str, Any]]) -> bool:
    """Drop a mined rule that fights a derived rule on the same observations."""
    if not derived:
        return False
    derived_live = [other for other in derived if other.is_live() and other.kind is rule.kind]
    if not derived_live:
        return False
    for row in rows:
        features: Features = row["features"]
        if not holds(rule.when, features):
            continue
        for other in derived_live:
            if not holds(other.when, features):
                continue
            if other.then.mode is OutcomeMode.SET and rule.then.mode is OutcomeMode.SET:
                if other.then.field == rule.then.field and other.then.values != rule.then.values:
                    return True
            if other.then.field == rule.then.field and _exclusive_conflict(other.then.values, rule.then.values):
                return True
    return False


def _exclusive_conflict(left: list[str], right: list[str]) -> bool:
    """Same namespace, different value (priority:p0 vs priority:p1)."""
    for a in left:
        ns, _, _rest = a.partition(":")
        if not _rest:
            continue
        for b in right:
            other_ns, _, other = b.partition(":")
            if ns == other_ns and a != b and other:
                return True
    return False
