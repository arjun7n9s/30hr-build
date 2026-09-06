"""Policy stream (active + shadow) and GitHub-readonly tool gateway."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from journeyman.contracts import DualPass, DualPassResult, GateDecision, PolicyArm, PolicyDocument, ShadowArm

_GITHUB_READONLY = PolicyDocument(
    version="1",
    allow=[
        "get_file_contents",
        "get_repository",
        "list_issues",
        "get_issue",
        "search_issues",
        "list_pull_requests",
        "get_pull_request",
        "search_pull_requests",
        "search_code",
        "list_labels",
        "get_label",
        "list_commits",
        "get_commit",
        "list_branches",
    ],
    deny=[
        "create_issue",
        "create_pull_request",
        "push_files",
        "create_or_update_file",
        "delete_file",
        "merge_pull_request",
        "update_issue",
        "add_issue_comment",
        "create_repository",
        "delete_repository",
        "run_workflow",
        "get_secret",
        "list_secrets",
        "create_or_update_secret",
    ],
    shadow=ShadowArm(name="shadow", policy_version="1-shadow", enabled=True),
)


class PolicyStream:
    def __init__(self, path: Path | None = None, document: PolicyDocument | None = None) -> None:
        self.path = path
        self._live_state: dict[str, int] = {}
        self._document = document or _load_document(path) or _GITHUB_READONLY

    def current(self) -> DualPass:
        return DualPass(
            live=PolicyArm.LIVE,
            policy=self._document,
            shadow=self._document.shadow,
        )

    def decide(self, tool: str, args: dict[str, Any] | None = None) -> GateDecision:
        allowed = _allowed(self._document, tool)
        self._live_state[tool] = self._live_state.get(tool, 0) + 1
        return GateDecision(passed=allowed, score=1.0 if allowed else 0.0, reason=tool)

    def shadow_decide(self, tool: str, args: dict[str, Any] | None = None) -> GateDecision | None:
        shadow = self._document.shadow
        if shadow is None or not shadow.enabled:
            return None
        allowed = _allowed(self._document, tool)
        # Shadow must not apply state_changes.
        return GateDecision(passed=allowed, score=1.0 if allowed else 0.0, reason=f"shadow:{tool}")

    @property
    def live_state(self) -> dict[str, int]:
        return dict(self._live_state)


class ToolGateway:
    def __init__(self, stream: PolicyStream | None = None) -> None:
        self.stream = stream or PolicyStream()

    def allow(self, tool: str, args: dict[str, Any], stream: PolicyStream | None = None) -> DualPassResult:
        active = stream or self.stream
        live = active.decide(tool, args)
        shadow = active.shadow_decide(tool, args)
        shadow_allowed = None if shadow is None else shadow.passed
        return DualPassResult(
            live_allowed=live.passed,
            shadow_allowed=shadow_allowed,
            divergence=shadow_allowed is not None and shadow_allowed != live.passed,
            tool=tool,
            policy_version=active.current().policy.version,
        )


def _allowed(policy: PolicyDocument, tool: str) -> bool:
    if any(fnmatch.fnmatch(tool, pattern) for pattern in policy.deny):
        return False
    if not policy.allow:
        return True
    return any(fnmatch.fnmatch(tool, pattern) for pattern in policy.allow)


def _load_document(path: Path | None) -> PolicyDocument | None:
    if path is None or not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    data = _parse_simple_yaml(text)
    shadow_raw = data.get("shadow")
    shadow = None
    if isinstance(shadow_raw, dict):
        shadow = ShadowArm(
            name=str(shadow_raw.get("name", "shadow")),
            policy_version=str(shadow_raw.get("policy_version", "shadow")),
            enabled=str(shadow_raw.get("enabled", "true")).lower() != "false",
        )
    return PolicyDocument(
        version=str(data.get("version", "1")),
        allow=list(data.get("allow") or []),
        deny=list(data.get("deny") or []),
        shadow=shadow,
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Tiny YAML subset: version, allow/deny lists, shadow mapping."""
    result: dict[str, Any] = {"allow": [], "deny": []}
    section: str | None = None
    shadow: dict[str, str] = {}
    in_shadow = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("-"):
            key = stripped[:-1].strip()
            if key in {"allow", "deny"}:
                section = key
                in_shadow = False
            elif key == "shadow":
                in_shadow = True
                section = None
            else:
                section = None
                in_shadow = False
            continue
        if stripped.startswith("- ") and section in {"allow", "deny"}:
            result[section].append(stripped[2:].strip().strip('"'))
            continue
        if ":" in stripped and indent == 0:
            key, _, value = stripped.partition(":")
            result[key.strip()] = value.strip().strip('"')
            in_shadow = False
            section = None
            continue
        if in_shadow and ":" in stripped:
            key, _, value = stripped.partition(":")
            shadow[key.strip()] = value.strip().strip('"')
    if shadow:
        result["shadow"] = shadow
    return result
