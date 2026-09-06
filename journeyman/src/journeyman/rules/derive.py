"""Compile a workspace's own documents into rules.

Derivation is the honest floor of learning: the agent reads files the third-party
app already contains and turns the conventions written there into executable
rules, citing the exact line. It knows *document* conventions (a CODEOWNERS
table, an `A → B` rule list) but never the contents — no label name, area, or
owner appears anywhere in this module.

Mining (inducing rules the docs never state, from how the workspace actually
behaves) is the next layer and lives beside this one.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

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
from journeyman.rules.features import Evidence

_ARROW = re.compile(r"\s*(?:→|->|=>)\s*")
_NAMESPACED = re.compile(r"`?([a-z][\w.-]*:[\w.*-]+)`?", re.I)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s*")
_LEAD_WORDS = re.compile(r"^(?:path|paths|when|if|for|a|an|the)\s+", re.I)
_HANDLE = re.compile(r"^[@$]|@")
_MAX_ALTERNATIVES = 8


@dataclass
class Derivation:
    """Rules the agent could compile, plus the lines it could not.

    `unlearned` is shown in the UI on purpose. An agent that quietly drops the
    conventions it failed to parse looks smarter than it is.
    """

    rules: list[Rule] = field(default_factory=list)
    unlearned: list[str] = field(default_factory=list)


def derive_from_evidence(evidence: Evidence, *, version: str) -> Derivation:
    """Derive everything available from this run's fetched files."""
    out = Derivation()
    owners = evidence.file("CODEOWNERS", ".github/CODEOWNERS")
    if owners:
        out.rules.extend(derive_codeowners(owners, version=version))
    contributing = evidence.file("CONTRIBUTING.md", "CONTRIBUTING")
    if contributing:
        derived = derive_contributing(contributing, version=version)
        out.rules.extend(derived.rules)
        out.unlearned.extend(derived.unlearned)
    return out


def derive_codeowners(text: str, *, version: str, source: str = "CODEOWNERS") -> list[Rule]:
    """`<path pattern> <owner...>` per line — GitHub's documented format.

    The logical owner is the first token that is not an @handle or an email; if
    every token is a handle, the pattern's last directory segment is used, which
    is the convention teams fall back on when handles are not meaningful names.
    """
    rules: list[Rule] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern, tokens = parts[0], parts[1:]
        prefix = _dir_prefix(pattern)
        if not prefix:
            continue
        owner = next((token for token in tokens if not _HANDLE.search(token)), "")
        if not owner:
            owner = prefix.rstrip("/").rsplit("/", 1)[-1]
        if not owner:
            continue
        rules.append(
            _rule(
                kind=RuleKind.OWNER,
                when=Predicate(op=PredicateOp.CONTAINS, field="path", values=[prefix]),
                then=RuleOutcome(field="owner", values=[owner], mode=OutcomeMode.SET),
                evidence=RuleEvidence(
                    origin=RuleOrigin.DERIVED,
                    source=source,
                    refs=[f"{source}#L{lineno}"],
                    note=line,
                ),
                version=version,
            )
        )
    return rules


def derive_contributing(
    text: str,
    *,
    version: str,
    source: str = "CONTRIBUTING.md",
) -> Derivation:
    """Compile `condition → outcome` convention lines into label rules.

    Two documented shapes are understood:

    * plain — `crash/nil/OOM → sev:high`. Slash- or pipe-separated conditions
      become alternatives; the namespaced tokens on the right become values.
    * templated — `path src/a|b|c → matching ns:*`. A wildcard on the right is
      filled per alternative from that alternative's last path segment, which is
      how teams write one line to mean N parallel rules.

    Anything else is returned as `unlearned` rather than guessed at.
    """
    out = Derivation()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _BULLET.sub("", raw).strip().rstrip(".")
        if not line or not _ARROW.search(line):
            continue
        parts = _ARROW.split(line, maxsplit=1)
        if len(parts) != 2:
            out.unlearned.append(line)
            continue
        left, right = parts[0].strip(), parts[1].strip()
        values = [match.group(1) for match in _NAMESPACED.finditer(right)]
        if not values or not left:
            out.unlearned.append(line)
            continue
        condition = _LEAD_WORDS.sub("", left.strip("`").strip())
        wildcard = next((value for value in values if value.endswith("*")), "")
        alternatives = _alternatives(condition, templated=bool(wildcard))
        if wildcard:
            fixed = [value for value in values if not value.endswith("*")]
            namespace = wildcard.rsplit(":", 1)[0]
            made = False
            for alternative in alternatives:
                leaf = alternative.rstrip("/").rsplit("/", 1)[-1]
                if not leaf:
                    continue
                made = True
                out.rules.append(
                    _rule(
                        kind=RuleKind.LABEL,
                        when=Predicate(
                            op=PredicateOp.CONTAINS, field="text", values=[alternative]
                        ),
                        then=RuleOutcome(
                            field="labels",
                            values=sorted({*fixed, f"{namespace}:{leaf}"}),
                            mode=OutcomeMode.ADD,
                        ),
                        evidence=RuleEvidence(
                            origin=RuleOrigin.DERIVED,
                            source=source,
                            refs=[f"{source}#L{lineno}"],
                            note=line,
                        ),
                        version=version,
                    )
                )
            if not made:
                out.unlearned.append(line)
            continue
        out.rules.append(
            _rule(
                kind=RuleKind.LABEL,
                when=_any_contains("text", alternatives),
                then=RuleOutcome(field="labels", values=sorted(set(values)), mode=OutcomeMode.ADD),
                evidence=RuleEvidence(
                    origin=RuleOrigin.DERIVED,
                    source=source,
                    refs=[f"{source}#L{lineno}"],
                    note=line,
                ),
                version=version,
            )
        )
    return out


def rule_id(kind: RuleKind, when: Predicate, then: RuleOutcome) -> str:
    """Stable id so re-deriving the same convention merges instead of duplicating."""
    blob = "|".join(
        [
            kind.value,
            when.model_dump_json(exclude_defaults=True),
            then.model_dump_json(exclude_defaults=True),
        ]
    )
    return f"{kind.value}-{hashlib.sha1(blob.encode('utf-8')).hexdigest()[:10]}"


def _rule(
    *,
    kind: RuleKind,
    when: Predicate,
    then: RuleOutcome,
    evidence: RuleEvidence,
    version: str,
) -> Rule:
    return Rule(
        id=rule_id(kind, when, then),
        kind=kind,
        when=when,
        then=then,
        evidence=evidence,
        # A documented convention is the workspace stating its own rule, so it
        # starts active with support 1 — the line itself. Mined rules must earn
        # their status from observations instead.
        stats=RuleStats(coverage=1, support=1, confidence=1.0).recompute(),
        status=RuleStatus.ACTIVE,
        version=version,
    )


def _any_contains(field_name: str, values: list[str]) -> Predicate:
    if len(values) == 1:
        return Predicate(op=PredicateOp.CONTAINS, field=field_name, values=values)
    return Predicate(
        any_of=[
            Predicate(op=PredicateOp.CONTAINS, field=field_name, values=[value])
            for value in values
        ]
    )


def _alternatives(condition: str, *, templated: bool) -> list[str]:
    """Split a condition into parallel alternatives.

    Pipes always alternate. Slashes only alternate when no piece looks like a
    filename, so `docs/typo/README` becomes three conditions while
    `src/payments/charge.py` stays one path.
    """
    token = max(condition.split(), key=len, default="") if "|" in condition else ""
    if token and "|" in token:
        head, _, tail = token.partition("|")
        prefix = head.rsplit("/", 1)[0] + "/" if "/" in head else ""
        pieces = [head] + [
            piece if "/" in piece else f"{prefix}{piece}" for piece in tail.split("|") if piece
        ]
        return _clean(pieces)
    if templated:
        return _clean([condition])
    pieces = condition.split("/")
    if 1 < len(pieces) <= _MAX_ALTERNATIVES and all(
        piece and "." not in piece and " " not in piece.strip() for piece in pieces
    ):
        return _clean(pieces)
    return _clean([condition])


def _clean(pieces: list[str]) -> list[str]:
    out: list[str] = []
    for piece in pieces:
        value = piece.strip().strip("`").strip()
        if value and value not in out:
            out.append(value)
    return out[:_MAX_ALTERNATIVES]


def _dir_prefix(pattern: str) -> str:
    value = pattern.strip().lstrip("/").replace("\\", "/")
    if not value or value in {"*", "**"}:
        return ""
    if "." in value.rsplit("/", 1)[-1]:
        return value
    return value if value.endswith("/") else f"{value}/"
