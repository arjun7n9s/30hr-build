"""Answer repo-triage asks from MCP evidence + learned rules.

Nothing here encodes the fixture's taxonomy. Two kinds of logic are allowed:

* **learned** — label and owner answers come from `Rule` objects the agent
  derived or mined from the workspace. With an empty rule set this module
  returns nothing for those asks, which is the honest v0 baseline.
* **protocol** — duplicate/fix_pr/summarize use conventions that belong to
  GitHub itself (`Closes #12`, issue numbering, title similarity), not to any
  particular repo. Those are generic and stay in code.

If you find yourself adding a repo's label name, area, or issue number to this
file, it belongs in a rule with evidence instead.
"""

from __future__ import annotations

import re
from typing import Any

from journeyman.contracts import Rule, RuleHit, RuleKind
from journeyman.rules import apply_rules, collect_evidence, issue_features, path_features
from journeyman.rules.features import Evidence

_CLOSES = re.compile(r"\b(?:closes|closed|close|fixes|fixed|fix|resolves|resolved)\s+#(\d+)\b", re.I)
_STOPWORDS = frozenset({"the", "and", "for", "this", "that", "with", "from", "when", "after", "into"})
_DUPLICATE_MIN_SCORE = 0.34
_FIX_PR_MIN_SCORE = 0.30


def answer_task(
    task_type: str,
    question: str,
    github: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    *,
    rules: list[Rule] | None = None,
) -> tuple[dict[str, Any], list[RuleHit]]:
    """Produce a structured answer plus the rules that fired producing it."""
    evidence = collect_evidence(tool_calls)
    rules = list(rules or [])
    if task_type == "label":
        return _label(github, evidence, rules, task_type)
    if task_type == "owner":
        return _owner(github, question, evidence, rules, task_type)
    if task_type == "duplicate":
        return _duplicate(github, evidence), []
    if task_type == "fix_pr":
        return _fix_pr(github, evidence), []
    if task_type == "summarize":
        return _summarize(github, evidence, rules, task_type)
    return {}, []


def _label(
    github: dict[str, Any],
    evidence: Evidence,
    rules: list[Rule],
    task_type: str,
) -> tuple[dict[str, Any], list[RuleHit]]:
    issue = _target_issue(github, evidence)
    if issue is None:
        return {}, []
    features = issue_features(issue, task_type=task_type)
    answer, hits = apply_rules(rules, features, kind=RuleKind.LABEL)
    labels = answer.get("labels") or []
    if not labels:
        # No rule covers this issue. Say so instead of guessing — an unsupported
        # guess that happens to be right teaches reflection the wrong lesson.
        return {"text": f"no label rule covers issue {issue.get('number')}"}, hits
    return {"labels": labels, "text": " ".join(labels)}, hits


def _owner(
    github: dict[str, Any],
    question: str,
    evidence: Evidence,
    rules: list[Rule],
    task_type: str,
) -> tuple[dict[str, Any], list[RuleHit]]:
    path = str(github.get("path") or _path_from(question) or "")
    if not path:
        return {"text": "no path in the ask"}, []
    features = path_features(path, task_type=task_type)
    answer, hits = apply_rules(rules, features, kind=RuleKind.OWNER)
    owner = (answer.get("owner") or [""])[0]
    if not owner:
        return {"text": f"no owner rule covers {path}"}, hits
    return {"owner": owner, "text": owner}, hits


def _duplicate(github: dict[str, Any], evidence: Evidence) -> dict[str, Any]:
    """Nearest existing issue by title overlap. Generic, not repo-specific."""
    target = _target_issue(github, evidence)
    if target is None:
        return {"text": "target issue not retrieved"}
    target_number = _as_int(target.get("number"))
    tokens = _issue_tokens(target)
    if not tokens:
        return {"text": "target issue has no text"}
    best: dict[str, Any] | None = None
    best_score = 0.0
    for other in evidence.issues:
        other_number = _as_int(other.get("number"))
        if other_number is None or other_number == target_number:
            continue
        score = _overlap(tokens, _issue_tokens(other))
        if score > best_score:
            best, best_score = other, score
    if best is None or best_score < _DUPLICATE_MIN_SCORE:
        return {"text": "no duplicate above threshold"}
    return {"duplicate_of": _as_int(best.get("number")), "text": str(best.get("title") or "")}


def _fix_pr(github: dict[str, Any], evidence: Evidence) -> dict[str, Any]:
    """`Closes #N` is GitHub's own linking convention; title overlap is the fallback."""
    issue_number = _as_int(github.get("issue_number"))
    if issue_number is not None:
        for pull in evidence.pulls:
            body = f"{pull.get('body') or ''}\n{pull.get('title') or ''}"
            if any(int(match) == issue_number for match in _CLOSES.findall(body)):
                return {"pr": _as_int(pull.get("number")), "text": str(pull.get("title") or "")}
    target = _target_issue(github, evidence)
    tokens = _tokens(str((target or {}).get("title") or ""))
    if not tokens:
        return {"text": "no linking PR found"}
    best: dict[str, Any] | None = None
    best_score = 0.0
    for pull in evidence.pulls:
        score = _overlap(tokens, _tokens(str(pull.get("title") or "")))
        if score > best_score:
            best, best_score = pull, score
    if best is None or best_score < _FIX_PR_MIN_SCORE:
        return {"text": "no linking PR found"}
    return {"pr": _as_int(best.get("number")), "text": str(best.get("title") or "")}


def _summarize(
    github: dict[str, Any],
    evidence: Evidence,
    rules: list[Rule],
    task_type: str,
) -> tuple[dict[str, Any], list[RuleHit]]:
    """Issues matching the asked-for labels, using rules where labels are absent."""
    wanted = [str(label) for label in (github.get("labels") or [])]
    state = str(github.get("state") or "")
    keys: list[str] = []
    hits: list[RuleHit] = []
    for issue in evidence.issues:
        if state and str(issue.get("state") or state) != state:
            continue
        features = issue_features(issue, task_type=task_type)
        inferred, fired = apply_rules(rules, features, kind=RuleKind.LABEL)
        known = {label.lower() for label in features.get("labels", [])}
        known.update(label.lower() for label in inferred.get("labels", []))
        if wanted and not {label.lower() for label in wanted} <= known:
            continue
        hits.extend(fired)
        number = _as_int(issue.get("number"))
        if number is not None:
            keys.append(str(number))
        key = str(issue.get("key") or "")
        if key:
            keys.append(key)
    unique = list(dict.fromkeys(keys))
    return {"keys": unique, "text": " ".join(unique)}, hits


def score_frozen(expected: dict[str, Any], output: str, answer: dict[str, Any] | None = None) -> bool:
    """Score one frozen case against the structured answer.

    Label and owner asks are scored on the structured answer only. Scanning the
    model's prose for the right tokens used to let a confident paragraph pass a
    task the agent never actually decided.
    """
    answer = answer or {}
    blob = f"{output} {answer}".lower()
    if expected.get("labels"):
        want = {str(label).lower() for label in expected["labels"]}
        got = {str(label).lower() for label in answer.get("labels") or []}
        return got == want
    if expected.get("owner"):
        return str(answer.get("owner") or "").strip().lower() == str(expected["owner"]).strip().lower()
    if expected.get("duplicate_of") is not None:
        return _ref_matches(answer.get("duplicate_of"), blob, expected["duplicate_of"], expected.get("duplicate_of_key"))
    if expected.get("pr") is not None:
        return _ref_matches(
            answer.get("pr"),
            blob,
            expected.get("pr_number") or expected.get("pr"),
            expected.get("pr_key"),
        )
    checks = (
        list(expected.get("must_mention") or [])
        + list(expected.get("must_mention_keys") or [])
        + list(expected.get("must_mention_if_open") or [])
        + list(expected.get("must_mention_if_open_keys") or [])
    )
    if not checks:
        return False
    got = {str(key).lower() for key in answer.get("keys") or []}
    return all(str(item).lower() in got for item in checks)


def _ref_matches(got: Any, blob: str, number: Any, key: Any) -> bool:
    if got is not None:
        if _as_int(got) is not None and _as_int(got) == _as_int(number):
            return True
        if key is not None and str(got).lower() == str(key).lower():
            return True
        return False
    if key is not None and str(key).lower() in blob:
        return True
    return number is not None and bool(re.search(rf"\b{re.escape(str(number))}\b", blob))


def _target_issue(github: dict[str, Any], evidence: Evidence) -> dict[str, Any] | None:
    hit = evidence.issue_by_number(github.get("issue_number"))
    if hit is not None:
        return hit
    title = str(github.get("issue_title") or "")
    if title:
        for issue in evidence.issues:
            if str(issue.get("title") or "").lower() == title.lower():
                return issue
    return None


def _path_from(question: str) -> str:
    match = re.search(r"\b((?:[\w.-]+/)+[\w.-]+\.\w+)\b", question)
    return match.group(1) if match else ""


def _issue_tokens(issue: dict[str, Any]) -> set[str]:
    """Title plus body. Two reports of the same defect rarely share a title."""
    return _tokens(f"{issue.get('title') or ''}\n{issue.get('body') or ''}")


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
