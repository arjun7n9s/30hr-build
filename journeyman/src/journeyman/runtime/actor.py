"""Readonly GitHub actor: cheap-first hops, gated tools, traced every hop."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from journeyman.contracts import (
    Playbook,
    RuleHit,
    SkillQuery,
    SpanKind,
    Split,
    Stage,
    TraceEventRow,
    TraceSpan,
)
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.memory import ScriptStore
from journeyman.partners.chat import ChatClient, ChatTurn
from journeyman.partners.github import GitHubClient
from journeyman.partners.mcp import GithubMcp
from journeyman.partners.sink import emit_node
from journeyman.policy import ToolGateway
from journeyman.runtime import ContextGate
from journeyman.runtime.triage import answer_task
from journeyman.skills import SkillLibrary as SkillStore
from journeyman.spend import CostRouter

_STOPWORDS = frozenset(
    {
        "about", "all", "and", "any", "are", "can", "does", "for", "from", "get", "has",
        "have", "how", "into", "its", "list", "not", "our", "repo", "repository", "say",
        "that", "the", "their", "there", "these", "this", "true", "was", "were", "what",
        "when", "where", "which", "who", "why", "with", "you", "your",
    }
)


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
    answer: dict[str, Any] = field(default_factory=dict)
    speed_ms: float = 0.0
    rule_hits: list[RuleHit] = field(default_factory=list)
    """Which learned rules produced this answer. Input to per-rule attribution."""


class Actor:
    def __init__(
        self,
        *,
        router: CostRouter | None = None,
        gateway: ToolGateway | None = None,
        gate: ContextGate | None = None,
        chat: ChatClient | None = None,
        github: GitHubClient | GithubMcp | None = None,
        skills: SkillStore | None = None,
        scripts: ScriptStore | None = None,
        sink: TraceSink | None = None,
        repo: str = "arjun7n9s/journeyman-fixture",
        project: str = "demo",
    ) -> None:
        self.router = router or CostRouter()
        self.gateway = gateway or ToolGateway()
        self.gate = gate or ContextGate()
        self.chat = chat or ChatClient(offline=True)
        self.github = github or GithubMcp(offline=True)
        self.skills = skills or SkillStore()
        self.scripts = scripts or ScriptStore()
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
        split: Split = Split.DEV,
        task: dict[str, Any] | None = None,
    ) -> ActorTurn:
        started = time.perf_counter()
        trace_id = uuid.uuid4().hex[:16]
        embed_decision = self.router.embed_route()
        emit_node(
            self.sink,
            "Router",
            title="embed",
            detail=embed_decision.model,
            payload={"choice": embed_decision.choice.value, "path": "embed"},
        )
        try:
            self.chat.embed(prompt)
        except Exception:
            pass
        hits = _playbook_hits(playbook, prompt)
        skill_hits = self.skills.find(SkillQuery(text=prompt))
        hits.extend(f"skill:{hit.skill.name}" for hit in skill_hits)
        script_hits = self.scripts.find(prompt)
        hits.extend(f"script:{item.name}" for item in script_hits)
        system = _system_prompt(playbook, skill_hits, script_hits)
        evidence: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        spans: list[TraceSpan] = []
        events: list[TraceEventRow] = []
        tokens = 0
        cost = 0.0
        if _should_use_tools(playbook):
            for name, args in _plan_tools(prompt, self.owner, self.repo_name, task):
                result, tool_span, event = self._tool_hop(
                    name,
                    args,
                    trace_id=trace_id,
                    session_id=session_id,
                    hits=hits,
                    split=split,
                )
                spans.append(tool_span)
                events.append(event)
                denied = bool(result.get("denied"))
                tool_calls.append({"name": name, "args": args, "result": result, "denied": denied})
                if not denied and _has_payload(result) and _relevant(prompt, result):
                    evidence.append(_evidence_text(name, result))
        first = self.router.decide(prompt)
        emit_node(
            self.sink,
            "Router",
            title=first.choice.value,
            detail=first.model,
            payload={"gate_miss": first.gate_miss, "node": "Actor"},
        )
        try:
            turn = self.chat.complete(
                _messages(system, prompt, evidence),
                first,
                evidence=evidence,
            )
        except RuntimeError as exc:
            turn = ChatTurn(
                text=f"chat error: {exc}",
                model=first.model,
                provider="error",
                tokens=0,
                cost=0.0,
                raw={"error": str(exc)[:300]},
            )
        span, event = self._llm_span(
            prompt,
            turn,
            trace_id=trace_id,
            session_id=session_id,
            prompt_variant=prompt_variant,
            hits=hits,
            tool_calls=tool_calls,
            split=split,
        )
        spans.append(span)
        events.append(event)
        tokens += turn.tokens
        cost += turn.cost
        score = _grounding_score(turn.text, evidence)
        second = self.router.decide(prompt, cheap_output=turn.text, score=score)
        if second.gate_miss:
            emit_node(
                self.sink,
                "Router",
                title="escalate",
                detail=second.model,
                payload={"gate_miss": True, "reason": str(second.escalate_reason)},
            )
        escalated = second.choice is not first.choice or second.gate_miss
        final = turn
        if escalated:
            try:
                final = self.chat.complete(
                    _messages(system, prompt, evidence),
                    second,
                    evidence=evidence,
                )
            except RuntimeError as exc:
                final = ChatTurn(
                    text=f"chat error: {exc}",
                    model=second.model,
                    provider="error",
                    tokens=0,
                    cost=0.0,
                    raw={"error": str(exc)[:300]},
                )
            span, event = self._llm_span(
                prompt,
                final,
                trace_id=trace_id,
                session_id=session_id,
                prompt_variant=prompt_variant,
                hits=hits,
                tool_calls=tool_calls,
                split=split,
            )
            spans.append(span)
            events.append(event)
            tokens += final.tokens
            cost += final.cost
        structured: dict[str, Any] = {}
        rule_hits: list[RuleHit] = []
        if task:
            # Runs at every version, including v0. With an empty rule set this
            # returns "no rule covers it" rather than a guess, so the baseline is
            # a real answer attempt instead of a disabled code path.
            structured, rule_hits = answer_task(
                str(task.get("type") or ""),
                prompt,
                dict(task.get("github") or {}),
                tool_calls,
                rules=playbook.rules,
            )
        return ActorTurn(
            text=_with_answer(final.text, structured),
            spans=spans,
            tool_calls=tool_calls,
            tokens=tokens,
            cost=cost,
            playbook_hits=hits,
            model=final.model,
            escalated=escalated,
            events=events,
            answer=structured,
            speed_ms=round((time.perf_counter() - started) * 1000, 1),
            rule_hits=rule_hits,
        )

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        result, _, _ = self._tool_hop(
            name,
            args or {},
            trace_id="adhoc",
            session_id="demo",
            hits=[],
            split=Split.DEV,
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
        split: Split = Split.DEV,
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
                "split": split.value,
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
        split: Split = Split.DEV,
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
                "split": split.value,
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
                "split": split.value,
            },
        )
        self.sink.emit(event)
        self.sink.emit_span(span)
        return span, event


def _should_use_tools(playbook: Playbook) -> bool:
    """Always. Tool access is granted, not learned.

    This used to return False for an empty playbook, which meant the v0 baseline
    was an agent forbidden from touching the third-party app — so every later
    gain was really just "tools got switched on". What the agent learns is which
    tools to reach for and in what order, and that shows up in the tool plan and
    in cost, not in whether it may call anything at all.
    """
    del playbook
    return True


def _playbook_hits(playbook: Playbook, prompt: str) -> list[str]:
    needle = prompt.lower()
    hits: list[str] = []
    for entry in playbook.entries:
        blob = f"{entry.id} {entry.text} {' '.join(entry.tags)}".lower()
        if not needle or any(token in blob for token in needle.split()[:6]) or entry.text:
            hits.append(entry.id)
    return hits[:8]


def _system_prompt(playbook: Playbook, skill_hits: list[Any], script_hits: list[Any] | None = None) -> str:
    parts = [entry.text for entry in playbook.entries if entry.text.strip()]
    for hit in skill_hits:
        parts.append(f"skill {hit.skill.name}: {hit.skill.body}")
    for script in script_hits or []:
        parts.append(f"script {script.name}: {script.body}")
    return "\n\n".join(parts) or "Answer the user."


def _messages(system: str, prompt: str, evidence: list[str]) -> list[dict[str, str]]:
    user = prompt
    if evidence:
        user = prompt + "\n\nRepo evidence:\n" + "\n".join(evidence[:8])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _plan_tools(
    question: str,
    owner: str,
    repo: str,
    task: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """One evidence plan for every ask, plus whatever the ask points at.

    This deliberately does not branch on `task["type"]`. A per-type tool list is
    the eval's shape written into Python: it makes the agent look competent on
    the five fixture task types and blind everywhere else. Instead every run
    fetches the same repo context and adds reads for the specific issue, pull
    request, or file the question names.
    """
    github = dict((task or {}).get("github") or {})
    base = {"owner": owner, "repo": repo}
    planned: list[tuple[str, dict[str, Any]]] = []
    issue_n = _first_int(github.get("issue_number"), _match(r"issue\s+#?(\d+)", question))
    if issue_n is not None:
        planned.append(("issue_read", {**base, "method": "get", "issue_number": issue_n}))
    pr_n = _first_int(github.get("pr_number"), _match(r"(?:pull request|pr)\s+#?(\d+)", question))
    if pr_n is not None:
        planned.append(("pull_request_read", {**base, "pull_number": pr_n}))
    path = str(github.get("path") or _match(r"([\w./-]+\.\w+)", question) or "")
    if path:
        planned.append(("get_file_contents", {**base, "path": path}))
    planned.extend(
        [
            ("get_file_contents", {**base, "path": "CONTRIBUTING.md"}),
            ("get_file_contents", {**base, "path": "CODEOWNERS"}),
            ("list_issues", {**base, "state": "all"}),
            ("list_pull_requests", {**base, "state": "all"}),
            ("list_label", dict(base)),
        ]
    )
    return _dedupe_plan(planned)


def _match(pattern: str, text: str) -> str:
    hit = re.search(pattern, text, re.I)
    return hit.group(1) if hit else ""


def _first_int(*values: Any) -> int | None:
    for value in values:
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _dedupe_plan(planned: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    seen: set[str] = set()
    out: list[tuple[str, dict[str, Any]]] = []
    for name, args in planned:
        key = f"{name}:{sorted(args.items())}"
        if key in seen:
            continue
        seen.add(key)
        out.append((name, args))
    return out


def _with_answer(text: str, structured: dict[str, Any]) -> str:
    extra = structured.get("text") if structured else ""
    if extra and extra not in text:
        return f"{text}\n{extra}"
    return text


def _has_payload(result: dict[str, Any]) -> bool:
    if result.get("found") is False:
        return False
    items = result.get("items") or result.get("issues") or result.get("labels")
    if isinstance(items, list):
        return bool(items)
    return bool(
        result.get("body")
        or result.get("title")
        or result.get("content")
        or result.get("full_name")
        or result.get("text")
    )


def _evidence_text(name: str, result: dict[str, Any]) -> str:
    return f"{name}: {result}"


def _relevant(question: str, result: dict[str, Any]) -> bool:
    """Keep a fetched result only if it shares a content word with the ask.

    The plan fetches the same repo context on every run, so without this filter
    an ask the repo has nothing to say about would still come back "grounded" in
    whatever issues happened to exist, and the agent would never answer "no
    evidence". Relevance is judged on retrieved values, not on task type.
    """
    asked = _content_tokens(question)
    if not asked:
        return True
    return bool(asked & _content_tokens(_value_blob(result)))


def _value_blob(value: Any, depth: int = 0) -> str:
    if depth > 4:
        return ""
    if isinstance(value, dict):
        return " ".join(_value_blob(item, depth + 1) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_value_blob(item, depth + 1) for item in value)
    if isinstance(value, bool) or value is None:
        return ""
    return str(value)


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if token not in _STOPWORDS and (len(token) > 2 or token.isdigit())
    }


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
