# Journeyman

Journeyman is a self-improving agent workbench: it ingests execution traces, judges failures, synthesizes probes, proposes versioned patches under budget, verifies with exact replay + adversarial suites, routes work cheap-first with quality gates, grows a local skill library (search-before-write), and enforces tool calls through versioned policy streams with optional shadow arms — journaling durable insights across sessions.

This tree is the scaffold. `journeyman.contracts` is the only place shapes live. Later steps fill the mechanism packages without redefining models.

The supervise cycle, when implemented, follows this order:

TraceIngest.poll → FailureJudge.diagnose → skip if not failure → CausalAnalyst.analyze → ProbeFactory.synthesize → resolve baseline → LiveScorer.run_baseline → PromptSurgeon.propose (candidate only) → LiveScorer.run_candidate → ExactReplay.replay → AdversarialProbe.attack → persist postmortem stub

Ingest skips `session_id=="test"`, `prompt_variant=="candidate"`, and tool-child spans. The seen ring holds 500 ids.

## Layout

- `src/journeyman/contracts` — typed models, enums, constants
- mechanism packages — stubs that raise `NotImplementedError`
- `playbooks/index.yaml` — harness list (empty, schema-valid)
- `journal/CORE.md` — durable-insight template
- `tests/contracts` — roundtrip, `should_stop`, `WorkItem.from_span`, enum snapshot

## Develop

```bash
python -m pip install -e ".[dev]"
python -m pytest
```
