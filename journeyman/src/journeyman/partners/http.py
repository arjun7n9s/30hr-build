"""stdlib JSON HTTP. Handles SSE (GitHub MCP) without SDKs."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    body, _hdrs = request_json("POST", url, payload, headers, timeout=timeout)
    return body


def get_json(
    url: str,
    headers: dict[str, str],
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    body, _hdrs = request_json("GET", url, None, headers, timeout=timeout)
    return body


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str],
    *,
    timeout: float = 60.0,
    attempts: int = 3,
) -> tuple[dict[str, Any], dict[str, str]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = {"Accept": "application/json", **headers}
    if body is not None:
        merged["Content-Type"] = "application/json"
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        request = urllib.request.Request(url, data=body, headers=merged, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                out_headers = {str(k): str(v) for k, v in response.headers.items()}
            return parse_body(raw), out_headers
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"http {exc.code} {url}: {detail[:300]}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last = exc
            continue
    raise RuntimeError(f"http timeout {url}: {last}") from last


def parse_body(raw: str) -> dict[str, Any]:
    text = (raw or "").lstrip("\ufeff").strip()
    if not text:
        return {}
    if text[0] in "{[":
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    parsed: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            parsed = obj
    if parsed is None:
        raise RuntimeError(f"http body not json: {text[:180]}")
    return parsed
