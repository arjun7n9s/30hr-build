# Journeyman UI mockup brief

You are a **mockup / visual-design worker only**.

- Do **not** implement the Journeyman backend, actor, eval harness, or fixture seeder.
- Do **not** touch `eval/`, playbook runtime, or GitHub seeding.
- Do **not** add `package.json`, npm, Vite, or a dev server just to show static screens. Static HTML/CSS only.
- Put all deliverables under `mockups/` in this workspace.
- After the primary HTML exists, open it with `ao preview mockups/index.html` (path is relative to the workspace root). Do not use `file://`.

Read `SPEC.md` or `plans/SPEC.md` if present so the screens match the product. Product is **Journeyman**: an apprentice agent that learns a third-party GitHub repo via MCP, writes a playbook, and shows measurable v0 vs vN gains.

## Research first (required)

Search the live web before you draw. Steal structure from **best-in-class agent / eval / ops UIs**, not generic AI-SaaS landings (no floating gradient orbs, no Inter-on-navy dashboard cliché unless you can justify it from a cited product).

Look at, and name in a short `mockups/RESEARCH.md`, at least 5 of:

- LangSmith (trace tree, run compare)
- Braintrust / Promptfoo (experiment scoreboard, DEV vs hold-out)
- Phoenix / Arize (span-level traces)
- Weights & Biases or Weave
- Linear (issue density, keyboard-first, status)
- Vercel / v0 project dashboard
- Cursor / Claude Code session traces
- GitHub Issues + Projects (source domain)
- Hex / Observable (notebook-grade data clarity)

For each: what pattern you took, and which Journeyman screen it maps to.

**Direction to choose (do not invent a sixth product):**

- **Genre:** dark, dense, instrument-panel. Feels like a control room for an apprentice, not a marketing site.
- **Information hierarchy:** scoreboard first, chrome last. A judge should see **v0 vs vN** and the three metrics in under 3 seconds.
- **Typography:** one strong display face + one readable mono for traces/JSON. Avoid generic Inter-only UI.
- **Color:** semantic only — DEV vs hold-out, pass/fail, cost, promote. Not rainbow badges.
- **Density:** more Linear / LangSmith than Notion. Tables and traces beat cards.
- **Motion:** none required. Static mockups.

## Screens you must mock (exactly these five)

Use a shared shell: left or top nav with these five destinations. Realistic Journeyman data (GitHub triage, labels `type:bug` / `area:runtime`, playbook entries, tool traces). No lorem.

### 1. Challenge

Judge types a general task (issue title/body or “label this”). Shows the actor will hit GitHub MCP + the **active playbook**. Read-only classify/answer. No “add to hold-out” control.

### 2. Runs

Timeline/table of eval runs. **Color-code DEV vs hold-out.** Columns that matter: version (v0 empty playbook vs vN), split, **accuracy**, **cost** (tools + tokens), **speed** (ms). Headline: v0 vs latest, so the learning claim is obvious. Clicking a run goes to Trace.

### 3. Trace cockpit

Step-through of one run: tool name, args, result snippet, latency, cost. Expand a span. This is LangSmith-like, not a raw log dump. Show a playbook hit vs a cold explore path.

### 4. Playbook viewer

Versioned playbook dump: facts learned from the fixture repo (label taxonomy, stack-trace → bug, `src/billing` → billing, search-before-list-all). Show active version pointer and a diff vs previous version.

### 5. Promote

Gate: candidate version, DEV score, **sealed hold-out headline**, Approve / reject. Reject does not dump a failing budget-exhaust candidate. Copy should say hold-out never trained the playbook.

## Deliverables

1. `mockups/RESEARCH.md` — sources + what you stole.
2. `mockups/index.html` — shell + nav; default to Runs (the judging argument).
3. One HTML file per screen, linked from the shell (`challenge.html`, `runs.html`, `trace.html`, `playbook.html`, `promote.html`) **or** a single HTML with in-page sections that look like those five routes. Prefer five files + index if clearer.
4. Shared `mockups/styles.css`. No JS framework. Tiny JS for tabs is OK.
5. Open the primary file with `ao preview mockups/index.html` when it exists.

Work on a session feature branch (sibling of `.../root`, not `root/topic`). Commit mockups only. Do not open a PR unless asked.

When done, reply with: 5 research takeaways, the visual thesis in 2 sentences, and the `mockups/` paths.
