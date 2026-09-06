# Journeyman v1 spec

Pinned. Do not reopen the third-party choice.

- **Product:** Journeyman
- **Track:** Automated Agent Engineering
- **Third-party:** GitHub official MCP
  - Eval / default: `https://api.githubcopilot.com/mcp/readonly`
  - Write (only if Challenge later needs it; v1 is read-only): `https://api.githubcopilot.com/mcp/`
- **Workspace:** seeded fixture repo `arjun7n9s/journeyman-fixture` (create if missing)
- **Task family:** repo triage / grounding (same tools, varied asks)
- **Architecture:** locked in [architecture.md](architecture.md). Grafts in: Router, Gates, Patch+Budget, RedTeam, Scripts, Journal, Rollback, TensorMux, Neatlogs, OpenAI escalate + embeddings.
- **Build order:** Actor↔MCP↔Traces↔Neatlogs → Reflect→Playbook/Journal+RAG → EvalDev → Patch+Budget → Promote/held-out → Router/Gates/RedTeam polish.

## Policy allowlist

Allowed (read): list/get repo, list labels, get file (`CODEOWNERS`, `CONTRIBUTING.md`, paths under `src/`), list/get/search issues, list/get/search PRs, search code.

Denied: push, force-push, delete, secrets, org admin, workflows, deploy keys, writing issues/PRs/comments during DEV or hold-out.

Challenge tab is read-only in v1 (classify / answer only). It must not append tasks to hold-out.

## Fixture repo (seed this)

Public repo `arjun7n9s/journeyman-fixture`. Plant these so the playbook has *their* data to learn.

**Labels:** `type:bug`, `type:feat`, `type:docs`, `area:api`, `area:runtime`, `area:billing`, `area:ui`, `priority:p0`, `priority:p1`.

**Files:**

- `CONTRIBUTING.md` — label rules (stack trace → `type:bug`; crash/nil/OOM → `priority:p0`; path `src/billing|runtime|api|ui` → matching `area:*`; docs/typo/README → `type:docs`).
- `CODEOWNERS` — `/src/billing/ @arjun7n9s`, `/src/runtime/ @arjun7n9s`, `/src/api/ @arjun7n9s`, `/src/ui/ @arjun7n9s`.
- Stub files: `src/billing/charge.py`, `src/runtime/worker.py`, `src/api/routes.py`, `src/ui/app.tsx`, `README.md`.

**Logical owners** (eval answers use these, not the GitHub handle): `src/billing` → `billing`, `src/runtime` → `runtime`, `src/api` → `api`, `src/ui` → `ui`.

After creating issues/PRs, write the assigned numbers into the eval JSON. Do not invent numbers.

### World issues to create (titles must match)

| Key | Title | Body must include | Intended labels |
|---|---|---|---|
| I1 | API returns 500 on empty payload | stack trace with `src/api/routes.py` | type:bug, area:api |
| I2 | Add invoice PDF export | billing/invoice feature ask | type:feat, area:billing |
| I3 | README typo in install section | docs/typo | type:docs |
| I4 | Runtime worker leaks memory after 2h | stack in `src/runtime/worker.py` | type:bug, area:runtime |
| I5 | Crash loop on nil context | crash + nil + `src/runtime/worker.py` | type:bug, area:runtime, priority:p0 |
| I6 | Dark mode toggle | UI feature | type:feat, area:ui |
| I7 | Charge webhook retries twice | `src/billing/charge.py` | type:bug, area:billing |
| I8 | Document env vars | docs | type:docs |
| I9 | API returns 500 when body is empty | same bug as I1, different wording | type:bug, area:api (duplicate of I1) |
| I10 | Worker OOM after long run | same as I4, different wording | type:bug, area:runtime (duplicate of I4) |
| I11 | OpenAPI spec missing 400 examples | docs + api | type:docs, area:api |
| I12 | Billing cron double-charges on retry | `src/billing/charge.py` | type:bug, area:billing, priority:p0 |
| I13 | Add CSV export for invoices | similar to I2, hold-out | type:feat, area:billing |
| I14 | Panic in worker when ctx canceled | similar to I5, hold-out | type:bug, area:runtime, priority:p0 |
| I15 | Fix typo in contributing guide | docs, hold-out | type:docs |
| I16 | UI button misaligned on settings | ui bug, hold-out | type:bug, area:ui |
| I17 | REST handler 500 on null JSON | similar to I1, hold-out | type:bug, area:api |
| I18 | Rate limit headers not documented | docs+api, hold-out | type:docs, area:api |

### World PRs to create

| Key | Title | Touches | Closes |
|---|---|---|---|
| P1 | Fix empty payload 500 in API | `src/api/routes.py` | I1 |
| P2 | Cap runtime worker memory | `src/runtime/worker.py` | I4 |
| P3 | Idempotent billing webhook | `src/billing/charge.py` | I7 |
| P4 | Settings page layout | `src/ui/app.tsx` | (none) |

## Eval JSON (commit into this product repo)

Write `eval/dev.json` and `eval/holdout.json`. Schema:

```json
{
  "split": "dev",
  "repo": "arjun7n9s/journeyman-fixture",
  "tasks": [
    {
      "id": "dev-01",
      "type": "label",
      "prompt": "What labels should this issue get, using this repo's taxonomy?",
      "github": { "issue_key": "I1", "issue_number": 0 },
      "expected": { "labels": ["area:api", "type:bug"] },
      "score": { "accuracy": "exact_set" }
    }
  ]
}
```

Replace `issue_number` / `pr_number` with real GitHub numbers. Keep `issue_key` / `pr_key` stable.

### DEV tasks (10) — reflection may use these traces only

| id | type | target | expected |
|---|---|---|---|
| dev-01 | label | I1 | labels: type:bug, area:api |
| dev-02 | label | I2 | labels: type:feat, area:billing |
| dev-03 | label | I3 | labels: type:docs |
| dev-04 | label | I5 | labels: type:bug, area:runtime, priority:p0 |
| dev-05 | duplicate | I9 | duplicate_of: I1 |
| dev-06 | duplicate | I10 | duplicate_of: I4 |
| dev-07 | owner | PR path `src/billing/charge.py` | owner: billing |
| dev-08 | owner | PR path `src/runtime/worker.py` | owner: runtime |
| dev-09 | summarize | open bugs in area:api | must mention I1 (and I9 if still open) |
| dev-10 | fix_pr | which PR fixed I1 | pr: P1 |

### Hold-out tasks (6) — sealed. Run only at promote. Never write playbook from these.

| id | type | target | expected |
|---|---|---|---|
| hold-01 | label | I13 | labels: type:feat, area:billing |
| hold-02 | label | I14 | labels: type:bug, area:runtime, priority:p0 |
| hold-03 | label | I15 | labels: type:docs |
| hold-04 | label | I17 | labels: type:bug, area:api |
| hold-05 | owner | PR path `src/ui/app.tsx` | owner: ui |
| hold-06 | summarize | open docs issues | must mention I3 and I8 (I15/I18 if open) |

Hold-out is a sealed **task set**, not hidden issues. The actor can list the repo. The harness must not run hold-out until promote, and must not feed hold-out traces into reflection.

## Metrics (every run, all three)

- **accuracy:** 1 if expected fields match (label exact-set, duplicate issue number, owner string, PR number; summarize = required keys present). Else 0. Split score = mean.
- **cost:** tool-call count + token estimate (or $ if available).
- **speed:** wall-clock ms.

Reliability (optional): tool errors / retries. Show if cheap.

## Learning loop

Follow [architecture.md](architecture.md) build order.

1. Actor retrieves active playbook (and scripts when present). Challenge → router (stub until polish) → actor → gates (stub until polish) → policy → GitHub MCP. Write a trace.
2. Reflection merges a **diffable playbook version**, may emit a script, and **appends a journal lesson**. Next run must read playbook/scripts.
3. Eval DEV on the frozen 10. Patch synthesizer + budget produce candidates. Do not promote on budget exhaust / no-improve stop.
4. Promote runs sealed hold-out on a candidate only. Approve / reject / **rollback** the version pointer. Red-team runs on LIVE later.
5. Runs shows **v0 (empty playbook)** vs later versions. Challenge never writes hold-out. Hold-out never trains playbook or journal.

Playbook should grow facts like: this repo's labels; stack trace → bug; `src/billing` → billing; search before list-all.

## UI

Challenge, Runs (v0 vs vN + the three metrics), Trace cockpit, Playbook viewer, **Journal tab**, **Promote / Rollback**.

## Worker split

**Seed fixture:** create/seed `journeyman-fixture`, write `eval/dev.json` + `eval/holdout.json` (+ this spec if missing). No product UI. Commit on a session feature branch. Report repo URL and issue/PR number map.

**Build loop:** actor + traces + playbook + DEV/hold-out harness + the UI above, against this spec and the eval JSON schema. If JSON numbers are still `0`, keep the schema and poll/merge the fixture worker's files. Use GitHub MCP (readonly) with a token from env (`GITHUB_TOKEN` / `GH_TOKEN`). Do not add a second MCP.
