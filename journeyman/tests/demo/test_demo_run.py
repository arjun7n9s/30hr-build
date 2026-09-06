"""Offline demo runner: Run1 weak → cycle → RunN better/cheaper."""

from pathlib import Path

from journeyman.demo.run import run_demo


def test_demo_runner_offline_improves(tmp_path: Path) -> None:
    report = run_demo("github_triage_v1", work_root=tmp_path, offline=True)
    assert report.run1.pass_rate < report.run_n.pass_rate
    assert report.run_n.pass_rate == 1.0
    assert report.run_n.cost <= report.run1.cost
    assert report.promoted is True
    assert report.pointer.active != "weak-0"
    assert report.journal_path.exists()
    assert report.diff_path.exists()
    assert "Run1" in report.journal_path.read_text(encoding="utf-8")
    assert report.eval_result.delta is not None
    assert report.eval_result.delta > 0
    assert report.eval_result.wilson_low is not None
