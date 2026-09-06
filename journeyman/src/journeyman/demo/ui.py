"""Minimal local HTML cockpit. Reads DemoReport JSON; does not run the loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_ui(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload)
    path.write_text(_HTML.replace("__REPORT__", blob.replace("</", "<\\/")), encoding="utf-8")
    return path


_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Journeyman</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Anton&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet" />
  <style>
    :root { --cream:#F3E9D8; --ink:#111111; --poster:#F04E2E; }
    * { box-sizing: border-box; }
    html, body { margin: 0; background: var(--cream); color: var(--ink); font-family: "IBM Plex Sans", sans-serif; }
    button, a, [role="button"] { cursor: pointer; }
    .shell { max-width: 1120px; margin: 0 auto; padding: 1.4rem 1.2rem 3rem; }
    header { display: flex; justify-content: space-between; gap: 1rem; border-bottom: 2px solid var(--ink); padding-bottom: 0.9rem; }
    h1 { margin: 0; font-family: "IBM Plex Sans", sans-serif; font-size: 1.45rem; font-weight: 600; }
    .kicker { margin: 0 0 0.2rem; font-family: "IBM Plex Mono", monospace; font-size: 0.68rem; letter-spacing: 0.16em; text-transform: uppercase; }
    .meta { font-family: "IBM Plex Mono", monospace; font-size: 0.75rem; text-align: right; }
    nav { display: flex; gap: 0; margin: 1rem 0; border-bottom: 2px solid var(--ink); }
    .tab { background: transparent; border: 0; border-bottom: 4px solid transparent; padding: 0.6rem 0.85rem; font: inherit; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; }
    .tab.active { border-bottom-color: var(--poster); }
    .panel { border: 2px solid var(--ink); background: var(--cream); padding: 1rem; margin: 0.7rem 0; box-shadow: 7px 7px 0 var(--poster); }
    .metric { font-size: 3rem; line-height: 0.94; font-weight: 600; }
    pre { white-space: pre-wrap; font-family: "IBM Plex Mono", monospace; font-size: 0.82rem; }
    a { color: var(--ink); }
    .stamp { background: var(--ink); color: var(--cream); border: 0; padding: 0.7rem 1rem; font-weight: 600; box-shadow: 7px 7px 0 var(--poster); }
    .stamp:hover { transform: translate(3px, 3px); background: var(--poster); color: var(--ink); }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 0.35rem 0.2rem; border-bottom: 1px solid var(--ink); font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <p class="kicker">Python source of truth</p>
        <h1>Journeyman</h1>
      </div>
      <div class="meta" id="meta"></div>
    </header>
    <nav>
      <button class="tab active" data-tab="challenge">Challenge</button>
      <button class="tab" data-tab="runs">Runs</button>
      <button class="tab" data-tab="trace">Trace</button>
      <button class="tab" data-tab="playbook">Playbook</button>
      <button class="tab" data-tab="journal">Journal</button>
      <button class="tab" data-tab="promote">Promote / Rollback</button>
    </nav>
    <main id="main"></main>
  </div>
  <script>
    const R = __REPORT__;
    const pct = (n) => n == null ? "—" : Math.round(n * 100) + "%";
    document.getElementById("meta").innerHTML =
      `<div>${R.repo || ""}</div><div>mode ${R.mode}</div><div>active ${R.pointer.active}</div>`;
    const telemetry = /^(?:[-*]\\s*)?(?:Run\\d+\\s+DEV\\b|Reflect merged\\b|promoted\\s|Derived\\s|Mined\\s|candidate held\\b|postmortem\\s)/i;
    const failureDump = /When asked .+ do not invent\\.\\s*Failed with/i;
    const weakAdvice = /be helpful and confident|guess if you are unsure/i;
    const toolDump = /\\{['"]found['"]|get_file_contents:|pull_request_read:|issue_read:|list_issues:|From repo evidence/i;
    const humanize = (text) => text
      .replace(/^WHEN\\s+/i, "If ")
      .replace(/\\s+THEN\\s+/i, ", ")
      .replace(/\\['([^']+)'\\]/g, "$1")
      .replace(/\\["([^"]+)"\\]/g, "$1")
      .replace(/\\bcontains\\b/g, "mentions")
      .replace(/\\bset owner=/g, "set owner to ")
      .replace(/\\badd labels=/g, "add label ")
      .trim();
    const isHuman = (line) => {
      const t = (line || "").trim();
      return t.length >= 12 && t.length <= 280 && !telemetry.test(t) && !failureDump.test(t) && !weakAdvice.test(t) && !toolDump.test(t);
    };
    const lessons = (() => {
      const out = [];
      const seen = new Set();
      const push = (id, text) => {
        const key = text.toLowerCase();
        if (seen.has(key) || !isHuman(text)) return;
        seen.add(key);
        out.push({ id, text });
      };
      (R.playbook_entries || []).forEach((entry) => {
        if ((entry.tags || []).includes("weak")) return;
        String(entry.text || "").split(/\\n+/).forEach((chunk) => {
          push(entry.id, chunk.replace(/^[-*]\\s*/, "").replace(/^Rule:\\s*/i, "").trim());
        });
      });
      (R.playbook_rules || []).forEach((rule) => push(rule.id, humanize(rule.text || "")));
      return out;
    })();
    const systemLog = String(R.journal || "").split(/\\r?\\n/)
      .map((line) => line.replace(/^[-*]\\s*/, "").trim())
      .filter((line) => telemetry.test(line));
    const lessonHtml = (items) => items.length
      ? `<ul>${items.map((item) => `<li>${item.text}</li>`).join("")}</ul>`
      : `<p>No human lessons yet. Run <code>python -m journeyman.demo.run --challenge frozen --mode offline</code>.</p>`;
    const pages = {
      challenge: () => `<section>
        <p class="kicker">Challenge ${R.challenge_id} · Cold → Learn → Warm</p>
        <div class="panel"><strong>Hold-out never trained the playbook.</strong></div>
        <div class="panel">
          <p class="kicker">1 · Cold</p>
          <p>Run1 DEV on a weak / empty playbook: <strong>${pct(R.run1 && R.run1.pass_rate)}</strong> pass · cost ${R.run1 && R.run1.cost} · ${(R.run1 && R.run1.tool_calls) || 0} tools · ${(R.run1 && R.run1.tokens) || 0} tok.</p>
        </div>
        <div class="panel">
          <p class="kicker">2 · Learn</p>
          <p>Human lessons from the playbook (not CORE.md telemetry).</p>
          ${lessonHtml(lessons.slice(0, 4))}
          <p><button class="stamp" data-goto="playbook">Open Playbook</button></p>
        </div>
        <div class="panel">
          <p class="kicker">3 · Warm</p>
          <p>RunN DEV <strong>${pct(R.run_n && R.run_n.pass_rate)}</strong> vs Run1 ${pct(R.run1 && R.run1.pass_rate)} · cost ${R.run_n && R.run_n.cost} vs ${R.run1 && R.run1.cost} · ${R.promoted ? "PROMOTED" : "HELD"}.</p>
          <p>Hold-out stayed sealed until promote${R.hold_candidate ? ` (prior ${pct(R.hold_prior && R.hold_prior.pass_rate)} → candidate ${pct(R.hold_candidate.pass_rate)})` : ""}.</p>
          <p>Hold-out never trained the playbook.</p>
          ${R.neatlogs_url ? `<p><a href="${R.neatlogs_url}">Open Neatlogs</a></p>` : ""}
        </div>
      </section>`,
      runs: () => `<section>
        <div class="panel"><p class="kicker">Run1 DEV</p><div class="metric">${pct(R.run1 && R.run1.pass_rate)}</div>
          <p>cost ${R.run1 && R.run1.cost} · tokens ${R.run1 && R.run1.tokens}</p></div>
        <div class="panel"><p class="kicker">RunN DEV</p><div class="metric">${pct(R.run_n && R.run_n.pass_rate)}</div>
          <p>cost ${R.run_n && R.run_n.cost} · tokens ${R.run_n && R.run_n.tokens} · ${R.promoted ? "PROMOTED" : "HELD"}</p></div>
      </section>`,
      trace: () => `<section>
        <p class="kicker">Neatlogs is system of record. Spans below are the flushed child tree.</p>
        <div class="panel">
          <p>trace_id ${R.neatlogs_trace_id || "(unset — no NEATLOGS_API_KEY)"}</p>
          <p>${R.neatlogs_url ? `<a href="${R.neatlogs_url}">Open cockpit</a>` : ""}</p>
          <pre>${JSON.stringify(R.children || [], null, 2)}</pre>
        </div>
      </section>`,
      playbook: () => `<section>
        <p class="kicker">Diffable entries after Reflect merge. Candidate until promote.</p>
        <div class="panel"><pre>${(R.playbook_entries || []).map(e => "# " + e.id + "\\n" + e.text).join("\\n\\n") || "empty"}</pre></div>
        <div class="panel"><p class="kicker">Candidate diff</p><pre>${R.diff || ""}</pre></div>
      </section>`,
      journal: () => `<section>
        <p class="kicker">Lessons are playbook text. Pipeline telemetry stays in System log.</p>
        <div class="panel">
          <p class="kicker">Lessons</p>
          ${lessonHtml(lessons)}
        </div>
        ${systemLog.length ? `<details class="panel"><summary>System log — CORE.md / persist_lesson telemetry</summary><pre>${systemLog.join("\\n")}</pre></details>` : ""}
      </section>`,
      promote: () => `<section>
        <p class="kicker">Promote gate is Actor re-eval on frozen JSON. LiveScorer is aux only.</p>
        <div class="panel">
          <p>Decision: <strong>${R.promoted ? "PROMOTED" : "HELD"}</strong></p>
          <p>Hold-out prior ${pct(R.hold_prior && R.hold_prior.pass_rate)} · candidate ${pct(R.hold_candidate && R.hold_candidate.pass_rate)}</p>
          <p>Active ${R.pointer.active} · prior ${R.pointer.prior || "—"} · candidate ${R.pointer.candidate || "—"}</p>
          <p>RedTeam on LIVE: ${R.redteam ? (R.redteam.successes + "/" + R.redteam.n + " pass=" + R.redteam.pass_rate) : "not run"}</p>
          <p>Rollback is the prior pointer. This UI does not re-run the loop.</p>
        </div>
      </section>`
    };
    const main = document.getElementById("main");
    function show(id) {
      document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === id));
      main.innerHTML = pages[id]();
    }
    document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => show(t.dataset.tab)));
    document.addEventListener("click", (ev) => {
      const go = ev.target && ev.target.closest && ev.target.closest("[data-goto]");
      if (go) show(go.dataset.goto);
    });
    show("challenge");
  </script>
</body>
</html>
"""
