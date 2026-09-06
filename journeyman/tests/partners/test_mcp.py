from journeyman.partners.http import parse_body
from journeyman.partners.mcp import _unwrap_mcp


def test_parse_sse_jsonrpc() -> None:
    raw = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}\n\n'
    )
    body = parse_body(raw)
    assert body["jsonrpc"] == "2.0"
    assert "result" in body


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
