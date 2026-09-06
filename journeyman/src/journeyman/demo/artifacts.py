"""Serialize a demo run for the artifact UI. Not a second loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from journeyman.demo.ui import write_ui


def score_dict(score: Any | None) -> dict[str, Any] | None:
    if score is None:
        return None
    return {
        "pass_rate": score.pass_rate,
        "successes": score.successes,
        "n": score.n,
        "cost": score.cost,
        "tokens": score.tokens,
        "split": score.split.value if hasattr(score.split, "value") else str(score.split),
        "passed": list(score.passed),
    }


def report_dict(report: Any) -> dict[str, Any]:
    pointer = report.pointer
    return {
        "challenge_id": report.challenge_id,
        "mode": report.mode,
        "promoted": report.promoted,
        "run1": score_dict(report.run1),
        "run_n": score_dict(report.run_n),
        "hold_prior": score_dict(report.hold_prior),
        "hold_candidate": score_dict(report.hold_candidate),
        "pointer": {
            "active": pointer.active,
            "candidate": pointer.candidate,
            "prior": pointer.prior,
        },
        "candidate_version": report.candidate_version,
        "eval": {
            "wilson_low": report.eval_result.wilson_low,
            "wilson_high": report.eval_result.wilson_high,
            "delta": report.eval_result.delta,
        },
        "neatlogs_trace_id": report.neatlogs_trace_id,
        "neatlogs_url": report.neatlogs_url,
        "journal_path": str(report.journal_path),
        "diff_path": str(report.diff_path),
        "report_path": str(report.report_path) if report.report_path else "",
        "ui_path": str(report.ui_path) if report.ui_path else "",
        "journal": report.journal_text,
        "diff": report.diff_text,
        "playbook_entries": report.playbook_entries,
        "redteam": report.redteam,
        "children": report.children,
        "repo": report.repo,
    }


def write_artifacts(report: Any, work_root: Path) -> tuple[Path, Path]:
    payload = report_dict(report)
    runs = work_root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    report_path = runs / "last.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    ui_path = write_ui(payload, work_root / "ui" / "index.html")
    vite = _vite_public(work_root)
    if vite is not None:
        vite.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report.report_path = report_path
    report.ui_path = ui_path
    return report_path, ui_path


def _vite_public(work_root: Path) -> Path | None:
    for base in (work_root.resolve(), Path.cwd().resolve(), *list(Path.cwd().resolve().parents)[:3]):
        if (base / "web" / "src" / "App.tsx").exists():
            public = base / "web" / "public"
            public.mkdir(parents=True, exist_ok=True)
            return public / "last-report.json"
    return None
