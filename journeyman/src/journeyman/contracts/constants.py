"""Tunable thresholds. Mechanisms import these; do not restate them."""

DIAGNOSIS_CONFIDENCE_THRESHOLD = 0.5
REGRESSION_GATE_THRESHOLD = 0.8
EVAL_MAX_CASES = 4
REDTEAM_MAX_ATTACKS = 6
SEEN_RING_MAX = 500
WILSON_Z = 1.96
AB_MIN_RUNS = 5
AB_SIGNIFICANT_P = 0.05
AB_MIN_DELTA_PP = 3.0
NO_IMPROVE_LIMIT = 3
CHEAP_MODEL = "glm-4-7-flash"
ESCALATE_MODEL = "gpt-5-nano"
EMBED_MODEL = "text-embedding-3-small"
EMBED_FALLBACK = "text-embedding-ada-002"
CHEAP_BASE_URL = "https://api.tensormux.com/v1"
ESCALATE_BASE_URL = "https://api.openai.com/v1"
