# Journeyman architecture (integrated)

Locked loop + partner stack. Keys live in local `.env` only. Never paste keys into chat.

- **Track:** Automated Agent Engineering
- **Task family:** repo triage / grounding on `arjun7n9s/journeyman-fixture`
- **Third-party app:** GitHub MCP readonly
- **Everyday brain:** TensorMux `https://api.tensormux.com/v1` / `glm-4-7-flash` / `TMX_API_KEY`
- **Trace SoR:** Neatlogs (`NEATLOGS_API_KEY`) — Trace cockpit reads this
- **OpenAI (one partner, two uses):** `https://api.openai.com/v1` + `OPENAI_API_KEY`. Chat escalate = `gpt-5-nano` after a logged TensorMux quality-gate miss. Embeddings = `text-embedding-3-small` (ada-002 backup) from the Embed/RAG node. Not a child of chat.
- **Skip v1:** Smallest.ai voice, Dodo infra, prize-credit boxes

```mermaid
flowchart TB
  subgraph ui [Browser UI]
    Challenge[Challenge]
    Runs[Runs timeline]
    Trace[Trace cockpit]
    PlaybookUI[Playbook viewer]
    JournalUI[Journal tab]
    PromoteUI[Promote / Rollback]
  end

  subgraph brain [Journeyman loop]
    Router[Cost router]
    Actor[Journeyman Actor]
    Gates[Context Gates]
    Policy[Policy YAML]
    Reflect[Self-reflection]
    Patch[Patch synthesizer]
    Budget[Patch Budget]
    EvalDev[Eval DEV]
    EvalHold[Eval HELD-OUT]
    RedTeam[RedTeam on LIVE]
    Embed[Playbook RAG]
  end

  subgraph memory [Memory]
    Playbook[(Playbook versions)]
    Scripts[(Scripts)]
    Journal[(Playbook Journal md)]
    Traces[(Run traces)]
    Versions[(Active version pointer)]
  end

  subgraph partners [Partner stack]
    TMX[TensorMux glm-4-7-flash]
    NL[Neatlogs]
    OAI[AI Grants OpenAI]
  end

  subgraph tools [Third-party app]
    MCP[GitHub MCP readonly]
  end

  Judge([Judge]) --> Challenge
  Judge --> PromoteUI
  Judge --> Trace

  Playbook --> Embed
  Embed -->|text-embedding-3-small| OAI
  Embed -->|quirks this run| Actor
  Scripts -->|retrieved every run| Actor
  Versions -->|active playbook| Actor
  Playbook -->|seen pattern to cheap path| Router

  Challenge --> Router --> Actor
  Actor --> Gates --> Policy --> MCP --> Actor

  Actor -->|default| TMX
  Reflect -->|default| TMX
  Patch -->|default| TMX
  RedTeam -->|default| TMX

  Actor -->|gate miss: gpt-5-nano| OAI
  Reflect -->|gate miss: gpt-5-nano| OAI
  Patch -->|gate miss: gpt-5-nano| OAI

  Actor --> Traces
  Reflect --> Traces
  Patch --> Traces
  RedTeam --> Traces
  EvalDev --> Traces
  Traces -->|tokens latency cost| Runs
  Traces --> NL
  NL --> Trace

  Traces --> Reflect
  Playbook -->|merge / supersede| Reflect
  EvalDev -->|fail patterns| Reflect
  Reflect -->|diffable merge| Playbook
  Reflect --> Scripts
  Reflect -->|append lesson| Journal
  Journal --> JournalUI
  Playbook --> PlaybookUI
  Versions --> PlaybookUI

  Traces --> Patch
  Playbook --> Patch
  Scripts --> Patch
  Versions -->|prior verdicts| Patch
  Patch --> Budget
  Budget -->|candidate| EvalDev
  Budget -->|stop no-improve| PromoteUI

  EvalDev --> Runs
  EvalDev -->|helps| PromoteUI
  PromoteUI -->|candidate only| EvalHold
  EvalHold -->|headline| PromoteUI
  EvalHold --> Runs
  PromoteUI -->|approved| Versions
  PromoteUI -->|rollback| Versions
  PromoteUI -->|rejected| Actor

  Versions -->|LIVE| RedTeam
  RedTeam -->|fail| Patch
  RedTeam --> Runs

  Challenge -.->|never writes| EvalHold
```

## Runtime (Python source of truth)

Contracts, Actor, `SuperviseCycle`, `CostRouter.decide`, Reflect, and the demo loop live in `journeyman/`. The root TypeScript/Vite tree is legacy gather/mockups — not a second loop.

SuperviseCycle (pre-promote): TraceIngest.poll → FailureJudge.diagnose → skip if not failure → CausalAnalyst.analyze → ProbeFactory.synthesize → resolve baseline → LiveScorer.run_baseline → PromptSurgeon.propose (CANDIDATE only) → LiveScorer.run_candidate → ExactReplay.replay → persist postmortem.

Then: Eval DEV on the candidate → **sealed hold-out** (candidate vs prior active, scored only at promote; never a Run1 hold run; ingest ignores `split=holdout`) → promote if DEV improves and hold-out does not collapse → **RedTeam on LIVE** → RunN.

Cheap chat is `glm-4-7-flash` at `https://api.tensormux.com/v1`. Escalate is the same Actor/Reflect/Patch hop to `gpt-5-nano` at `https://api.openai.com/v1` only after a logged quality-gate miss. Embeddings (`text-embedding-3-small`) are a separate `embed_route` / `ChatClient.embed` path, never a child of chat. GitHub tools are official MCP readonly names; REST is `JOURNEYMAN_GITHUB_REST=1` only. Frozen eval is `eval/dev.json` (10) + `eval/holdout.json` (6) on `arjun7n9s/journeyman-fixture`. Trace SoR ingest is `https://ingest.neatlogs.com` (`POST /v1/trace`); the dashboard is `https://app.neatlogs.com`.

## Partner rules

| Partner | Role | Not for |
|---|---|---|
| **TensorMux** | Default provider for Actor / Reflect / Patch / RedTeam (`glm-4-7-flash`). | Embeddings |
| **Neatlogs** | System of record. Ingest `https://ingest.neatlogs.com` (`NEATLOGS_BASE_URL`, `POST /v1/trace`, `x-api-key`). Dashboard `https://app.neatlogs.com`. Universal path: **Actor / Reflect / Patch / RedTeam / Eval DEV / Eval Hold / Router → Traces → NL → Trace cockpit**. | Replacing Runs scores; posting to `app.neatlogs.com` |
| **AI Grants OpenAI** | One key, two calls. **Chat:** after a logged TensorMux quality-gate miss, the same Actor / Reflect / Patch node calls `gpt-5-nano`. **Embed:** Playbook RAG calls `text-embedding-3-small` (ada-002 backup). Base URL `https://api.openai.com/v1`. | Daily chat driver; a separate "Nano" service |
| **GitHub MCP** | Third-party app. Official readonly MCP (`issue_read`, `list_issues`, …). Frozen eval on `arjun7n9s/journeyman-fixture`. | Writes in DEV/hold-out; REST as the primary path |
| **Smallest.ai / Dodo** | Keys may exist in `.env`. Not architecture boxes in v1. | |

Every model call (TensorMux or OpenAI) still writes tokens, latency, and rough $ onto the **trace**, then into Neatlogs and the Runs timeline.

## Grafts

Router, Gates, Patch + Budget, RedTeam, Scripts, Journal, Rollback, TensorMux, Neatlogs, OpenAI (escalate + embeddings).

## Build order

1. **Actor ↔ MCP ↔ Traces ↔ Neatlogs** — Challenge → router stub → actor → gates stub → policy → GitHub MCP. TensorMux default. Every hop + model call: node → Traces → NL.
2. **Reflect → Playbook / Journal + RAG** — DEV traces → playbook + journal. Embed node → OpenAI embeddings. Escalate Reflect to `gpt-5-nano` only on a logged gate miss (same Reflect node).
3. **Eval DEV** — frozen 10-task DEV. Eval → Traces → NL. Runs shows v0 vs later.
4. **Patch + Budget** — TensorMux default; escalate Patch to nano on a logged miss. Replay the same Neatlogs run family.
5. **Promote / held-out** — candidate-only sealed hold-out; approve / reject / rollback.
6. **Router / Gates / RedTeam polish** — cheap path; gates; red-team still Actor-style: node → TMX (or nano) and node → Traces → NL.

Invariant: Challenge never writes hold-out. Hold-out is scored only at promote (candidate vs prior active) and never trains playbook or journal. OpenAI chat never appears unless a gate miss is logged. RedTeam runs after promote on LIVE only.

## Locked interfaces

| Surface | Shows |
|---|---|
| Challenge | Judge task in; MCP + active playbook/scripts |
| Runs | DEV vs hold-out, v0 vs vN, accuracy / cost / speed. Cost from traces. |
| Trace | Neatlogs cockpit. Judge lands here for before/after a patch. |
| Playbook | Active version + RAG-retrieved facts |
| Journal | Append-only reflection lessons |
| Promote / Rollback | DEV + hold-out headline; approve, reject, rollback |
