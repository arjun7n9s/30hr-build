import time

import pytest

from journeyman.partners.http import parse_body, read_sse_message
from journeyman.partners.mcp import _live_args, _unwrap_mcp


def test_parse_sse_jsonrpc() -> None:
    raw = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}\n\n'
    )
    body = parse_body(raw)
    assert body["jsonrpc"] == "2.0"
    assert "result" in body


class _SseAfterEvent:
    """Yields one JSON-RPC event, then would hang if the client kept reading."""

    def __init__(self) -> None:
        self._lines = [
            b"event: message\n",
            b'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n',
            b"\n",
        ]
        self._i = 0

    def readline(self) -> bytes:
        if self._i >= len(self._lines):
            raise AssertionError("SSE reader must stop after the first complete event")
        line = self._lines[self._i]
        self._i += 1
        return line


def test_read_sse_stops_before_eof() -> None:
    body = read_sse_message(_SseAfterEvent())
    assert body["jsonrpc"] == "2.0"
    assert body["result"]["ok"] is True


class _SseNoBlank:
    def __init__(self) -> None:
        self._sent = False

    def readline(self) -> bytes:
        if self._sent:
            raise AssertionError("complete JSON-RPC data line is enough")
        self._sent = True
        return b'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n'


def test_read_sse_accepts_jsonrpc_without_blank_line() -> None:
    body = read_sse_message(_SseNoBlank())
    assert body["result"]["ok"] is True


class _ChatSse:
    def __init__(self) -> None:
        self._lines = [
            b'data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"po"}}]}\n',
            b"\n",
            b'data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"ng"}}]}\n',
            b"\n",
            b"data: [DONE]\n",
            b"\n",
        ]
        self._i = 0

    def readline(self) -> bytes:
        if self._i >= len(self._lines):
            raise AssertionError("chat SSE must stop at [DONE], not EOF")
        line = self._lines[self._i]
        self._i += 1
        return line


def test_read_sse_assembles_chat_chunks() -> None:
    body = read_sse_message(_ChatSse())
    assert body["choices"][0]["message"]["content"] == "pong"


class _KeepaliveOnly:
    def readline(self) -> bytes:
        return b": keepalive\n"


def test_read_sse_deadline_raises() -> None:
    with pytest.raises(TimeoutError):
        read_sse_message(_KeepaliveOnly(), deadline=time.monotonic() - 1)


def test_parse_plain_json() -> None:
    body = parse_body('{"success": true, "trace_id": "abc"}')
    assert body["trace_id"] == "abc"


def test_unwrap_mcp_text_json() -> None:
    raw = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "content": [
                {"type": "text", "text": '{"number":1,"title":"API returns 500 on empty payload"}'}
            ]
        },
    }
    hit = _unwrap_mcp(raw)
    assert hit["found"] is True
    assert hit["number"] == 1
    assert "500" in hit["title"]


def test_unwrap_mcp_issues_list() -> None:
    raw = {
        "result": {
            "content": [{"type": "text", "text": '{"issues":[{"number":1,"title":"a"}]}'}]
        }
    }
    hit = _unwrap_mcp(raw)
    assert hit["found"] is True
    assert hit["items"][0]["number"] == 1


def test_live_args_normalize_pull_request_read() -> None:
    mapped = _live_args("pull_request_read", {"owner": "o", "repo": "r", "pull_number": 19})
    assert mapped["method"] == "get"
    assert mapped["pullNumber"] == 19
    assert "pull_number" not in mapped


def test_unwrap_mcp_is_error_is_a_failed_tool() -> None:
    hit = _unwrap_mcp(
        {
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "unknown tool: list_label"}],
            }
        }
    )
    assert hit.get("found") is False
    assert "unknown" in str(hit.get("error") or "")
