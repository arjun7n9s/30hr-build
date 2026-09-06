"""Readonly GitHub actor: cheap-first hops, gated tools, traced every hop."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from journeyman.contracts import (
    Playbook,
    SkillQuery,
    SpanKind,
    Stage,
    TraceEventRow,
    TraceSpan,
)
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.partners.chat import ChatClient, ChatTurn
from journeyman.partners.github import GitHubClient
from journeyman.policy import ToolGateway
from journeyman.runtime import ContextGate
from journeyman.skills import SkillLibrary as SkillStore
from journeyman.spend import CostRouter

_TOOL_HINTS = ("tool", "lookup", "evidence", "cite", "search", "issue", "refuse", "do not invent")


@dataclass
class ActorTurn:
    text: str
    spans: list[TraceSpan]
    tool_calls: list[dict[str, Any]]
    tokens: int
    cost: float
    playbook_hits: list[str]
    model: str
    escalated: bool
    events: list[TraceEventRow] = field(default_factory=list)


class Actor:
    def __init__(
        self,
        *,
        router: CostRouter | None = None,
        gateway: ToolGateway | None = None,
        gate: ContextGate | None = None,
        chat: ChatClient | None = None,
        github: GitHubClient | None = None,
        skills: SkillStore | None = None,
        sink: TraceSink | None = None,
        repo: str = "demo/widget",
        project: str = "demo",
    ) -> None:
        self.router = router or CostRouter()
        self.gateway = gateway or ToolGateway()
        self.gate = gate or ContextGate()
        self.chat = chat or ChatClient(offline=True)
        self.github = github or GitHubClient(offline=True)
        self.skills = skills or SkillStore()
        self.sink = sink or NullTraceSink()
        self.repo = repo
        self.project = project
        owner, _, name = repo.partition("/")
        self.owner = owner or "demo"
        self.repo_name = name or repo

    def run(
        self,
        prompt: str,
        *,
        playbook: Playbook,
        session_id: str = "demo",
        prompt_variant: str = "baseline",
    ) -> ActorTurn:
        trace_id = uuid.uuid4().hex[:16]
        hits = _playbook_hits(playbook, prompt)
        skill_hits = self.skills.find(SkillQuery(text=prompt))
        hits.extend(f"skill:{hit.skill.name}" for hit in skill_hits)
        system = _system_prompt(playbook, skill_hits)
        evidence: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        spans: list[TraceSpan] = []
        events: list[TraceEventRow] = []
        tokens = 0
        cost = 0.0
        if _should_use_tools(playbook):
            for name, args in _plan_tools(prompt, self.owner, self.repo_name):
                result, tool_span, event = self._tool_hop(
                    name,
                    args,
                    trace_id=trace_id,
                    session_id=session_id,
                    hits=hits,
                )
                spans.append(tool_span)
                events.append(event)
                denied = bool(result.get("denied"))
                tool_calls.append({"name": name, "args": args, "result": result, "denied": denied})
                if not denied and _has_payload(result):
                    evidence.append(_evidence_text(name, result))
        first = self.router.decide(prompt)
        turn = self.chat.complete(
            _messages(system, prompt, evidence),
            first,
            evidence=evidence,
        )
        span, event = self._llm_span(
            prompt,
            turn,
            trace_id=trace_id,
            session_id=session_id,
            prompt_variant=prompt_variant,
            hits=hits,
            tool_calls=tool_calls,
        )
        spans.append(span)
        events.append(event)
        tokens += turn.tokens
        cost += turn.cost
        score = _grounding_score(turn.text, evidence)
        second = self.router.decide(prompt, cheap_output=turn.text, score=score)
        escalated = second.choice is not first.choice or second.gate_miss
        final = turn
        if escalated:
            final = self.chat.complete(
                _messages(system, prompt, evidence),
                second,
                evidence=evidence,
            )
            span, event = self._llm_span(
                prompt,
                final,
                trace_id=trace_id,
                session_id=session_id,
                prompt_variant=prompt_variant,
                hits=hits,
                tool_calls=tool_calls,
            )
            spans.append(span)
            events.append(event)
            tokens += final.tokens
            cost += final.cost
        return ActorTurn(
            text=final.text,
            spans=spans,
            tool_calls=tool_calls,
            tokens=tokens,
            cost=cost,
            playbook_hits=hits,
            model=final.model,
            escalated=escalated,
            events=events,
        )

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        result, _, _ = self._tool_hop(
            name,
            args or {},
            trace_id="adhoc",
            session_id="demo",
            hits=[],
        )
        return result

    def _tool_hop(
        self,
        name: str,
        args: dict[str, Any],
        *,
        trace_id: str,
        session_id: str,
        hits: list[str],
    ) -> tuple[dict[str, Any], TraceSpan, TraceEventRow]:
        sendoff = self.gate.enter("tool", {"tool": name, "args": args}, include=["tool", "args"])
        allowed = self.gateway.allow(name, args)
        self.gate.exit(sendoff, tool=name)
        if not allowed.live_allowed:
            result: dict[str, Any] = {"found": False, "denied": True, "error": "policy deny"}
        else:
            raw = self.github.call(name, args)
            result = raw if isinstance(raw, dict) else {"found": False, "error": "bad tool result"}
            if "found" not in result:
                result = {**result, "found": True}
        span = TraceSpan(
            span_id=uuid.uuid4().hex[:12],
            trace_id=trace_id,
            project=self.project,
            started_at=datetime.now(timezone.utc),
            input_text=name,
            output_text=str(result)[:400],
            session_id=session_id,
            prompt_variant=None,
            span_kind=SpanKind.TOOL,
            tool_calls=[{"name": name, "args": args, "result": result}],
            raw={
                "name": f"tool.{name}",
                "provider": "github",
                "model": "",
                "tokens": 0,
                "cost": 0.0,
                "playbook_hits": hits,
                "denied": bool(result.get("denied")),
            },
        )
        event = TraceEventRow(
            work_item_id=f"work-{span.span_id}",
            stage=Stage.WATCHED,
            title=f"tool {name}",
            detail="denied" if result.get("denied") else name,
            payload={"tool": name, "denied": bool(result.get("denied"))},
        )
        self.sink.emit(event)
        self.sink.emit_span(span)
        return result, span, event

    def _llm_span(
        self,
        prompt: str,
        turn: ChatTurn,
        *,
        trace_id: str,
        session_id: str,
        prompt_variant: str,
        hits: list[str],
        tool_calls: list[dict[str, Any]],
    ) -> tuple[TraceSpan, TraceEventRow]:
        span = TraceSpan(
            span_id=uuid.uuid4().hex[:12],
            trace_id=trace_id,
            project=self.project,
            started_at=datetime.now(timezone.utc),
            input_text=prompt,
            output_text=turn.text,
            session_id=session_id,
            prompt_variant=prompt_variant,
            span_kind=SpanKind.LLM,
            tool_calls=[{k: call[k] for k in ("name", "result") if k in call} for call in tool_calls],
            raw={
                "name": "llm.complete",
                "provider": turn.provider,
                "model": turn.model,
                "tokens": turn.tokens,
                "cost": turn.cost,
                "playbook_hits": hits,
            },
        )
        event = TraceEventRow(
            work_item_id=f"work-{span.span_id}",
            stage=Stage.WATCHED,
            title="llm hop",
            detail=turn.model,
            payload={
                "provider": turn.provider,
                "model": turn.model,
                "tokens": turn.tokens,
                "cost": turn.cost,
                "playbook_hits": hits,
            },
        )
        self.sink.emit(event)
        self.sink.emit_span(span)
        return span, event


def _should_use_tools(playbook: Playbook) -> bool:
    if playbook.empty:
        return False
    blob = " ".join(entry.text for entry in playbook.entries).lower()
    return any(hint in blob for hint in _TOOL_HINTS)


def _playbook_hits(playbook: Playbook, prompt: str) -> list[str]:
    needle = prompt.lower()
    hits: list[str] = []
    for entry in playbook.entries:
        blob = f"{entry.id} {entry.text} {' '.join(entry.tags)}".lower()
        if not needle or any(token in blob for token in needle.split()[:6]) or entry.text:
            hits.append(entry.id)
    return hits[:8]


def _system_prompt(playbook: Playbook, skill_hits: list[Any]) -> str:
    parts = [entry.text for entry in playbook.entries if entry.text.strip()]
    for hit in skill_hits:
        parts.append(f"skill {hit.skill.name}: {hit.skill.body}")
    return "\n\n".join(parts) or "Answer the user."


def _messages(system: str, prompt: str, evidence: list[str]) -> list[dict[str, str]]:
    user = prompt
    if evidence:
        user = prompt + "\n\nRepo evidence:\n" + "\n".join(evidence[:8])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _plan_tools(question: str, owner: str, repo: str) -> list[tuple[str, dict[str, Any]]]:
    planned: list[tuple[str, dict[str, Any]]] = []
    issue = re.search(r"issue\s+#?(\d+)", question, re.I)
    pull = re.search(r"(?:pull request|pr)\s+#?(\d+)", question, re.I)
    base = {"owner": owner, "repo": repo}
    if issue:
        planned.append(("get_issue", {**base, "issue_number": int(issue.group(1))}))
    if pull:
        planned.append(("get_pull_request", {**base, "pull_number": int(pull.group(1))}))
    planned.append(("search_issues", {**base, "query": question}))
    planned.append(("search_code", {**base, "query": question}))
    if re.search(r"label", question, re.I):
        planned.append(("list_labels", dict(base)))
    path_hit = re.search(r"([\w./-]+\.py)", question)
    if path_hit or re.search(r"retry", question, re.I):
        planned.append(("get_file_contents", {**base, "path": path_hit.group(1) if path_hit else "src/retry.py"}))
    return planned


def _has_payload(result: dict[str, Any]) -> bool:
    if result.get("found") is False:
        return False
    items = result.get("items")
    if isinstance(items, list):
        return bool(items)
    return bool(result.get("body") or result.get("title") or result.get("content") or result.get("full_name"))


def _evidence_text(name: str, result: dict[str, Any]) -> str:
    return f"{name}: {result}"


def _grounding_score(output: str, evidence: list[str]) -> float:
    text = output.lower()
    abstain = any(
        token in text
        for token in ("missing", "cannot answer", "do not know", "don't know", "no evidence", "not found")
    )
    if evidence:
        return 0.95
    if abstain:
        return 0.9
    return 0.2
