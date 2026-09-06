# Journeyman

Journeyman is a self-improving agent workbench: it ingests execution traces, judges failures, synthesizes probes, proposes versioned patches under budget, verifies with exact replay, promotes under a sealed hold-out, then red-teams the LIVE version. It routes work cheap-first with `CostRouter.decide`, grows a local skill library (search-before-write), and enforces GitHub MCP readonly tools through versioned policy streams.

This package is the **source of truth**. `journeyman.contracts` is the only place shapes live. Mechanisms import those contracts. The root TypeScript/Vite tree is legacy mockups.

SuperviseCycle (pre-promote):

TraceIngest.poll → FailureJudge.diagnose → skip if not failure → CausalAnalyst.analyze → ProbeFactory.synthesize → resolve baseline → LiveScorer.run_baseline → PromptSurgeon.propose (candidate only) → LiveScorer.run_candidate → ExactReplay.replay → persist postmortem

Promote uses Eval DEV plus a sealed hold-out (never a Run1 hold score). RedTeam runs after promote on LIVE. Ingest skips `session_id=="test"`, `prompt_variant=="candidate"`, `split=holdout`, and tool-child spans. The seen ring holds 500 ids.

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
python -m journeyman.demo.run
python -m journeyman.demo.run --challenge github_triage_v1
```
