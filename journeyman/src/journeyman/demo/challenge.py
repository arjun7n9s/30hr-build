"""Load challenge fixtures for the demo runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from journeyman.contracts import Playbook, PlaybookEntry, Split


@dataclass
class ChallengeCase:
    id: str
    question: str
    expected: str
    split: Split
    task_type: str = ""
    github: dict[str, Any] = field(default_factory=dict)
    expected_obj: dict[str, Any] = field(default_factory=dict)


@dataclass
class Challenge:
    id: str
    title: str
    prompt: str
    success_metric: str
    repo: str
    weak_playbook: Playbook
    dev: list[ChallengeCase]
    held_out: list[ChallengeCase]
    github: dict[str, Any]
    path: Path


def challenges_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "fixtures" / "challenges"


def load_challenge(challenge_id: str, directory: Path | None = None) -> Challenge:
    folder = directory or challenges_dir()
    path = folder / f"{challenge_id}.yaml"
    if not path.exists():
        path = folder / f"{challenge_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"challenge not found: {challenge_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    weak_raw = data.get("weak_playbook") or {}
    entries = [
        PlaybookEntry(
            id=str(row.get("id")),
            text=str(row.get("text") or ""),
            tags=list(row.get("tags") or []),
            version=str(row.get("version") or "0"),
        )
        for row in (weak_raw.get("entries") or [])
    ]
    weak = Playbook(
        version=str(weak_raw.get("version") or "weak-0"),
        entries=entries,
        empty=bool(weak_raw.get("empty", True)),
    )
    return Challenge(
        id=str(data["id"]),
        title=str(data.get("title") or data["id"]),
        prompt=str(data.get("prompt") or ""),
        success_metric=str(data.get("success_metric") or ""),
        repo=str(data.get("repo") or "demo/widget"),
        weak_playbook=weak,
        dev=_cases(data.get("dev") or [], Split.DEV),
        held_out=_cases(data.get("held_out") or [], Split.HOLDOUT),
        github=dict(data.get("github") or {}),
        path=path,
    )


def _cases(rows: list[Any], split: Split) -> list[ChallengeCase]:
    cases: list[ChallengeCase] = []
    for row in rows:
        cases.append(
            ChallengeCase(
                id=str(row["id"]),
                question=str(row["question"]),
                expected=str(row["expected"]),
                split=split,
            )
        )
    return cases
