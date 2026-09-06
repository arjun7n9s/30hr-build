"""Evaluate learned rules against a feature record.

The engine is deliberately small and total: no eval, no code generation, no
network. A rule can only test strings and write strings, which is what makes a
mined rule safe to promote automatically.
"""

from __future__ import annotations

import re
from functools import lru_cache

from journeyman.contracts import (
    OutcomeMode,
    Predicate,
    PredicateOp,
    Rule,
    RuleHit,
    RuleKind,
)
from journeyman.rules.features import Features


def holds(predicate: Predicate, features: Features) -> bool:
    if predicate.all_of:
        return all(holds(child, features) for child in predicate.all_of)
    if predicate.any_of:
        return any(holds(child, features) for child in predicate.any_of)
    if predicate.none_of:
        return not any(holds(child, features) for child in predicate.none_of)
    values = features.get(predicate.field or "", [])
    if predicate.op is PredicateOp.EXISTS:
        return any(value.strip() for value in values)
    return any(_leaf(predicate, value) for value in values)


def apply_rules(
    rules: list[Rule],
    features: Features,
    *,
    kind: RuleKind | None = None,
) -> tuple[dict[str, list[str]], list[RuleHit]]:
    """Run every live rule and collect what fired.

    Returns the answer fragment plus the hits that produced it. The hits are the
    attribution record: they go onto the span so a later ablation pass can ask
    what a single rule was actually worth.
    """
    answer: dict[str, list[str]] = {}
    hits: list[RuleHit] = []
    live = [rule for rule in rules if rule.is_live()]
    if kind is not None:
        live = [rule for rule in live if rule.kind is kind]
    live.sort(key=lambda rule: rule.stats.confidence, reverse=True)
    decided: set[str] = set()
    for rule in live:
        if not holds(rule.when, features):
            continue
        target = rule.then.field
        if rule.then.mode is OutcomeMode.SET:
            if target in decided:
                continue
            answer[target] = list(rule.then.values)
            decided.add(target)
        else:
            bucket = answer.setdefault(target, [])
            for value in rule.then.values:
                if value not in bucket:
                    bucket.append(value)
        hits.append(RuleHit(rule_id=rule.id, field=target, values=list(rule.then.values)))
    for target, values in answer.items():
        if target not in decided:
            answer[target] = sorted(values)
    return answer, hits


def _leaf(predicate: Predicate, value: str) -> bool:
    hay = value.lower()
    for raw in predicate.values:
        needle = raw.lower()
        if predicate.op is PredicateOp.CONTAINS and needle in hay:
            return True
        if predicate.op is PredicateOp.EQUALS and needle == hay:
            return True
        if predicate.op is PredicateOp.PREFIX and hay.startswith(needle):
            return True
        if predicate.op is PredicateOp.IN_SET and hay == needle:
            return True
        if predicate.op is PredicateOp.MATCHES:
            pattern = _compile(raw)
            if pattern is not None and pattern.search(value):
                return True
    return False


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None
