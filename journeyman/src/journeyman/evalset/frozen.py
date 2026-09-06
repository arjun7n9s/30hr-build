"""Frozen DEV/hold-out eval + MCP fixture world for arjun7n9s/journeyman-fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from journeyman.contracts import Playbook, PlaybookEntry, Split
from journeyman.demo.challenge import Challenge, ChallengeCase

REPO = "arjun7n9s/journeyman-fixture"

ISSUE_TITLES: dict[str, str] = {
    "I1": "API returns 500 on empty payload",
    "I2": "Add invoice PDF export",
    "I3": "README typo in install section",
    "I4": "Runtime worker leaks memory after 2h",
    "I5": "Crash loop on nil context",
    "I6": "Dark mode toggle",
    "I7": "Charge webhook retries twice",
    "I8": "Document env vars",
    "I9": "API returns 500 when body is empty",
    "I10": "Worker OOM after long run",
    "I11": "OpenAPI spec missing 400 examples",
    "I12": "Billing cron double-charges on retry",
    "I13": "Add CSV export for invoices",
    "I14": "Panic in worker when ctx canceled",
    "I15": "Fix typo in contributing guide",
    "I16": "UI button misaligned on settings",
    "I17": "REST handler 500 on null JSON",
    "I18": "Rate limit headers not documented",
}

PR_META: dict[str, dict[str, str]] = {
    "P1": {"title": "Fix empty payload 500 in API", "closes": "I1"},
    "P2": {"title": "Cap runtime worker memory", "closes": "I4"},
    "P3": {"title": "Idempotent billing webhook", "closes": "I7"},
    "P4": {"title": "Settings page layout", "closes": ""},
}

CODEOWNERS = """\
src/api/ api
src/billing/ billing
src/runtime/ runtime
src/ui/ ui
"""


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "eval" / "dev.json").exists():
            return parent
    return here.parents[4]


def load_frozen_eval() -> Challenge:
    root = repo_root()
    dev_path = root / "eval" / "dev.json"
    hold_path = root / "eval" / "holdout.json"
    numbers_path = root / "eval" / "numbers.json"
    dev = json.loads(dev_path.read_text(encoding="utf-8"))
    hold = json.loads(hold_path.read_text(encoding="utf-8"))
    numbers = json.loads(numbers_path.read_text(encoding="utf-8")) if numbers_path.exists() else {}
    repo = str(dev.get("repo") or hold.get("repo") or REPO)
    snapshot = build_world(numbers)
    weak = Playbook(
        version="weak-0",
        empty=True,
        entries=[
            PlaybookEntry(
                id="helpful",
                text="Be helpful and confident. Guess if you are unsure.",
                tags=["weak"],
                version="0",
            )
        ],
    )
    return Challenge(
        id="frozen",
        title="Frozen GitHub triage eval",
        prompt="Answer only from retrieved repository evidence. If evidence is missing, say so.",
        success_metric="eval JSON expected fields",
        repo=repo,
        weak_playbook=weak,
        dev=_frozen_cases(dev.get("tasks") or [], Split.DEV),
        held_out=_frozen_cases(hold.get("tasks") or [], Split.HOLDOUT),
        github=snapshot,
        path=dev_path,
    )


def build_world(numbers: dict[str, Any] | None = None) -> dict[str, Any]:
    issue_nums = dict((numbers or {}).get("issues") or {})
    pr_nums = dict((numbers or {}).get("prs") or {})
    issues = []
    for key, title in ISSUE_TITLES.items():
        number = int(issue_nums.get(key) or key[1:])
        issues.append(
            {
                "key": key,
                "number": number,
                "title": title,
                "body": title,
                "labels": [],
                "state": "open",
            }
        )
    pulls = []
    for key, meta in PR_META.items():
        number = int(pr_nums.get(key) or (18 + int(key[1:])))
        closes = meta.get("closes") or ""
        closes_n = int(issue_nums.get(closes) or (closes[1:] if closes else 0) or 0)
        body = f"Closes #{closes_n}" if closes_n else meta["title"]
        pulls.append(
            {
                "key": key,
                "number": number,
                "title": meta["title"],
                "body": body,
                "closes": closes,
                "merged": False,
                "state": "open",
            }
        )
    files = [
        {"path": "CODEOWNERS", "content": CODEOWNERS},
        {"path": "src/billing/charge.py", "content": "# billing\n"},
        {"path": "src/runtime/worker.py", "content": "# runtime\n"},
        {"path": "src/ui/app.tsx", "content": "// ui\n"},
        {"path": "src/api/handler.py", "content": "# api\n"},
        {"path": "src/retry.py", "content": "MAX_RETRY = 3\n"},
    ]
    labels = [
        {"name": "area:api"},
        {"name": "area:billing"},
        {"name": "area:runtime"},
        {"name": "area:ui"},
        {"name": "type:bug"},
        {"name": "type:feat"},
        {"name": "type:docs"},
        {"name": "priority:p0"},
    ]
    return {
        "repo": REPO,
        "issues": issues,
        "pulls": pulls,
        "files": files,
        "labels": labels,
        "commits": [{"sha": "abc1234", "message": "seed"}],
        "branches": ["main"],
    }


def _frozen_cases(tasks: list[Any], split: Split) -> list[ChallengeCase]:
    cases: list[ChallengeCase] = []
    for row in tasks:
        expected_obj = dict(row.get("expected") or {})
        cases.append(
            ChallengeCase(
                id=str(row["id"]),
                question=str(row.get("prompt") or ""),
                expected=_keyword_hint(expected_obj),
                split=split,
                task_type=str(row.get("type") or ""),
                github=dict(row.get("github") or {}),
                expected_obj=expected_obj,
            )
        )
    return cases


def _keyword_hint(expected: dict[str, Any]) -> str:
    if expected.get("labels"):
        return " ".join(str(x) for x in expected["labels"])
    if expected.get("owner"):
        return str(expected["owner"])
    if expected.get("duplicate_of") is not None:
        return str(expected["duplicate_of"])
    if expected.get("pr") is not None:
        return str(expected.get("pr_number") or expected["pr"])
    keys = expected.get("must_mention") or expected.get("must_mention_keys") or []
    return " ".join(str(x) for x in keys)
