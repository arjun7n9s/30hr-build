"""Learned rules: the unit of memory the agent grows, verifies, and retires.

A Rule is the executable form of one thing the agent learned about a third-party
workspace. It is app-agnostic on purpose: `when` tests a feature record extracted
from tool evidence, `then` writes values onto one answer field. Nothing in this
module knows about GitHub, labels, or any particular repo.

Three properties make a rule promotable instead of merely plausible:

* `evidence` — where it came from, with refs a human can open.
* `stats` — how much observed data supports it, and how much contradicts it.
* `status` — candidate / shadow / active / retired, so promotion is a state
  change on an individual belief rather than on a whole playbook version.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from journeyman.contracts.enums import (
    OutcomeMode,
    PredicateOp,
    RuleKind,
    RuleOrigin,
    RuleStatus,
)


class Predicate(BaseModel):
    """A boolean test over a feature record.

    Exactly one shape per node:

    * leaf — `op` + `field` (+ `values` for every op except `exists`)
    * `all_of` — every child must hold
    * `any_of` — at least one child must hold
    * `none_of` — no child may hold

    A leaf holds when *any* value under `field` satisfies `op`. Feature values are
    always lists of strings, so `contains` on a multi-valued field means "any of
    them contains this".
    """

    model_config = ConfigDict(extra="forbid")

    op: PredicateOp | None = None
    field: str | None = None
    values: list[str] = Field(default_factory=list)
    all_of: list[Predicate] = Field(default_factory=list)
    any_of: list[Predicate] = Field(default_factory=list)
    none_of: list[Predicate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> Predicate:
        shapes = [
            bool(self.op is not None or self.field is not None),
            bool(self.all_of),
            bool(self.any_of),
            bool(self.none_of),
        ]
        if sum(shapes) != 1:
            raise ValueError("predicate must be exactly one of: leaf, all_of, any_of, none_of")
        if shapes[0]:
            if self.op is None or not self.field:
                raise ValueError("leaf predicate needs both op and field")
            if self.op is not PredicateOp.EXISTS and not self.values:
                raise ValueError(f"op {self.op.value} needs at least one value")
            for value in self.values:
                if len(value) > MAX_PATTERN_LEN:
                    raise ValueError(f"predicate value exceeds {MAX_PATTERN_LEN} chars")
        return self

    def describe(self) -> str:
        """Human-readable form. This is what the Playbook tab renders."""
        if self.all_of:
            return "(" + " AND ".join(child.describe() for child in self.all_of) + ")"
        if self.any_of:
            return "(" + " OR ".join(child.describe() for child in self.any_of) + ")"
        if self.none_of:
            return "NOT (" + " OR ".join(child.describe() for child in self.none_of) + ")"
        if self.op is PredicateOp.EXISTS:
            return f"{self.field} exists"
        return f"{self.field} {self.op.value if self.op else '?'} {self.values!r}"


MAX_PATTERN_LEN = 200
"""Cap on a single predicate value. Keeps mined regexes inspectable and bounded."""

Predicate.model_rebuild()


class RuleOutcome(BaseModel):
    """What the rule asserts when its predicate holds.

    `field` is an answer field (`labels`, `owner`, ...), not a feature field.
    `ADD` unions values into the answer; `SET` wins outright, highest-confidence
    rule first.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    values: list[str] = Field(default_factory=list)
    mode: OutcomeMode = OutcomeMode.ADD

    def describe(self) -> str:
        verb = "set" if self.mode is OutcomeMode.SET else "add"
        return f"{verb} {self.field}={', '.join(self.values)}"


class RuleEvidence(BaseModel):
    """Provenance. A rule with no refs cannot be promoted."""

    model_config = ConfigDict(extra="forbid")

    origin: RuleOrigin
    source: str
    """Where it came from: a file path, a corpus name, or a proposing model."""

    refs: list[str] = Field(default_factory=list)
    """Opaque handles the UI can resolve, e.g. `issue:42`, `CONTRIBUTING.md#L12`."""

    note: str = ""
    """The raw line or observation that produced the rule, kept verbatim."""


class RuleStats(BaseModel):
    """Observed support. Filled by the miner, refreshed on every verification pass.

    `coverage` counts observations where the predicate held. `support` counts the
    subset where the outcome also held; `counterexamples` is the remainder. So
    `confidence == support / coverage`, and a rule that fires often but is right
    rarely is visibly distinct from one that never fires at all.
    """

    model_config = ConfigDict(extra="forbid")

    coverage: int = 0
    support: int = 0
    counterexamples: int = 0
    confidence: float = 0.0
    lift: float | None = None
    """confidence / base rate of the outcome. >1 means the rule beats guessing."""

    fired: int = 0
    """Runtime firings since the rule went active. Retirement input."""

    accuracy_delta: float | None = None
    """Measured leave-one-out contribution. Filled by the ablation pass."""

    cost_delta: float | None = None

    def recompute(self) -> RuleStats:
        self.counterexamples = max(self.coverage - self.support, 0)
        self.confidence = round(self.support / self.coverage, 4) if self.coverage else 0.0
        return self


class Rule(BaseModel):
    """One learned belief, versioned with the playbook that introduced it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: RuleKind
    when: Predicate
    then: RuleOutcome
    evidence: RuleEvidence
    stats: RuleStats = Field(default_factory=RuleStats)
    status: RuleStatus = RuleStatus.CANDIDATE
    version: str = "0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def describe(self) -> str:
        return f"WHEN {self.when.describe()} THEN {self.then.describe()}"

    def is_live(self) -> bool:
        """Active rules affect answers. Shadow rules are scored but not applied."""
        return self.status is RuleStatus.ACTIVE


class RuleHit(BaseModel):
    """A rule that fired on one task. Recorded on the span for attribution."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    field: str
    values: list[str] = Field(default_factory=list)


class RuleSet(BaseModel):
    """Rules carried by one playbook version."""

    model_config = ConfigDict(extra="forbid")

    version: str = "0"
    rules: list[Rule] = Field(default_factory=list)

    def live(self, kind: RuleKind | None = None) -> list[Rule]:
        rules = [rule for rule in self.rules if rule.is_live()]
        if kind is not None:
            rules = [rule for rule in rules if rule.kind is kind]
        return sorted(rules, key=lambda rule: rule.stats.confidence, reverse=True)

    def by_id(self, rule_id: str) -> Rule | None:
        return next((rule for rule in self.rules if rule.id == rule_id), None)
