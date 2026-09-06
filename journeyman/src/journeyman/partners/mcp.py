"""Official GitHub MCP readonly client. Fixture doubles offline; REST only behind a flag."""

from __future__ import annotations

import json
import os
from typing import Any

from journeyman.partners.github import EMPTY, FixtureGitHub, GitHubClient
from journeyman.partners.http import request_json
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
        self._session_id: str | None = None
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        name = _ALIASES.get(tool, tool)
        if self.offline:
            return self.fixture.call(name, args)
        if os.environ.get(REST_FLAG) == "1":
            return GitHubClient(self.snapshot, offline=False).call(_rest_alias(name), args)
        key = (name, json.dumps(args, sort_keys=True, default=str))
        if key in self._cache:
            return self._cache[key]
        result = self._rpc(name, args)
        self._cache[key] = result
        return result

    def _ensure_session(self) -> None:
        if self._session_id:
            return
        self._rpc_id += 1
        body, headers = request_json(
            "POST",
            self.url,
            {
                "jsonrpc": "2.0",
                "id": self._rpc_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "journeyman", "version": "0.1.0"},
                },
            },
            self._headers(),
            timeout=40.0,
        )
        self._session_id = (
            headers.get("Mcp-Session-Id")
            or headers.get("mcp-session-id")
            or _header_ci(headers, "mcp-session-id")
        )
        if body.get("error"):
            raise RuntimeError(str(body["error"])[:300])
        try:
            request_json(
                "POST",
                self.url,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                self._headers(),
                timeout=20.0,
            )
        except RuntimeError:
            pass

    def _rpc(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            self._ensure_session()
            self._rpc_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": self._rpc_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            }
            raw, _headers = request_json(
                "POST",
                self.url,
                payload,
                self._headers(),
                timeout=40.0,
            )
        except RuntimeError as exc:
            return {**EMPTY, "error": str(exc)[:300]}
        return _unwrap_mcp(raw)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers


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


def _unwrap_mcp(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("error"):
        return {**EMPTY, "error": str(raw["error"])[:300]}
    result = raw.get("result", raw)
    if not isinstance(result, dict):
        return {"found": True, "data": result}
    content = result.get("content")
    if isinstance(content, list) and content:
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
            elif isinstance(item, dict) and item.get("text"):
                texts.append(str(item["text"]))
        blob = "\n".join(texts).strip()
        if blob:
            try:
                parsed = json.loads(blob)
            except json.JSONDecodeError:
                return {"found": True, "text": blob[:4000], "body": blob[:4000]}
            if isinstance(parsed, dict):
                if "items" not in parsed and isinstance(parsed.get("issues"), list):
                    parsed = {**parsed, "items": parsed["issues"]}
                if "items" not in parsed and isinstance(parsed.get("labels"), list):
                    parsed = {**parsed, "items": parsed["labels"]}
                return {**parsed, "found": parsed.get("found", True)}
            if isinstance(parsed, list):
                return {"found": True, "items": parsed}
    if "found" not in result:
        return {**result, "found": True}
    return result


def _header_ci(headers: dict[str, str], name: str) -> str | None:
    want = name.lower()
    for key, value in headers.items():
        if key.lower() == want:
            return value
    return None


def _rest_alias(name: str) -> str:
    return {
        "issue_read": "get_issue",
        "pull_request_read": "get_pull_request",
        "list_label": "list_labels",
    }.get(name, name)


def mcp_tool_url(owner: str, repo: str, tool: str) -> str:
    del owner, repo, tool
    return MCP_URL
