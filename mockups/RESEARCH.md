# Journeyman UI Design Research & Pattern Theft

This document details the architectural and visual patterns researched and adapted from best-in-class agent evaluation, developer observability, and issue tracking tools for **Journeyman** — an apprentice agent that learns a third-party GitHub repository via MCP, compiles an active grounding playbook, and proves measurable v0 vs vN improvements.

---

## 1. LangSmith (Trace Trees & Run Compare)

- **Observed Patterns:**
  - Nested hierarchical execution trees (Run -> Agent Step -> Tool Call -> Model Evaluation).
  - High-density metadata headers per span: duration in milliseconds, input/output token counts, estimated dollar cost, and error status badges.
  - Side-by-side run comparison diffing: comparing two runs on the same input prompt with highlighted differences in tool call sequence and output quality.
- **What We Stole for Journeyman:**
  - **Trace Cockpit (`trace.html`):** The expandable span tree where the top-level task decomposes into `Playbook: Query Cache`, `Tool Call: github_mcp/get_issue`, and `Agent: Synthesize & Ground Answer`.
  - **Playbook Hit vs. Cold Explore Comparison:** Direct side-by-side trace visualizer comparing an ungrounded v0 run (blindly executing 6 exploratory calls across the repo, costing 14.2k tokens over 4,850ms) against a grounded v3 run (1 playbook lookup + 1 direct GitHub MCP call, costing 820 tokens over 890ms).
- **Mapped Screen:** `trace.html` (Trace Cockpit) and `runs.html` (Run comparison).

---

## 2. Braintrust & Promptfoo (Experiment Scoreboards & Split Gating)

- **Observed Patterns:**
  - Experiment matrix view comparing prompt/playbook versions (v0 through vN) horizontally across fixed evaluation test suites.
  - Strict semantic segregation between development training splits and sealed regression hold-out splits.
  - Three core evaluation columns displayed with tabular clarity: **Accuracy** (% pass), **Cost** (tokens / tool calls), and **Speed** (wall-clock latency).
  - Regression gating banners that block promotion if cost increases or accuracy regresses.
- **What We Stole for Journeyman:**
  - **Runs Scoreboard (`runs.html`):** The immediate 3-second judging hero scoreboard displaying the delta between `v0 (Baseline)` and `v3 (Active)` across Accuracy (+80.0%), Cost (-73% tokens, -75% tool calls), and Latency (-78% speedup).
  - **DEV vs. Hold-out Color Coding:** Cyan badge for DEV (10 frozen tasks used for reflection) vs. Violet locked badge for HOLD-OUT (6 cryptographically sealed tasks evaluated only at promotion).
  - **Promotion Gate (`promote.html`):** A strict gate requiring candidate versions to surpass DEV accuracy thresholds and maintain hold-out performance without budget exhaustion.
- **Mapped Screen:** `runs.html` (Scoreboard & Table) and `promote.html` (Promotion Gate).

---

## 3. Arize Phoenix (Span-Level Waterfall & Span Kinds)

- **Observed Patterns:**
  - Timeline waterfall visualizer where horizontal bars represent relative and absolute wall-clock durations of each span.
  - Semantic span typing: distinct visual tags for `AGENT`, `RETRIEVER` (Playbook Cache), and `TOOL` (MCP Client).
  - Detailed span payload drawer revealing input parameters, raw JSON responses, and HTTP/RPC status codes upon selection.
- **What We Stole for Journeyman:**
  - **Trace Waterfall Bar:** In the Trace Cockpit, each execution step features a proportional latency timeline bar showing where time was spent (e.g. 15ms playbook memory lookup vs. 340ms external GitHub MCP network call vs. 495ms model inference).
  - **Span Kind Pills:** Clear badge taxonomy (`[PLAYBOOK_HIT]`, `[MCP_CALL]`, `[POLICY_CHECK]`, `[SYNTHESIS]`) so judges instantly recognize the agent's decision boundary.
- **Mapped Screen:** `trace.html` (Trace Cockpit).

---

## 4. Linear (Dense Dark-Mode Instrument Panel & Keyboard-First Layout)

- **Observed Patterns:**
  - Pure utility-first dark mode: layered neutral slate/zinc surfaces (`#0b0d10`, `#12161c`, `#181e26`) with crisp 1px borders (`rgba(255,255,255,0.08)`) instead of heavy shadows or decorative gradients.
  - Tabular numerals (`font-variant-numeric: tabular-nums`) aligning metrics, costs, and latencies across dense data tables.
  - Keyboard shortcut hints (`[1]`-`[5]` navigation keys, `[/]` filter, `[Esc]` close) for rapid navigation.
  - High information density: tables and structured lists over bloated cards, eliminating empty padding.
- **What We Stole for Journeyman:**
  - **Shared Shell & Layout Grid:** Universal top navigation bar with keyboard shortcut indicators (`1: Runs`, `2: Challenge`, `3: Trace`, `4: Playbook`, `5: Promote`).
  - **Color Discipline:** Strict semantic-only colors (Emerald pass, Rose fail, Cyan DEV, Violet Hold-out, Amber active pointer) with no decorative rainbow badges.
- **Mapped Screen:** Shared Shell (`index.html`, `styles.css`) across all 5 screens.

---

## 5. GitHub Issues & Projects (Source Domain Authenticity)

- **Observed Patterns:**
  - Native GitHub issue triage metadata: issue numbers (`#1`, `#5`), label badges (`type:bug`, `area:runtime`, `priority:p0`), and logical code ownership (`CODEOWNERS`).
  - Read-only vs. write permission indicators and token scope warnings.
  - Git commit-style unified diff views showing additions (`+`) and removals (`-`) between versions.
- **What We Stole for Journeyman:**
  - **Realistic Domain Data:** Real fixture data matching `SPEC.md` (`arjun7n9s/journeyman-fixture`, issues `I1`..`I18`, PRs `P1`..`P4`, labels `type:bug`, `type:feat`, `type:docs`, `area:api`, `area:runtime`, `area:billing`, `area:ui`, `priority:p0`, `priority:p1`).
  - **Playbook Diff Viewer (`playbook.html`):** Git-style diff viewer highlighting facts newly learned by reflection (e.g. `+ search-before-list-all heuristic`, `+ stack trace -> type:bug mapping`, `+ /src/billing/ -> billing logical owner`).
  - **Read-Only Sandbox Banner (`challenge.html`):** Policy allowlist status confirming zero write permissions, blocking mutation attempts, and strictly prohibiting additions to the hold-out dataset.
- **Mapped Screen:** `challenge.html` (Challenge Sandbox) and `playbook.html` (Playbook Viewer).

---

## 6. Cursor & Claude Code (Session Traces & Policy Verification)

- **Observed Patterns:**
  - Monospaced agent action logs displaying exact MCP tool calls, CLI arguments, and formatted output previews.
  - Safety policy banners verifying execution boundaries before tools are invoked.
- **What We Stole for Journeyman:**
  - **Challenge Execution Log:** Live terminal-style read-out in `challenge.html` demonstrating the agent consulting the active playbook before issuing the read-only GitHub MCP query.
  - **Policy Guard Invariant Display:** Explicit verification that read-only allowlist rules (`mcp/readonly`) were respected and mutation requests were rejected.
- **Mapped Screen:** `challenge.html` and `trace.html`.

---

## 7. Hex & Observable (Notebook-Grade Lesson Journal)

- **Observed Patterns:**
  - Append-only linear narrative streams capturing sequential iterations, code experiments, and data insights chronologically.
  - Clear metadata provenance: author, triggering run ID, timestamps, and confidence boundaries.
- **What We Stole for Journeyman:**
  - **Journal Tab (`journal.html`):** The append-only reflection log (`JOURNAL.md`) capturing architectural insights (e.g. deduplication fingerprints, `#HEUR-01: search-before-list-all`, logical CODEOWNERS owner mappings) synthesized exclusively from DEV traces.
  - **Quarantine Guarantee Callout:** Explicit banner and metadata badges verifying that hold-out traces never contaminate the journal stream.
- **Mapped Screen:** `journal.html` (Playbook Journal).

---

## 8. Vercel & Linear (Instant Deployment Rollback & Pointer Audit)

- **Observed Patterns:**
  - Version pointer architecture where production points to an immutable deployment hash, decoupled from new builds.
  - One-click instant rollback restoring prior verified stable pointers without full rebuilds or destructive data loss.
  - Visual distinction between candidate evaluation, active production pointer, and historical rollback targets.
- **What We Stole for Journeyman:**
  - **Promote / Rollback Gate (`promote.html`):** Interactive rollback controls allowing judges or operators to immediately re-point the active version pointer to prior verified releases (`v2`, `v1`) in the event of regressions.
  - **Safe Rejection Guarantee:** Rejection archives a candidate safely without rolling back to an ungrounded baseline or dumping failing budget-exhaust candidates into production.
- **Mapped Screen:** `promote.html` (Promote & Rollback Gate).

---

## 9. Integrated Partner Stack (TensorMux, Neatlogs, OpenAI Escalate + Embeddings)

- **Observed Architecture Invariants (Commit 4dcfa90):**
  - **TensorMux (`https://api.tensormux.com/v1`, model `glm-4-7-flash`):** Daily brain driving Actor, Self-Reflection, Patch Synthesizer, and RedTeam runs. Every model invocation writes input/output token counts, latency, and estimated cost directly into the run trace.
  - **Neatlogs (`NEATLOGS_API_KEY`):** System of Record (SoR) for traces. Ingests hierarchical spans for every tool hop (`github_mcp/readonly`) and model call with role attribution (`actor`, `reflect`, `patch`, `eval`, `redteam`). Fail &rarr; patch &rarr; replay cycles share the same run family.
  - **AI Grants OpenAI (`https://api.openai.com/v1`):** Strictly segmented into two bounded roles:
    1. *Escalator:* `gpt-5-nano` is triggered *only* after a logged TensorMux quality-gate miss on Reflect, Patch, or an ungrounded Actor step.
    2. *Embeddings:* `text-embedding-3-small` (with `ada-002` fallback) generates dense vector embeddings for fast Playbook RAG retrieval.
- **What We Stole for Journeyman:**
  - **Neatlogs Trace Cockpit (`trace.html`):** The entire Trace Cockpit UI is styled as a high-fidelity Neatlogs span inspector, tracking span IDs (`nl_sp_8f3a1b`), role kinds, proportional duration waterfalls, and before/after patch replay families.
  - **Quality Gate Visibility:** Visual indicators and verification checks showing TensorMux executing at $0.0016/triage with zero OpenAI escalate invocations when grounding succeeds.
- **Mapped Screens:** `trace.html` (Neatlogs Cockpit), `challenge.html` (TensorMux Actor), `playbook.html` (OpenAI Embeddings RAG), and `journal.html` (TensorMux Reflection).
