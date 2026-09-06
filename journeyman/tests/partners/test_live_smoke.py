"""Live partner smoke. Skipped unless required keys are in the environment."""

from __future__ import annotations

import os

import pytest

from journeyman.evalset.frozen import load_frozen_eval
from journeyman.partners.chat import ChatClient
from journeyman.partners.mcp import GithubMcp
from journeyman.partners.sink import NeatlogsTraceSink
from journeyman.spend import load_local_env

_REQUIRED = (
    "TMX_API_KEY",
    "OPENAI_API_KEY",
    "NEATLOGS_API_KEY",
    "NEATLOGS_PROJECT_ID",
)


def _live_ready() -> bool:
    load_local_env()
    if not all(os.environ.get(name) for name in _REQUIRED):
        return False
    return bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))


@pytest.mark.live
def test_live_chat_mcp_neatlogs_trace_id() -> None:
    if not _live_ready():
        pytest.skip("live keys absent from local .env")
    from journeyman.contracts import CostRouterDecision, RouteChoice
    from journeyman.partners.sink import emit_node
    from journeyman.contracts import Stage

    chat = ChatClient(offline=False)
    turn = chat.complete(
        [{"role": "user", "content": "Reply with the single word pong."}],
        CostRouterDecision(
            choice=RouteChoice.CHEAP,
            reason="live smoke",
            model=chat.cheap_model,
            gate_miss=False,
        ),
    )
    assert turn.provider == "cheap"
    assert turn.text
    assert "offline" not in turn.raw

    challenge = load_frozen_eval()
    mcp = GithubMcp(challenge.github, offline=False)
    hit = mcp.call(
        "issue_read",
        {"owner": "arjun7n9s", "repo": "journeyman-fixture", "method": "get", "issue_number": 1},
    )
    assert hit.get("found") is not False
    assert "error" not in hit or hit.get("title")
    assert hit.get("title") or hit.get("body") or hit.get("text")

    sink = NeatlogsTraceSink.from_env()
    from journeyman.ingest import NullTraceSink

    assert not isinstance(sink, NullTraceSink)
    emit_node(sink, "Eval DEV", title="live-smoke", stage=Stage.WATCHED, payload={"n": 1})
    trace_id = sink.flush()
    assert getattr(sink, "last_status", None) == 200 or bool(trace_id)
    assert trace_id or getattr(sink, "last_trace_id", None)
