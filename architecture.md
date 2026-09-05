# Journeyman architecture (locked)

This is the **finalized** graph. Grafts are in. Implement in the build order below — do not skip ahead to polish boxes.

- **Track:** Automated Agent Engineering
- **Third-party (pinned):** GitHub official MCP, readonly for eval (`https://api.githubcopilot.com/mcp/readonly`)
- **Workspace:** `arjun7n9s/journeyman-fixture`
- **Task family:** repo triage / grounding
- **Metrics every run:** accuracy, cost (tools + tokens), speed (ms)

See [plans/SPEC.md](plans/SPEC.md) for tasks, policy, and eval splits.

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

Do not implement later stages before earlier ones work and can be shown.

1. **Actor ↔ MCP ↔ Traces** — Challenge hits actor; policy-gated GitHub MCP; every run writes a trace.
2. **Reflect → Playbook / Journal** — DEV traces become a diffable playbook version and an appended journal lesson. Next run retrieves playbook (and scripts when they exist).
3. **Eval DEV** — frozen 10-task DEV scores accuracy / cost / speed. Runs shows v0 vs later.
4. **Patch + Budget** — synthesizer proposes a candidate; N tries / no-improve stop. Do not promote a failing exhaust.
5. **Promote / held-out** — candidate-only sealed hold-out; approve activates version; rollback restores prior pointer.
6. **Router / Gates / RedTeam polish** — cheap path on seen patterns; context gates in front of policy; red-team on LIVE writes fails into Patch and Runs.

Invariant through every stage: Challenge never writes hold-out. Hold-out never trains playbook or journal.

## Locked interfaces

| Surface | Shows |
|---|---|
| Challenge | Judge task in; classify/answer via MCP + active playbook/scripts |
| Runs | DEV vs hold-out, v0 vs vN, three metrics; later red-team rows |
| Trace | Step-through tool spans, args, result, cost, latency |
| Playbook | Active version + facts learned from the fixture repo |
| Journal | Append-only lessons from reflection (markdown) |
| Promote / Rollback | DEV score + hold-out headline; approve, reject, rollback |
