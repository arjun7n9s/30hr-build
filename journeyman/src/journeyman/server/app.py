"""FastAPI wrapper — exposes journeyman.demo.run over HTTP.

GET  /api/health     — liveness + which partner keys are present
GET  /api/report     — latest runs/last.json
POST /api/run        — full frozen loop (offline|live)
POST /api/challenge  — one freeform task through the active playbook
POST /api/rollback   — restore the prior version pointer
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from journeyman.contracts import Playbook, PlaybookEntry, Split
from journeyman.demo.artifacts import report_dict
from journeyman.demo.run import run_demo
from journeyman.evalset.frozen import load_frozen_eval
from journeyman.memory import MemoryStore
from journeyman.partners.chat import ChatClient
from journeyman.partners.mcp import GithubMcp
from journeyman.runtime.actor import Actor
from journeyman.spend import CostRouter, load_local_env

load_local_env()


def _work_root() -> Path:
    return Path(os.environ.get("JOURNEYMAN_WORK_ROOT", ".tmp-ui")).resolve()


def _default_mode() -> str:
    return os.environ.get("JOURNEYMAN_MODE", "offline")


app = FastAPI(title="Journeyman API", version="0.1.0")
_origins_env = os.environ.get("CORS_ORIGINS", "*")
_origins = ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChallengeIn(BaseModel):
    prompt: str
    task_type: str | None = None
    target: str | None = None
    body: str | None = None


class RunIn(BaseModel):
    challenge_id: str = "frozen"
    mode: str | None = None


def _serialize_turn(turn: Any, prompt: str, task_type: str | None) -> dict[str, Any]:
    spans_out: list[dict[str, Any]] = []
    for span in turn.spans or []:
        raw = getattr(span, "raw", {}) or {}
        kind = getattr(span, "span_kind", "")
        spans_out.append(
            {
                "name": getattr(span, "name", "span"),
                "kind": kind.value if hasattr(kind, "value") else str(kind),
                "duration_ms": raw.get("duration_ms") or raw.get("latency_ms") or 0,
                "tokens": raw.get("tokens") or 0,
                "cost": raw.get("cost") or 0.0,
                "model": raw.get("model") or "",
                "route": raw.get("route") or "",
                "input": raw.get("input"),
                "output": raw.get("output") or raw.get("result"),
            }
        )
    return {
        "prompt": prompt,
        "task_type": task_type,
        "answer": turn.answer or {"text": turn.text},
        "text": turn.text,
        "tokens": turn.tokens,
        "cost": turn.cost,
        "speed_ms": turn.speed_ms,
        "tool_calls": len(turn.tool_calls or []),
        "playbook_hits": turn.playbook_hits or [],
        "rule_hits": [
            {"rule_id": getattr(hit, "rule_id", ""), "why": getattr(hit, "why", "")}
            for hit in (turn.rule_hits or [])
        ],
        "escalated": bool(turn.escalated),
        "model": turn.model,
        "spans": spans_out,
    }


def _load_report_dict() -> dict[str, Any] | None:
    root = _work_root()
    for candidate in (root / "runs" / "last.json", root / "last.json"):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def _active_playbook() -> Playbook:
    memory = MemoryStore(_work_root())
    pointer = memory.load_pointer()
    if pointer is not None:
        playbook = memory.load_playbook(pointer.active)
        if playbook is not None:
            return playbook
    return Playbook(
        version="weak-0",
        entries=[
            PlaybookEntry(
                id="helpful",
                text="Be helpful and confident. Guess if you are unsure.",
                tags=["weak"],
            )
        ],
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "journeyman",
        "work_root": str(_work_root()),
        "default_mode": _default_mode(),
        "keys": {
            "TMX_API_KEY": bool(os.environ.get("TMX_API_KEY")),
            "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
            "GITHUB_TOKEN": bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")),
            "NEATLOGS_API_KEY": bool(os.environ.get("NEATLOGS_API_KEY")),
        },
    }


@app.get("/api/report")
def report() -> dict[str, Any]:
    data = _load_report_dict()
    if data is None:
        raise HTTPException(status_code=404, detail="no report yet — POST /api/run first")
    return data


@app.post("/api/run")
def run(body: RunIn) -> dict[str, Any]:
    mode = body.mode or _default_mode()
    if mode not in {"offline", "live"}:
        raise HTTPException(status_code=400, detail="mode must be 'offline' or 'live'")
    started = time.perf_counter()
    demo_report = run_demo(body.challenge_id, work_root=_work_root(), mode=mode)
    payload = report_dict(demo_report)
    payload["_run_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return payload


@app.post("/api/challenge")
def challenge(body: ChallengeIn) -> dict[str, Any]:
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    frozen = load_frozen_eval()
    playbook = _active_playbook()
    live = _default_mode() == "live" and bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    actor = Actor(
        chat=ChatClient(offline=not live),
        github=GithubMcp(frozen.github, offline=not live),
        router=CostRouter(),
        repo=frozen.repo,
    )
    task: dict[str, Any] = {}
    if body.task_type:
        task["type"] = body.task_type
    if body.target:
        task["target"] = body.target
    if body.body:
        task["body"] = body.body
        task.setdefault("github", {})["body"] = body.body

    session_id = f"challenge-{uuid.uuid4().hex[:8]}"
    turn = actor.run(prompt, playbook=playbook, session_id=session_id, split=Split.DEV, task=task or None)
    return {
        "session_id": session_id,
        "playbook_version": playbook.version,
        "mode": "live" if live else "offline",
        "result": _serialize_turn(turn, prompt, body.task_type),
    }


@app.post("/api/rollback")
def rollback() -> dict[str, Any]:
    memory = MemoryStore(_work_root())
    try:
        restored = memory.rollback()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    data = _load_report_dict()
    if data is not None:
        data.setdefault("pointer", {})
        data["pointer"]["active"] = restored.active
        data["pointer"]["prior"] = restored.prior
        data["pointer"]["candidate"] = restored.candidate
        data["promoted"] = False
        target = _work_root() / "runs" / "last.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "pointer": {
            "active": restored.active,
            "prior": restored.prior,
            "candidate": restored.candidate,
        },
    }
