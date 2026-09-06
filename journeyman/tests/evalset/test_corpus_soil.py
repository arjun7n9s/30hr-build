"""Mining soil: unlabeled eval, labeled corpus, hidden convention stays out of Python."""

from __future__ import annotations

import json
import re
from pathlib import Path

from journeyman.evalset.frozen import load_frozen_eval, repo_root


def _hidden_marker() -> str:
    text = (repo_root() / "corpus" / "HIDDEN.md").read_text(encoding="utf-8")
    match = re.search(r"^marker:\s*(\S+)", text, re.M)
    assert match, "corpus/HIDDEN.md must declare marker: <token>"
    return match.group(1)


def test_hidden_convention_not_hardcoded() -> None:
    marker = _hidden_marker()
    root = Path(__file__).resolve().parents[2] / "src" / "journeyman"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "evalset" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(re.escape(marker), text, re.I):
            rel = path.relative_to(root).as_posix()
            offenders.append(rel)
    assert not offenders, f"hidden marker {marker!r} baked into {offenders}"


def test_hidden_file_is_not_in_the_offline_snapshot() -> None:
    challenge = load_frozen_eval()
    paths = {str(row.get("path")) for row in challenge.github.get("files") or []}
    assert "corpus/HIDDEN.md" not in paths
    assert "CONTRIBUTING.md" in paths


def test_manifest_expects_p1_and_counts() -> None:
    manifest = json.loads((repo_root() / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["expects_p1"] == ["dev-13", "dev-14", "hold-07"]
    assert manifest["counts"]["labeled_documented"] >= 20
    assert manifest["counts"]["labeled_hidden"] >= 8
    labeled = [row for row in manifest["examples"] if row["role"] == "corpus"]
    assert all(row["ref"].startswith("issue:") for row in labeled)
    assert all(row["intended_labels"] for row in labeled)


def test_eval_extras_are_unlabeled_in_the_snapshot() -> None:
    challenge = load_frozen_eval()
    by_number = {int(row["number"]): row for row in challenge.github["issues"]}
    for case in challenge.dev + challenge.held_out:
        number = case.github.get("issue_number")
        if number is None:
            continue
        issue = by_number[int(number)]
        names = [
            str(label.get("name") if isinstance(label, dict) else label)
            for label in issue.get("labels") or []
        ]
        assert names == [], f"{case.id} issue #{number} must be unlabeled, got {names}"


def test_corpus_issues_are_labeled_in_the_snapshot() -> None:
    challenge = load_frozen_eval()
    corpus = [
        row
        for row in challenge.github["issues"]
        if any(
            (label.get("name") if isinstance(label, dict) else label) == "corpus:mine"
            for label in row.get("labels") or []
        )
    ]
    assert len(corpus) >= 28
    hidden_labeled = [row for row in corpus if _hidden_marker().lower() in str(row.get("title") or "").lower()]
    assert len(hidden_labeled) >= 8


def test_holdout_stays_sealed() -> None:
    hold = json.loads((repo_root() / "eval" / "holdout.json").read_text(encoding="utf-8"))
    assert hold.get("sealed") is True
    ids = {task["id"] for task in hold["tasks"]}
    assert "hold-07" in ids
