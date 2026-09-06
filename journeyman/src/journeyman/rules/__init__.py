"""Rule engine: the executable form of what the agent has learned.

Layers, cheapest to strongest:

* `derive` — compile conventions the workspace already documents.
* `engine` — evaluate rules against a feature record.
* `features` — read third-party tool payloads into that feature record.

Mining and verification build on these without changing them.
"""

from journeyman.rules.derive import (
    Derivation,
    derive_codeowners,
    derive_contributing,
    derive_from_evidence,
    rule_id,
)
from journeyman.rules.engine import apply_rules, holds
from journeyman.rules.features import (
    Evidence,
    Features,
    collect_evidence,
    issue_features,
    merge_features,
    path_features,
)

__all__ = [
    "Derivation",
    "Evidence",
    "Features",
    "apply_rules",
    "collect_evidence",
    "derive_codeowners",
    "derive_contributing",
    "derive_from_evidence",
    "holds",
    "issue_features",
    "merge_features",
    "path_features",
    "rule_id",
]
