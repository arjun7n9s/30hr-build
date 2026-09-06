"""stdlib JSON HTTP. Handles SSE (GitHub MCP) without SDKs."""

from __future__ import annotations

import json
import time
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
    attempts: int = 3,
) -> dict[str, Any]:
    body, _hdrs = request_json(
        "POST", url, payload, headers, timeout=timeout, attempts=attempts
    )
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
                out_headers = {str(k): str(v) for k, v in response.headers.items()}
                return read_response(response, deadline=time.monotonic() + timeout), out_headers
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"http {exc.code} {url}: {detail[:300]}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last = exc
            continue
    raise RuntimeError(f"http timeout {url}: {last}") from last


def read_response(response: Any, *, deadline: float | None = None) -> dict[str, Any]:
    """JSON or SSE. Stop after a complete event — GitHub MCP keeps the stream open."""
    ctype = str(getattr(response, "headers", {}).get("Content-Type") or "").lower()
    if "text/event-stream" in ctype:
        return read_sse_message(response, deadline=deadline)
    raw = _read_bounded(response, deadline)
    return parse_body(raw)


def _read_bounded(response: Any, deadline: float | None) -> str:
    chunks: list[bytes] = []
    while True:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("http read deadline")
        remaining = 8.0 if deadline is None else max(0.05, deadline - time.monotonic())
        _set_sock_timeout(response, min(8.0, remaining))
        piece = response.read(8192)
        if not piece:
            break
        chunks.append(piece)
    return b"".join(chunks).decode("utf-8")


def _set_sock_timeout(response: Any, seconds: float) -> None:
    fp = getattr(response, "fp", None)
    raw = getattr(fp, "raw", None) if fp is not None else None
    sock = getattr(raw, "_sock", None) if raw is not None else None
    if sock is not None and hasattr(sock, "settimeout"):
        sock.settimeout(max(0.05, seconds))


def read_sse_message(response: Any, *, deadline: float | None = None) -> dict[str, Any]:
    """Read SSE until a JSON-RPC result, a finished chat chunk, or [DONE]. Never wait for EOF."""
    data_lines: list[str] = []
    idle = 0
    chat: dict[str, Any] | None = None
    while idle < 64:
        if deadline is not None and time.monotonic() > deadline:
            break
        remaining = 8.0 if deadline is None else max(0.05, deadline - time.monotonic())
        _set_sock_timeout(response, min(8.0, remaining))
        raw_line = response.readline()
        if not raw_line:
            break
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            parsed = _sse_data_json(data_lines)
            data_lines = []
            if parsed is None:
                idle += 1
                continue
            done, chat = _apply_sse_event(parsed, chat)
            if done is not None:
                return done
            idle = 0
            continue
        if line.startswith(":"):
            idle += 1
            continue
        idle = 0
        if not line.startswith("data:"):
            continue
        chunk = line[5:].lstrip()
        if chunk == "[DONE]":
            return chat or {}
        data_lines.append(chunk)
        parsed = _sse_data_json(data_lines)
        if parsed is None:
            continue
        done, chat = _apply_sse_event(parsed, chat)
        if done is not None:
            return done
        data_lines = []
    if chat is not None:
        return chat
    parsed = _sse_data_json(data_lines)
    if parsed:
        return parsed
    if deadline is not None and time.monotonic() > deadline:
        raise TimeoutError("sse deadline")
    return {}


def _apply_sse_event(
    parsed: dict[str, Any], chat: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if "jsonrpc" in parsed or "result" in parsed or "error" in parsed:
        if "method" in parsed and "id" not in parsed and "result" not in parsed:
            return None, chat
        return parsed, chat
    if "choices" in parsed:
        if parsed.get("object") == "chat.completion.chunk" or (
            parsed.get("choices")
            and isinstance(parsed["choices"][0], dict)
            and "delta" in parsed["choices"][0]
        ):
            return None, _merge_chat_chunk(chat, parsed)
        return parsed, parsed
    return parsed, chat


def _merge_chat_chunk(acc: dict[str, Any] | None, chunk: dict[str, Any]) -> dict[str, Any]:
    if acc is None:
        acc = {
            "id": chunk.get("id"),
            "model": chunk.get("model"),
            "choices": [{"message": {"role": "assistant", "content": ""}}],
            "usage": {},
        }
    delta = ((chunk.get("choices") or [{}])[0] or {}).get("delta") or {}
    content = delta.get("content") or ""
    message = acc["choices"][0]["message"]
    message["content"] = str(message.get("content") or "") + str(content)
    if chunk.get("usage"):
        acc["usage"] = chunk["usage"]
    acc["id"] = chunk.get("id") or acc.get("id")
    acc["model"] = chunk.get("model") or acc.get("model")
    return acc


def _sse_data_json(data_lines: list[str]) -> dict[str, Any] | None:
    blob = "\n".join(data_lines).strip()
    if not blob or blob == "[DONE]":
        return None
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else {"data": obj}


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
