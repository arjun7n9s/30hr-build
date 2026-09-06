"""Turn raw tool results into a feature record that rules can test.

This is the only place that knows the *shape* of a GitHub tool result. Rules
themselves never see a tool payload — they see `dict[str, list[str]]`, so the
same rule engine works against any third-party app once it has a reader here.

Feature vocabulary produced for an issue:

| field       | meaning                                        |
|-------------|------------------------------------------------|
| `title`     | issue title                                    |
| `body`      | issue body                                     |
| `text`      | title + body, the usual target for `contains`  |
| `labels`    | labels already on the object                   |
| `number`    | issue number as a string                       |
| `state`     | open / closed                                  |
| `path`      | file paths mentioned anywhere in the text      |
| `task_type` | the ask being answered                         |

Every value is a list of strings so a leaf predicate means "any value matches".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

Features = dict[str, list[str]]

_PATH_RE = re.compile(r"\b((?:[\w.-]+/)+[\w.-]+\.\w+)\b")

_ISSUE_LIST_TOOLS = {"list_issues", "search_issues"}
_PR_LIST_TOOLS = {"list_pull_requests", "search_pull_requests"}
_ISSUE_ONE_TOOLS = {"issue_read", "get_issue"}
_PR_ONE_TOOLS = {"pull_request_read", "get_pull_request"}
_LABEL_TOOLS = {"list_label", "list_labels"}
_FILE_TOOLS = {"get_file_contents"}


@dataclass
class Evidence:
    """Structured view of one run's tool results.

    Built from the actor's `tool_calls`, never from stringified payloads — the
    previous string-reparse path silently returned nothing, which is what forced
    hardcoded answers into the triage module.
    """

    issues: list[dict[str, Any]] = field(default_factory=list)
    pulls: list[dict[str, Any]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)

    def issue_by_number(self, number: Any) -> dict[str, Any] | None:
        want = _as_int(number)
        if want is None:
            return None
        return next((row for row in self.issues if _as_int(row.get("number")) == want), None)

    def file(self, *names: str) -> str:
        """First matching file content, matched on path suffix."""
        for name in names:
            for path, content in self.files.items():
                if path == name or path.endswith(f"/{name}"):
                    return content
        return ""


def collect_evidence(tool_calls: list[dict[str, Any]]) -> Evidence:
    evidence = Evidence()
    for call in tool_calls or []:
        if call.get("denied"):
            continue
        name = str(call.get("name") or "")
        result = call.get("result")
        if not isinstance(result, dict) or result.get("found") is False:
            continue
        items = [row for row in (result.get("items") or []) if isinstance(row, dict)]
        if name in _ISSUE_LIST_TOOLS:
            _extend(evidence.issues, items)
        elif name in _PR_LIST_TOOLS:
            _extend(evidence.pulls, items)
        elif name in _ISSUE_ONE_TOOLS and result.get("title") is not None:
            _extend(evidence.issues, [result])
        elif name in _PR_ONE_TOOLS and result.get("title") is not None:
            _extend(evidence.pulls, [result])
        elif name in _LABEL_TOOLS:
            for row in items:
                label = str(row.get("name") or "")
                if label and label not in evidence.labels:
                    evidence.labels.append(label)
        elif name in _FILE_TOOLS:
            path = str(result.get("path") or "")
            content = str(result.get("content") or result.get("text") or "")
            if path and content:
                evidence.files[path] = content
    return evidence


def issue_features(issue: dict[str, Any], *, task_type: str = "") -> Features:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    text = f"{title}\n{body}".strip()
    labels = [str(row.get("name") if isinstance(row, dict) else row) for row in issue.get("labels") or []]
    features: Features = {
        "title": [title],
        "body": [body],
        "text": [text],
        "labels": [label for label in labels if label],
        "path": sorted(set(_PATH_RE.findall(text))),
        "number": [str(issue.get("number") or "")],
        "state": [str(issue.get("state") or "")],
    }
    if task_type:
        features["task_type"] = [task_type]
    return features


def path_features(path: str, *, task_type: str = "") -> Features:
    normalized = str(path or "").replace("\\", "/").lstrip("/")
    features: Features = {
        "path": [normalized],
        "text": [normalized],
        "title": [normalized],
        "body": [],
        "labels": [],
    }
    if task_type:
        features["task_type"] = [task_type]
    return features


def merge_features(*records: Features) -> Features:
    merged: Features = {}
    for record in records:
        for key, values in record.items():
            bucket = merged.setdefault(key, [])
            for value in values:
                if value not in bucket:
                    bucket.append(value)
    return merged


def _extend(target: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        number = _as_int(row.get("number"))
        if number is not None and any(_as_int(seen.get("number")) == number for seen in target):
            continue
        target.append(row)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
