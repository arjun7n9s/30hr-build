# Journeyman architecture (locked v1)

Canonical copy: [../architecture.md](../architecture.md)

This is the **locked** baseline. Add branches and integrations only as explicit follow-ups. Do not resurrect cut boxes (cost router, Context Gates, patch synthesizer, script library, red-team) unless a later note says so.

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
    PromoteUI[Promote]
  end

  subgraph brain [Journeyman loop]
    Actor[Journeyman Actor]
    Policy[Policy YAML]
    Reflect[Self-reflection]
    EvalDev[Eval DEV]
    EvalHold[Eval HELD-OUT]
  end

  subgraph memory [Memory]
    Playbook[(Playbook versions)]
    Traces[(Run traces)]
    Versions[(Active version pointer)]
  end

  subgraph tools [Third-party]
    MCP[GitHub MCP readonly]
  end

  Judge([Judge]) --> Challenge
  Judge --> PromoteUI

  Playbook -->|retrieved every run| Actor
  Versions -->|active playbook| Actor

  Challenge --> Actor
  Actor --> Policy --> MCP --> Actor
  Actor --> Traces
  Traces --> Trace
  Traces --> Runs

  Traces --> Reflect
  Reflect -->|diffable merge| Playbook
  Playbook --> PlaybookUI
  Versions --> PlaybookUI

  Playbook --> EvalDev
  EvalDev --> Runs
  EvalDev -->|helps| PromoteUI
  PromoteUI -->|candidate only| EvalHold
  EvalHold -->|headline| PromoteUI
  EvalHold --> Runs
  PromoteUI -->|approved| Versions
  PromoteUI -->|rejected| Actor

  Challenge -.->|never writes| EvalHold
```

## Loop in words

1. Challenge hits the actor. The actor reads the **active playbook**, then Policy YAML, then GitHub MCP, then writes a **trace**.
2. After DEV work, reflection writes a **diffable playbook version**. The next run must retrieve it.
3. Frozen **Eval DEV** scores accuracy / cost / speed. If it helps, Promote may run **sealed hold-out**.
4. Approve activates the version pointer. Reject leaves the actor on the previous version.
5. Runs shows **v0 (empty playbook)** vs later versions. Hold-out never trains the playbook. Challenge never appends hold-out tasks.

## Intentionally not in v1

Cost router, Context Gates as a subsystem, patch synthesizer / patch budget product, script library, red-team cadence, rollback chrome beyond “activate this version.”

## Locked interfaces

| Surface | Shows |
|---|---|
| Challenge | Judge task in; classify/answer via MCP + playbook |
| Runs | DEV vs hold-out, v0 vs vN, three metrics |
| Trace | Step-through tool spans, args, result, cost, latency |
| Playbook | Active version + facts learned from the fixture repo |
| Promote | DEV score + hold-out headline; approve / reject |
