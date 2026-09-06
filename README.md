# Journeyman

Journeyman is a self-improving agent workbench: it ingests execution traces, judges failures, synthesizes probes, proposes versioned patches under budget, verifies with exact replay + adversarial suites, routes work cheap-first with quality gates, grows a local skill library (search-before-write), and enforces tool calls through versioned policy streams with optional shadow arms — journaling durable insights across sessions.

**Source of truth is the Python package `journeyman/`.** Contracts, Actor, SuperviseCycle, CostRouter.decide, sealed hold-out, and the demo loop live there. Do not re-implement those types or gates in TypeScript.

## Layout

| Path | What it is |
|---|---|
| `journeyman/` | Product runtime: contracts, Actor, SuperviseCycle, demo CLI |
| `eval/` | Frozen DEV (10) / hold-out (6) on `arjun7n9s/journeyman-fixture` |
| `src/` `web/` `mockups/` | Legacy gather UI / static mockups — not a second learning loop |
| `architecture.md` | Locked loop + partner graph |
| `SPEC.md` | Task family, policy, metrics |
| `plans/` | Briefs and research |

## Runtime (Python)

```bash
cd journeyman
python -m pip install -e ".[dev]"
python -m pytest
python -m journeyman.demo.run
python -m journeyman.demo.run --challenge github_triage_v1
```

Mechanisms import shapes from `journeyman.contracts` only. Keys stay in local `.env`.

## Legacy gather UI

The root TypeScript/Vite tree is parked as mockups. It must not grow a parallel CostRouter or SuperviseCycle. Optional later: a thin UI that shells out to `python -m journeyman.demo.run`.
