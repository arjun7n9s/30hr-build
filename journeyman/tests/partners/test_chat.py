from journeyman.contracts import CostRouterDecision, RouteChoice
from journeyman.partners.chat import CHAT_ATTEMPTS, CHAT_TIMEOUT_S, ChatClient


def test_live_chat_retries_timeout_then_succeeds(monkeypatch: object) -> None:
    calls: list[float] = []

    def fake_post(url, payload, headers, timeout=60.0, attempts=3):
        del url, headers, attempts
        calls.append(timeout)
        assert payload.get("stream") is False
        if len(calls) < CHAT_ATTEMPTS:
            raise RuntimeError("http timeout https://api.tensormux.com/v1/chat/completions")
        return {"choices": [{"message": {"content": "pong"}}], "usage": {"total_tokens": 1}}

    monkeypatch.setattr("journeyman.partners.chat.post_json", fake_post)
    monkeypatch.setenv("TMX_API_KEY", "test-not-a-secret")
    chat = ChatClient(offline=False)
    turn = chat.complete(
        [{"role": "user", "content": "Reply with the single word pong."}],
        CostRouterDecision(choice=RouteChoice.CHEAP, reason="timeout test", model=chat.cheap_model),
    )
    assert turn.text == "pong"
    assert turn.provider == "cheap"
    assert "offline" not in turn.raw
    assert calls == [CHAT_TIMEOUT_S] * CHAT_ATTEMPTS
