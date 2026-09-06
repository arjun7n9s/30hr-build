# Journeyman

Journeyman is a self-improving agent workbench: it ingests execution traces, judges failures, synthesizes probes, proposes versioned patches under budget, verifies with exact replay + adversarial suites, routes work cheap-first with quality gates, grows a local skill library (search-before-write), and enforces tool calls through versioned policy streams with optional shadow arms — journaling durable insights across sessions.

## Layout

| Path | What it is |
|---|---|
| `journeyman/` | Step 1 product: typed contracts + mechanism stubs |
| `eval/` | Frozen DEV / hold-out task set |
| `src/` `web/` | Runnable learning-loop UI (Challenge, Runs, Trace, Playbook, Journal, Promote) |
| `mockups/` | Static screen mockups |
| `architecture.md` | Locked loop + partner graph |
| `SPEC.md` | Task family, policy, metrics |
| `plans/` | Briefs and research |

## Contracts (Step 1)

```bash
cd journeyman
python -m pip install -e ".[dev]"
python -m pytest
```

Mechanisms import shapes from `journeyman.contracts` only.

## Loop UI

```bash
cp .env.example .env
npm install
npm test
npm run dev
```

Keys stay in local `.env`. Do not commit them.
