"""Prompt surgeon — candidate versions only; never auto-promote."""

from __future__ import annotations

import difflib

from journeyman.contracts import Stage, VersionRecord, VersionStatus, WorkItem


class PromptSurgeon:
    def propose(self, item: WorkItem) -> WorkItem:
        assert item.verdict is not None
        baseline = item.baseline_prompt or ""
        fix = (item.root_cause.fix_strategy if item.root_cause else "") or item.verdict.expected_behavior
        rule = f"\n\nRule: {fix}. Do not invent facts when tools return nothing."
        candidate = (baseline + rule).strip()
        item.candidate_prompt = candidate
        item.prompt_diff = "\n".join(
            difflib.unified_diff(
                baseline.splitlines(),
                candidate.splitlines(),
                fromfile="current",
                tofile="candidate",
                lineterm="",
            )
        )
        version = f"cand-{item.span.span_id[:8]}"
        item.candidate_prompt_version = version
        VersionRecord(version=version, parent=None, notes="candidate only", status=VersionStatus.CANDIDATE)
        item.stage = Stage.PATCHED
        return item
