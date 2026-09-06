"""The tool plan is generic: same core fetch regardless of task type."""

import inspect
from typing import Any

from journeyman.runtime import actor as actor_module
from journeyman.runtime.actor import _plan_tools

_CORE = {
    ("get_file_contents", "CONTRIBUTING.md"),
    ("get_file_contents", "CODEOWNERS"),
    ("list_issues", "all"),
    ("list_pull_requests", "all"),
    ("list_label", ""),
}


def _plan(task: dict[str, Any] | None, question: str = "who owns this?") -> list[tuple[str, dict[str, Any]]]:
    return _plan_tools(question, "demo", "widget", task)


def _core_of(plan: list[tuple[str, dict[str, Any]]]) -> set[tuple[str, str]]:
    return {(name, str(args.get("path") or args.get("state") or "")) for name, args in plan} & _CORE


def test_every_task_type_shares_the_same_core_plan() -> None:
    tasks: list[dict[str, Any] | None] = [
        {"type": "label", "github": {}},
        {"type": "owner", "github": {}},
        {"type": "summarize", "github": {}},
        None,
    ]
    cores = [_core_of(_plan(task)) for task in tasks]
    assert all(core == _CORE for core in cores)


def test_issue_number_adds_an_issue_read() -> None:
    plan = _plan({"type": "label", "github": {"issue_number": 12}})
    assert ("issue_read", {"owner": "demo", "repo": "widget", "method": "get", "issue_number": 12}) in plan
    assert _core_of(plan) == _CORE


def test_issue_number_in_the_question_adds_an_issue_read() -> None:
    plan = _plan(None, "what labels belong on issue #7?")
    assert any(name == "issue_read" and args["issue_number"] == 7 for name, args in plan)


def test_pr_number_adds_a_pull_request_read() -> None:
    plan = _plan({"type": "fix_pr", "github": {"pr_number": 4}})
    assert any(name == "pull_request_read" and args["pull_number"] == 4 for name, args in plan)


def test_path_adds_a_file_read_for_that_path() -> None:
    plan = _plan({"type": "owner", "github": {"path": "src/api/routes.py"}})
    assert ("get_file_contents", {"owner": "demo", "repo": "widget", "path": "src/api/routes.py"}) in plan
    assert _core_of(plan) == _CORE


def test_plan_is_deduped() -> None:
    plan = _plan({"type": "owner", "github": {"path": "CODEOWNERS"}})
    keys = [(name, tuple(sorted(args.items()))) for name, args in plan]
    assert len(keys) == len(set(keys))


def test_no_per_task_type_planner_remains() -> None:
    assert not hasattr(actor_module, "_plan_for_task")
    assert "_plan_for_task" not in inspect.getsource(actor_module)
