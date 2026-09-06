# Live smoke

Small-path proof that `--mode live` hits real Chat / GitHub MCP / Neatlogs IO. Same pipeline as offline; live branches only at those three hops. Keys stay in local `.env` and are not repeated here.

## Command

```bash
python -m journeyman.demo.run --challenge frozen --mode live --work-root /tmp/jm-live
```

Required env: `TMX_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`, `NEATLOGS_API_KEY`, `NEATLOGS_PROJECT_ID`, `NEATLOGS_BASE_URL=https://ingest.neatlogs.com`.

Live pytest (skipped by default): `pytest -m live`.

## Small-path transcript (2026-09-06, redacted)

```
keys TMX=set OAI=set GH=set NL=set PID=set
chat provider=cheap model=glm-4-7-flash offline=False chars=4 ms=3037
mcp found=True error=False title='API returns 500 on empty payload' session=True ms=4345
neatlogs last_status=200 trace_id=7a7def172bc1a6b861d098da2fd84a6b
neatlogs url=https://app.neatlogs.com/?trace_id=7a7def172bc1a6b861d098da2fd84a6b
probe ok
```

That is not an offline double: TensorMux returned live text, GitHub MCP readonly opened a session and read fixture issue #1, Neatlogs `POST /v1/trace` returned 200 and set `last_trace_id`.

## Frozen live (same keys, partial)

The full frozen CLI was started with `--mode live`. It completed Run1 + Reflect against the live fixture, then stalled on a later TensorMux hop while scoring the candidate. Killed; not claimed as a finished `render()` transcript.

```
Run1 DEV pass=0.0714 with weak playbook weak-0
Reflect merged 2 entries from 15 DEV-fail spans into cand-8edcb05c
Derived 1 rules from arjun7n9s/journeyman-fixture
Mined 10 rules from corpus soil: WHEN title contains ['flaky'] THEN add labels=priority:p1 cov=8 sup=8 lift=3.125
pointer active=weak-0 candidate=cand-8edcb05c
```

Hold-out was not scored (promote never finished). Chat hops now use `stream: false`, a 25s hard deadline, and 3 retries so one stall cannot freeze the CLI. Full frozen live is an optional overnight follow-up, not required to sign this gate.

## Default pytest

`82 passed, 2 skipped` — the two skips are `@pytest.mark.live` (keys absent in the default invocation). Prior baseline before the timeout tests was 79/2.
