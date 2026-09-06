# Journeyman

Journeyman is a self-improving agent workbench: it ingests execution traces, judges failures, synthesizes probes, proposes versioned patches under budget, verifies with exact replay, promotes under a sealed hold-out, then red-teams the LIVE version. It routes work cheap-first with `CostRouter.decide`, grows a local skill library (search-before-write), and enforces GitHub MCP readonly tools through versioned policy streams.

This package is the **source of truth**. `journeyman.contracts` is the only place shapes live. Mechanisms import those contracts. The root TypeScript/Vite tree is legacy mockups.

SuperviseCycle (pre-promote):

TraceIngest.poll → FailureJudge.diagnose → skip if not failure → CausalAnalyst.analyze → ProbeFactory.synthesize → resolve baseline → LiveScorer (aux) → PromptSurgeon.propose (candidate only) → LiveScorer aux candidate → ExactReplay.replay → persist postmortem

Promote uses Actor re-eval on frozen DEV plus a sealed hold-out (never a Run1 hold score). LiveScorer is aux inside the cycle only. RedTeam runs after promote on LIVE via `attack_live`. Ingest skips `session_id=="test"`, `prompt_variant=="candidate"`, `split=holdout`, and tool-child spans. The seen ring holds 500 ids.

## Layout

- `src/journeyman/contracts` — typed models, enums, constants
- `src/journeyman/runtime` — Actor, ContextGate, SuperviseCycle
- `src/journeyman/partners` — MCP, chat, ingest sink
- `playbooks/index.yaml` — harness list
- `journal/CORE.md` — durable-insight template
- `tests/` — contracts, cycle, sealed hold-out, frozen eval

## Develop

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m journeyman.demo.run --challenge frozen --mode offline
python -m journeyman.demo.run --challenge frozen --mode live
python -m journeyman.demo.run --rollback --work-root .
```

`--mode live` uses TensorMux/OpenAI HTTP, GitHub MCP readonly against `arjun7n9s/journeyman-fixture`, and Neatlogs ingest when those keys are in local `.env`. Offline shares the same pipeline and branches only at Chat / MCP / Neatlogs IO.

Open `ui/index.html` after a run (or the Vite shell, which reads `web/public/last-report.json`). The UI does not re-run the loop.

## Derive vs mine vs promote

- **Derive** reads CONTRIBUTING.md and CODEOWNERS and compiles documented `condition → outcome` lines into **ACTIVE** rules. Each rule cites a file and line. This is the honest floor: the workspace stating its own conventions.
- **Mine** reads issues labeled `corpus:mine` (via MCP / the offline fixture) and induces **CANDIDATE** rules: a title or body token → a label, with coverage / support / confidence / lift. Rules that clear those filters become **ACTIVE**. The miner never opens `corpus/HIDDEN.md`. Hold-out issues are unlabeled and never enter this soil.
- **Promote** is unchanged: Actor re-eval on frozen DEV is the signal; sealed hold-out runs only then (candidate vs prior); RedTeam runs after promote on LIVE.


