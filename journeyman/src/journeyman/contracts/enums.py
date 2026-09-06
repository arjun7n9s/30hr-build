"""Shared enumerations for Journeyman contracts."""

from enum import Enum


class FailureClass(str, Enum):
    HALLUCINATION = "hallucination"
    PROMPT_DRIFT = "prompt_drift"
    TOOL_FAILURE = "tool_failure"
    OK = "ok"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Stage(str, Enum):
    WATCHED = "watched"
    DIAGNOSED = "diagnosed"
    ROOT_CAUSED = "root_caused"
    SYNTHESIZED = "synthesized"
    EVALUATED = "evaluated"
    PATCHED = "patched"
    REPLAYED = "replayed"
    RED_TEAMED = "red_teamed"


class SpanKind(str, Enum):
    LLM = "LLM"
    TOOL = "TOOL"
    AGENT = "AGENT"


class Split(str, Enum):
    DEV = "dev"
    HOLDOUT = "holdout"


class RouteChoice(str, Enum):
    CHEAP = "cheap"
    ESCALATE = "escalate"


class JournalKind(str, Enum):
    LESSON = "lesson"
    INSIGHT = "insight"
    WARNING = "warning"


class SkillAction(str, Enum):
    SEARCH = "search"
    WRITE = "write"
    HIT = "hit"


class PolicyArm(str, Enum):
    LIVE = "live"
    SHADOW = "shadow"


class VersionAction(str, Enum):
    PROMOTE = "promote"
    ROLLBACK = "rollback"
    HOLD = "hold"


class VersionStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    ARCHIVED = "archived"


class EscalateReason(str, Enum):
    QUALITY_GATE = "quality_gate"
    EMPTY_OUTPUT = "empty_output"
    UNAVAILABLE = "unavailable"


ENUM_SNAPSHOT: dict[str, tuple[str, ...]] = {
    "FailureClass": ("hallucination", "prompt_drift", "tool_failure", "ok"),
    "Severity": ("critical", "high", "medium", "low"),
    "Stage": (
        "watched",
        "diagnosed",
        "root_caused",
        "synthesized",
        "evaluated",
        "patched",
        "replayed",
        "red_teamed",
    ),
    "SpanKind": ("LLM", "TOOL", "AGENT"),
    "Split": ("dev", "holdout"),
    "RouteChoice": ("cheap", "escalate"),
    "JournalKind": ("lesson", "insight", "warning"),
    "SkillAction": ("search", "write", "hit"),
    "PolicyArm": ("live", "shadow"),
    "VersionAction": ("promote", "rollback", "hold"),
    "VersionStatus": ("candidate", "active", "archived"),
    "EscalateReason": ("quality_gate", "empty_output", "unavailable"),
}
