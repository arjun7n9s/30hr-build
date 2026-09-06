"""stdlib JSON HTTP. No SDKs."""

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
    timeout: float = 20.0,
) -> dict[str, Any]:
    return _request("POST", url, payload, headers, timeout=timeout)


def get_json(
    url: str,
    headers: dict[str, str],
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    return _request("GET", url, None, headers, timeout=timeout)


def _request(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str],
    *,
    timeout: float,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = {"Accept": "application/json", **headers}
    if body is not None:
        merged["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=merged, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http {exc.code} {url}: {detail[:300]}") from exc
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {"data": parsed}
