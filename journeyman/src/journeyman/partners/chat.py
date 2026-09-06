"""Cheap-first chat and a separate embeddings path. Keys from local .env only."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from journeyman.contracts import (
    CHEAP_BASE_URL,
    CHEAP_MODEL,
    CostRouterDecision,
    EMBED_MODEL,
    ESCALATE_BASE_URL,
    ESCALATE_MODEL,
    RouteChoice,
)
from journeyman.partners.http import post_json
from journeyman.spend import load_local_env

# Hard cap per hop so a stalled TensorMux/OpenAI stream cannot freeze the CLI.
CHAT_TIMEOUT_S = 25.0
CHAT_ATTEMPTS = 3

HALLUCINATED = (
    "This repository always has a guaranteed 90-day refund policy "
    "and issue 12 is already shipped."
)
ABSTAIN = "Evidence is missing. I cannot answer from this repository."
CHEAP_COST = 0.001
ESCALATE_COST = 0.02


@dataclass
class ChatTurn:
    text: str
    model: str
    provider: str
    tokens: int
    cost: float
    raw: dict[str, Any]


class ChatClient:
    def __init__(self, *, offline: bool = True) -> None:
        load_local_env()
        self.offline = offline
        if not offline and not _cheap_key():
            raise RuntimeError("live mode needs TMX_API_KEY in local .env")
        self.cheap_model = os.environ.get("TENSOR_MUX_MODEL", CHEAP_MODEL)
        self.escalate_model = os.environ.get("OPENAI_ESCALATE_MODEL", ESCALATE_MODEL)
        self.embed_model = os.environ.get("OPENAI_EMBEDDING_MODEL", EMBED_MODEL)
        self.cheap_base = (
            os.environ.get("TENSOR_MUX_BASE_URL")
            or os.environ.get("CHEAP_BASE_URL")
            or CHEAP_BASE_URL
        )
        self.escalate_base = os.environ.get("OPENAI_BASE_URL") or os.environ.get(
            "ESCALATE_BASE_URL", ESCALATE_BASE_URL
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        decision: CostRouterDecision,
        *,
        evidence: list[str] | None = None,
    ) -> ChatTurn:
        if self.offline:
            return self._offline(messages, decision, evidence or [])
        return self._http(messages, decision)

    def embed(self, text: str) -> ChatTurn:
        """Embeddings stay on the escalate path, never the cheap chat hop."""
        key = _escalate_key()
        if self.offline or not key:
            return ChatTurn(
                text="",
                model=self.embed_model,
                provider="embed",
                tokens=len(text.split()),
                cost=0.0,
                raw={"offline": True, "dim": 8, "keyword_fallback": not bool(key)},
            )
        payload = _post_with_retry(
            self.escalate_base.rstrip("/") + "/embeddings",
            {"model": self.embed_model, "input": text},
            {"Authorization": f"Bearer {key}"},
        )
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        tokens = int(usage.get("total_tokens") or 0)
        return ChatTurn(
            text="",
            model=self.embed_model,
            provider="embed",
            tokens=tokens,
            cost=0.0,
            raw=payload,
        )

    def _http(self, messages: list[dict[str, str]], decision: CostRouterDecision) -> ChatTurn:
        if decision.choice is RouteChoice.ESCALATE:
            base, key, provider = self.escalate_base, _escalate_key(), "escalate"
        else:
            base, key, provider = self.cheap_base, _cheap_key(), "cheap"
        if not key:
            raise RuntimeError("chat key missing from local .env")
        payload = _post_with_retry(
            base.rstrip("/") + "/chat/completions",
            {"model": decision.model, "messages": messages, "stream": False},
            {"Authorization": f"Bearer {key}"},
        )
        text = _choice_text(payload)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        tokens = int(usage.get("total_tokens") or len(text.split()))
        cost = float(usage.get("cost") or (ESCALATE_COST if provider == "escalate" else CHEAP_COST))
        return ChatTurn(
            text=text,
            model=decision.model,
            provider=provider,
            tokens=tokens,
            cost=cost,
            raw=payload,
        )

    def _offline(
        self,
        messages: list[dict[str, str]],
        decision: CostRouterDecision,
        evidence: list[str],
    ) -> ChatTurn:
        provider = "escalate" if decision.choice is RouteChoice.ESCALATE else "cheap"
        cost = ESCALATE_COST if provider == "escalate" else CHEAP_COST
        if evidence:
            blob = "\n".join(evidence)
            text = f"From repo evidence:\n{blob[:1200]}"
        elif _asks_grounding(messages):
            text = ABSTAIN
        else:
            text = HALLUCINATED
        tokens = len(text.split())
        return ChatTurn(
            text=text,
            model=decision.model,
            provider=provider,
            tokens=tokens,
            cost=cost,
            raw={"offline": True},
        )


def _post_with_retry(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    last: Exception | None = None
    for _ in range(CHAT_ATTEMPTS):
        try:
            return post_json(url, payload, headers, timeout=CHAT_TIMEOUT_S, attempts=1)
        except RuntimeError as exc:
            last = exc
    raise RuntimeError(f"chat timeout after {CHAT_ATTEMPTS} attempts: {last}") from last


def _asks_grounding(messages: list[dict[str, str]]) -> bool:
    blob = " ".join(message.get("content", "") for message in messages).lower()
    return any(
        token in blob
        for token in ("evidence", "cite", "lookup", "tool", "refuse", "do not invent", "say so")
    )


def _choice_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return str(payload.get("text") or "")
    message = choices[0].get("message") or {}
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(choices[0].get("text") or "")


def _cheap_key() -> str:
    return (
        os.environ.get("TMX_API_KEY")
        or os.environ.get("TENSOR_MUX_API_KEY")
        or os.environ.get("TENSOR_API_KEY")
        or ""
    )


def _escalate_key() -> str:
    return os.environ.get("OPENAI_API_KEY") or ""
