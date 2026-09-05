# Journeyman architecture (locked)

Canonical copy: [../architecture.md](../architecture.md)

This is the **finalized** graph. Grafts are in. Implement in the build order below — do not skip ahead to polish boxes.

- **Track:** Automated Agent Engineering
- **Third-party (pinned):** GitHub official MCP, readonly for eval (`https://api.githubcopilot.com/mcp/readonly`)
- **Workspace:** `arjun7n9s/journeyman-fixture`
- **Task family:** repo triage / grounding
- **Metrics every run:** accuracy, cost (tools + tokens), speed (ms)

See [SPEC.md](./SPEC.md) for tasks, policy, and eval splits.

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
  end

  subgraph memory [Memory]
    Playbook[(Playbook versions)]
    Scripts[(Scripts)]
    Journal[(Playbook Journal md)]
    Traces[(Run traces)]
    Versions[(Active version pointer)]
  end

  subgraph tools [Third-party]
    MCP[GitHub MCP readonly]
  end

  Judge([Judge]) --> Challenge
  Judge --> PromoteUI

  Playbook -->|retrieved every run| Actor
  Scripts -->|retrieved every run| Actor
  Versions -->|active playbook| Actor
  Playbook -->|seen pattern to cheap path| Router

  Challenge --> Router --> Actor
  Actor --> Gates --> Policy --> MCP --> Actor
  Actor --> Traces
  Traces --> Trace
  Traces --> Runs

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

## Grafts (locked in)

Router, Gates, Patch + Budget, RedTeam, Scripts, Journal, Rollback on Promote.

## Build order

1. Actor ↔ MCP ↔ Traces
2. Reflect → Playbook / Journal
3. Eval DEV
4. Patch + Budget
5. Promote / held-out
6. Router / Gates / RedTeam polish

Invariant: Challenge never writes hold-out. Hold-out never trains playbook or journal.
