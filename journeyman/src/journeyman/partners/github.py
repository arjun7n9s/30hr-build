"""Readonly GitHub tool client. Fixture path for offline demo; HTTP when a token is set."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote, urlencode

from journeyman.partners.http import get_json
from journeyman.spend import load_local_env

EMPTY = {"found": False}


class GitHubClient:
    def __init__(self, snapshot: dict[str, Any] | None = None, *, offline: bool = True) -> None:
        load_local_env()
        self.snapshot = snapshot or {}
        token = os.environ.get("GITHUB_TOKEN") or ""
        self.offline = offline or not token
        self.token = token
        self.api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            return FixtureGitHub(self.snapshot).call(tool, args)
        return self._http(tool, args)

    def _http(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        owner, repo = _owner_repo(args)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        path = _rest_path(tool, owner, repo, args)
        if path is None:
            return {**EMPTY, "error": "unknown tool"}
        try:
            return get_json(self.api + path, headers)
        except RuntimeError as exc:
            return {**EMPTY, "error": str(exc)[:300]}


class FixtureGitHub:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        issues = list(self.snapshot.get("issues") or [])
        pulls = list(self.snapshot.get("pulls") or [])
        files = list(self.snapshot.get("files") or [])
        commits = list(self.snapshot.get("commits") or [])
        labels = list(self.snapshot.get("labels") or [])
        branches = list(self.snapshot.get("branches") or [])
        repo = self.snapshot.get("repo") or args.get("repo") or "demo/widget"
        if tool == "get_repository":
            return {"found": True, "full_name": repo, "description": "fixture repository"}
        if tool == "list_issues":
            return {"found": True, "items": issues}
        if tool == "get_issue":
            hit = _by_number(issues, args.get("issue_number") or args.get("number"))
            return {"found": bool(hit), **(hit or {})}
        if tool == "search_issues":
            return {"found": True, "items": _search(issues, str(args.get("query") or ""), ("title", "body"))}
        if tool == "list_pull_requests":
            return {"found": True, "items": pulls}
        if tool == "get_pull_request":
            hit = _by_number(pulls, args.get("pull_number") or args.get("number"))
            return {"found": bool(hit), **(hit or {})}
        if tool == "search_pull_requests":
            return {"found": True, "items": _search(pulls, str(args.get("query") or ""), ("title", "body"))}
        if tool == "search_code":
            return {"found": True, "items": _search(files, str(args.get("query") or ""), ("path", "content"))}
        if tool == "get_file_contents":
            path = str(args.get("path") or "")
            for row in files:
                if str(row.get("path")) == path:
                    return {"found": True, **row}
            return {**EMPTY}
        if tool == "list_labels":
            return {"found": True, "items": labels}
        if tool == "get_label":
            name = str(args.get("name") or "")
            for row in labels:
                label = row if isinstance(row, dict) else {"name": row}
                if str(label.get("name")) == name:
                    return {"found": True, **label}
            return {**EMPTY}
        if tool == "list_commits":
            return {"found": True, "items": commits}
        if tool == "get_commit":
            sha = str(args.get("sha") or "")
            for row in commits:
                if str(row.get("sha")) == sha:
                    return {"found": True, **row}
            return {**EMPTY}
        if tool == "list_branches":
            return {"found": True, "items": branches}
        return {**EMPTY, "error": "unknown tool"}


def _owner_repo(args: dict[str, Any]) -> tuple[str, str]:
    if args.get("owner") and args.get("repo"):
        return str(args["owner"]), str(args["repo"])
    full = str(args.get("full_name") or "demo/widget")
    owner, _, repo = full.partition("/")
    return owner, repo or full


def _rest_path(tool: str, owner: str, repo: str, args: dict[str, Any]) -> str | None:
    base = f"/repos/{quote(owner)}/{quote(repo)}"
    if tool == "get_repository":
        return base
    if tool == "list_issues":
        return base + "/issues"
    if tool == "get_issue":
        return base + f"/issues/{int(args.get('issue_number') or args.get('number') or 0)}"
    if tool == "search_issues":
        q = urlencode({"q": f"repo:{owner}/{repo} {args.get('query') or ''}"})
        return f"/search/issues?{q}"
    if tool == "list_pull_requests":
        return base + "/pulls"
    if tool == "get_pull_request":
        return base + f"/pulls/{int(args.get('pull_number') or args.get('number') or 0)}"
    if tool == "search_pull_requests":
        q = urlencode({"q": f"repo:{owner}/{repo} is:pr {args.get('query') or ''}"})
        return f"/search/issues?{q}"
    if tool == "search_code":
        q = urlencode({"q": f"repo:{owner}/{repo} {args.get('query') or ''}"})
        return f"/search/code?{q}"
    if tool == "get_file_contents":
        return base + f"/contents/{quote(str(args.get('path') or ''))}"
    if tool == "list_labels":
        return base + "/labels"
    if tool == "get_label":
        return base + f"/labels/{quote(str(args.get('name') or ''))}"
    if tool == "list_commits":
        return base + "/commits"
    if tool == "get_commit":
        return base + f"/commits/{quote(str(args.get('sha') or ''))}"
    if tool == "list_branches":
        return base + "/branches"
    return None


def _by_number(rows: list[Any], number: Any) -> dict[str, Any] | None:
    try:
        want = int(number)
    except (TypeError, ValueError):
        return None
    for row in rows:
        if isinstance(row, dict) and int(row.get("number") or 0) == want:
            return row
    return None


def _search(rows: list[Any], query: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    tokens = [
        token.lower().strip("?.!,")
        for token in query.split()
        if len(token.strip("?.!,")) > 3
    ]
    hits: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blob = " ".join(str(row.get(field) or "") for field in fields).lower()
        if not tokens or any(token in blob for token in tokens):
            hits.append(row)
    return hits
