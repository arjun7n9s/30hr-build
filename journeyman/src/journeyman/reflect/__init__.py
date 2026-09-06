"""Reflect: DEV-fail spans → retrieved PlaybookEntry list → merge/supersede."""

from __future__ import annotations

import math
from typing import Any

from journeyman.contracts import JournalEntry, JournalKind, Playbook, PlaybookEntry, Stage
from journeyman.ingest import NullTraceSink, TraceSink
from journeyman.journal import JournalStore
from journeyman.partners.chat import ChatClient
from journeyman.partners.sink import emit_node
from journeyman.spend import CostRouter


class Reflect:
    def merge(
        self,
        current: Playbook,
        incoming: list[PlaybookEntry],
        *,
        sink: TraceSink | None = None,
        version: str | None = None,
    ) -> Playbook:
        by_id = {entry.id: entry for entry in current.entries}
        superseded: list[str] = []
        for entry in incoming:
            if entry.id in by_id:
                superseded.append(entry.id)
            by_id[entry.id] = entry
        next_version = version or (incoming[0].version if incoming else current.version)
        merged = Playbook(version=next_version, entries=list(by_id.values()), empty=len(by_id) == 0)
        emit_node(
            sink or NullTraceSink(),
            "Reflect",
            title="merge",
            stage=Stage.PATCHED,
            detail=next_version,
            payload={"superseded": superseded, "n": len(merged.entries)},
        )
        return merged

    def from_failures(
        self,
        current: Playbook,
        failure_spans: list[Any],
        *,
        version: str,
        candidate_prompt: str = "",
        chat: ChatClient | None = None,
        router: CostRouter | None = None,
        sink: TraceSink | None = None,
        journal: JournalStore | None = None,
    ) -> Playbook:
        """Build a candidate playbook from DEV failure spans. Never reads hold-out."""
        sink = sink or NullTraceSink()
        chat = chat or ChatClient(offline=True)
        router = router or CostRouter()
        query = _failure_query(failure_spans)
        retrieved = self.retrieve(query, current.entries, chat=chat, router=router, sink=sink)
        incoming = _entries_from_failures(
            failure_spans,
            candidate_prompt=candidate_prompt,
            retrieved=retrieved,
            version=version,
        )
        emit_node(
            sink,
            "Reflect",
            title="from_failures",
            stage=Stage.PATCHED,
            detail=version,
            payload={"failures": len(failure_spans), "incoming": len(incoming), "query": query[:200]},
        )
        merged = self.merge(current, incoming, sink=sink, version=version)
        if journal is not None:
            journal.persist_lesson(
                JournalEntry(
                    id=f"reflect-{version}",
                    kind=JournalKind.LESSON,
                    text=(
                        f"Reflect merged {len(incoming)} entries from {len(failure_spans)} DEV-fail spans "
                        f"into {version}. Retrieved: {', '.join(e.id for e in retrieved) or 'none'}."
                    ),
                    session_id="reflect",
                    version=version,
                )
            )
        return merged

    def retrieve(
        self,
        query: str,
        entries: list[PlaybookEntry],
        *,
        chat: ChatClient,
        router: CostRouter,
        sink: TraceSink | None = None,
    ) -> list[PlaybookEntry]:
        """RAG via embed_route when an embeddings key is present; keyword fallback otherwise."""
        decision = router.embed_route()
        emit_node(
            sink or NullTraceSink(),
            "Router",
            title="embed",
            detail=decision.model,
            payload={"path": "embed", "node": "Reflect"},
        )
        turn = chat.embed(query)
        vector = _embedding(turn.raw)
        if vector and entries and not chat.offline:
            scored: list[tuple[float, PlaybookEntry]] = []
            for entry in entries:
                other = _embedding(chat.embed(entry.text[:800]).raw)
                scored.append((_cosine(vector, other) if other else 0.0, entry))
            scored.sort(key=lambda row: row[0], reverse=True)
            hits = [entry for score, entry in scored if score > 0][:5]
            if hits:
                return hits
        return _keyword_rank(query, entries)


def _failure_query(spans: list[Any]) -> str:
    parts: list[str] = []
    for span in spans[:12]:
        parts.append(getattr(span, "input_text", "") or "")
        parts.append(getattr(span, "output_text", "") or "")
    return " ".join(parts)[:2000]


def _entries_from_failures(
    spans: list[Any],
    *,
    candidate_prompt: str,
    retrieved: list[PlaybookEntry],
    version: str,
) -> list[PlaybookEntry]:
    lessons: list[str] = []
    for span in spans[:8]:
        asked = str(getattr(span, "input_text", "") or "")[:160]
        got = str(getattr(span, "output_text", "") or "")[:120]
        if asked:
            lessons.append(f"When asked `{asked}` do not invent. Failed with `{got}`. Cite tools. If missing, say so.")
    evidence = candidate_prompt.strip() or (
        "Answer only from retrieved GitHub evidence. Cite the tool. If evidence is missing, say so."
    )
    taxonomy = (
        "Infer area:/type:/priority: from retrieved issue titles and bodies. "
        "Use issue_read, list_issues, list_label, search_code. Never invent labels."
    )
    if lessons:
        evidence = evidence + "\n" + "\n".join(lessons[:6])
    incoming = [
        PlaybookEntry(id="candidate-rule", text=evidence, tags=["candidate", "evidence"], version=version),
        PlaybookEntry(id="taxonomy", text=taxonomy, tags=["taxonomy"], version=version),
    ]
    for entry in retrieved:
        if entry.id in {"candidate-rule", "taxonomy"}:
            continue
        incoming.append(
            PlaybookEntry(
                id=entry.id,
                text=entry.text,
                tags=list(entry.tags) + ["retrieved"],
                version=version,
            )
        )
    return incoming


def _keyword_rank(query: str, entries: list[PlaybookEntry]) -> list[PlaybookEntry]:
    tokens = {token for token in query.lower().split() if len(token) > 3}
    if not tokens:
        return list(entries)[:5]
    ranked: list[tuple[int, PlaybookEntry]] = []
    for entry in entries:
        blob = f"{entry.id} {entry.text} {' '.join(entry.tags)}".lower()
        ranked.append((sum(1 for token in tokens if token in blob), entry))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [entry for score, entry in ranked if score > 0][:5] or list(entries)[:5]


def _embedding(raw: dict[str, Any]) -> list[float] | None:
    data = raw.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        vec = data[0].get("embedding")
        if isinstance(vec, list) and vec:
            return [float(x) for x in vec]
    vec = raw.get("embedding")
    if isinstance(vec, list) and vec:
        return [float(x) for x in vec]
    return None


def _cosine(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n == 0:
        return 0.0
    dot = sum(left[i] * right[i] for i in range(n))
    a = math.sqrt(sum(left[i] * left[i] for i in range(n)))
    b = math.sqrt(sum(right[i] * right[i] for i in range(n)))
    if a == 0 or b == 0:
        return 0.0
    return dot / (a * b)
