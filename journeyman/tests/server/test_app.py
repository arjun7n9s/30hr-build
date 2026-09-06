"""Thin HTTP wrapper tests. The loop itself is covered by demo tests."""

from __future__ import annotations

from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from journeyman.contracts import EvalResult, Playbook, VersionPointer  # noqa: E402
from journeyman.demo.run import DemoReport, SplitScore  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("JOURNEYMAN_WORK_ROOT", str(tmp_path))
    monkeypatch.setenv("JOURNEYMAN_MODE", "offline")
    from journeyman.server import app as server_app

    return TestClient(server_app.app)


def test_health(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["service"] == "journeyman"
    assert "TMX_API_KEY" in body["keys"]


def test_report_missing(client: TestClient) -> None:
    res = client.get("/api/report")
    assert res.status_code == 404


def test_run_calls_demo(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from journeyman.server import app as server_app

    called: dict[str, object] = {}

    def fake_run(challenge_id: str, *, work_root: Path, mode: str = "offline") -> DemoReport:
        called["challenge_id"] = challenge_id
        called["mode"] = mode
        called["work_root"] = work_root
        (work_root / "runs").mkdir(parents=True, exist_ok=True)
        score = SplitScore(pass_rate=1.0, successes=1, n=1, cost=0.0, tokens=0, turns=[], passed=[True])
        report = DemoReport(
            challenge_id=challenge_id,
            run1=score,
            run_n=score,
            hold_prior=None,
            hold_candidate=None,
            promoted=True,
            pointer=VersionPointer(active="cand-1"),
            eval_result=EvalResult(eval_id="t", baseline_pass_rate=0.2, candidate_pass_rate=1.0, n=1),
            journal_path=work_root / "journal" / "CORE.md",
            diff_path=work_root / "journal" / "candidate.diff",
            candidate_version="cand-1",
            mode=mode,
        )
        return report

    monkeypatch.setattr(server_app, "run_demo", fake_run)
    res = client.post("/api/run", json={"challenge_id": "frozen", "mode": "offline"})
    assert res.status_code == 200
    body = res.json()
    assert body["challenge_id"] == "frozen"
    assert body["promoted"] is True
    assert called["mode"] == "offline"


def test_run_rejects_bad_mode(client: TestClient) -> None:
    res = client.post("/api/run", json={"mode": "theater"})
    assert res.status_code == 400


def test_challenge_offline(client: TestClient) -> None:
    res = client.post(
        "/api/challenge",
        json={"prompt": "What labels should a flaky test issue get?", "task_type": "label"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "offline"
    assert body["result"]["prompt"]
    assert isinstance(body["result"]["text"], str)


def test_rollback(client: TestClient, tmp_path: Path) -> None:
    from journeyman.memory import MemoryStore

    memory = MemoryStore(tmp_path)
    memory.save_playbook(Playbook(version="weak-0", entries=[]))
    memory.save_playbook(Playbook(version="cand-1", entries=[]))
    memory.save_pointer(VersionPointer(active="cand-1", prior="weak-0"))
    res = client.post("/api/rollback")
    assert res.status_code == 200
    assert res.json()["pointer"]["active"] == "weak-0"
    assert res.json()["pointer"]["prior"] == "cand-1"
