"""Official GitHub MCP readonly client. Fixture doubles offline; REST only behind a flag."""

from __future__ import annotations

import os
from typing import Any

from journeyman.partners.github import EMPTY, FixtureGitHub, GitHubClient
from journeyman.partners.http import post_json
from journeyman.spend import load_local_env

MCP_URL = "https://api.githubcopilot.com/mcp/readonly"
REST_FLAG = "JOURNEYMAN_GITHUB_REST"

_ALIASES = {
    "get_issue": "issue_read",
    "get_pull_request": "pull_request_read",
    "list_labels": "list_label",
}


class GithubMcp:
    def __init__(self, snapshot: dict[str, Any] | None = None, *, offline: bool = True) -> None:
        load_local_env()
        self.snapshot = snapshot or {}
        self.fixture = FixtureMcp(self.snapshot)
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        if not offline and not token and os.environ.get(REST_FLAG) != "1":
            raise RuntimeError("live mode needs GITHUB_TOKEN in local .env")
        self.offline = offline
        self.token = token
        self.url = os.environ.get("GITHUB_MCP_URL", MCP_URL)
        self._rpc_id = 0

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        name = _ALIASES.get(tool, tool)
        if self.offline:
            return self.fixture.call(name, args)
        if os.environ.get(REST_FLAG) == "1":
            return GitHubClient(self.snapshot, offline=False).call(_rest_alias(name), args)
        return self._rpc(name, args)

    def _rpc(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        try:
            raw = post_json(
                self.url,
                payload,
                {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json, text/event-stream",
                },
            )
        except RuntimeError as exc:
            return {**EMPTY, "error": str(exc)[:300]}
        result = raw.get("result", raw)
        if isinstance(result, dict):
            return {**result, "found": result.get("found", True)}
        return {"found": True, "data": result}


class FixtureMcp:
    """Serves frozen eval cases under official MCP tool names."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.inner = FixtureGitHub(snapshot)
        self.snapshot = snapshot

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        name = _ALIASES.get(tool, tool)
        mapped = dict(args)
        if name == "issue_read":
            mapped["issue_number"] = mapped.get("issue_number") or mapped.get("number")
            return self.inner.call("get_issue", mapped)
        if name == "pull_request_read":
            mapped["pull_number"] = mapped.get("pull_number") or mapped.get("number")
            return self.inner.call("get_pull_request", mapped)
        if name == "list_label":
            return self.inner.call("list_labels", mapped)
        if name == "get_repository_tree":
            files = list(self.snapshot.get("files") or [])
            return {"found": True, "items": [{"path": row.get("path")} for row in files if isinstance(row, dict)]}
        if name == "search_repositories":
            repo = self.snapshot.get("repo") or "arjun7n9s/journeyman-fixture"
            return {"found": True, "items": [{"full_name": repo}]}
        if name == "get_me":
            return {"found": True, "login": "fixture"}
        return self.inner.call(name if name != "issue_read" else "get_issue", mapped)


def _rest_alias(name: str) -> str:
    return {
        "issue_read": "get_issue",
        "pull_request_read": "get_pull_request",
        "list_label": "list_labels",
    }.get(name, name)


def mcp_tool_url(owner: str, repo: str, tool: str) -> str:
    del owner, repo, tool
    return MCP_URL
