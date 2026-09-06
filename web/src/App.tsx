import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type Lesson,
  type Report,
  type TaskRunResult,
  type TraceSpan,
  type VersionSnapshot,
  challengeLessons,
  cockpitHref,
  deltaPct,
  formatCost,
  formatMs,
  formatPct,
  formatTokens,
  ratioBar,
  speedOf,
  taskMatrix,
  toolsOf,
  versionHistory,
} from "./reportView";
import {
  health,
  loadReport,
  postChallenge,
  postRollback,
  postRun,
  type ChallengeResult,
} from "./api";

type Tab = "overview" | "learning" | "trace" | "promote";
type Source = "api" | "local" | "snapshot";

const TABS: { id: Tab; label: string; key: string }[] = [
  { id: "overview", label: "Overview", key: "1" },
  { id: "learning", label: "Learning", key: "2" },
  { id: "trace", label: "Trace", key: "3" },
  { id: "promote", label: "Promote", key: "4" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [report, setReport] = useState<Report | null>(null);
  const [source, setSource] = useState<Source>("snapshot");
  const [error, setError] = useState<string>("");
  const [apiUp, setApiUp] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { report: r, source: s } = await loadReport();
      setReport(r);
      setSource(s);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    health().then((h) => setApiUp(Boolean(h?.ok)));
  }, [refresh]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && ["INPUT", "TEXTAREA"].includes(e.target.tagName))
        return;
      const hit = TABS.find((t) => t.key === e.key);
      if (hit) setTab(hit.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app">
      <Chrome tab={tab} setTab={setTab} report={report} source={source} />
      <main className="frame">
        {!report && !error && <EmptyLoading />}
        {!report && error && <EmptyErr />}
        {report && tab === "overview" && (
          <Overview report={report} source={source} apiUp={apiUp} onGoLearn={() => setTab("learning")} />
        )}
        {report && tab === "learning" && <Learning report={report} apiUp={apiUp} onRefresh={refresh} />}
        {report && tab === "trace" && <Trace report={report} />}
        {report && tab === "promote" && <Promote report={report} apiUp={apiUp} onRefresh={refresh} />}
      </main>
    </div>
  );
}

/* ─────────── Chrome ─────────── */

function Chrome({
  tab,
  setTab,
  report,
  source,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  report: Report | null;
  source: Source;
}) {
  return (
    <header className="chrome">
      <div className="chrome-inner">
        <div className="brand">
          <span className="mark">J</span>
          <span className="name">Journeyman</span>
          <span className="sub">/ apprentice agent</span>
        </div>
        <nav className="tabs" aria-label="Sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={tab === t.id ? "on" : ""}
              onClick={() => setTab(t.id)}
              title={`Press ${t.key}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="chip-row">
          <SourceChip source={source} />
          <span className="chip" title="Active playbook pointer">
            <span className="dot" />
            {report?.pointer.active ?? "v0"}
          </span>
        </div>
      </div>
    </header>
  );
}

function SourceChip({ source }: { source: Source }) {
  if (source === "api") {
    return (
      <span className="chip" title="Connected to Journeyman API">
        <span className="dot live" />
        api · live
      </span>
    );
  }
  if (source === "local") {
    return (
      <span className="chip" title="Serving latest local Python run artifact">
        <span className="dot live" />
        local run
      </span>
    );
  }
  return (
    <span className="chip snap" title="Bundled demo snapshot — deploy API or run Python demo to replace">
      <span className="dot" />
      demo snapshot
    </span>
  );
}

/* ─────────── Overview ─────────── */

function Overview({
  report,
  source,
  apiUp,
  onGoLearn,
}: {
  report: Report;
  source: Source;
  apiUp: boolean;
  onGoLearn: () => void;
}) {
  const lessons = challengeLessons(report);
  const versions = versionHistory(report);
  const cold = report.run1;
  const warm = report.run_n;

  const accDelta = warm.pass_rate - cold.pass_rate;
  const toolDelta = deltaPct(toolsOf(cold), toolsOf(warm));
  const speedDelta = deltaPct(speedOf(cold) || 1, speedOf(warm) || 1);
  const tokenDelta = deltaPct(cold.tokens || 1, warm.tokens || 1);

  const lessonSubjects = pickLessonHeads(lessons);

  return (
    <section className="section">
      <div className="hero">
        <div>
          <p className="repo">{report.repo ?? "arjun7n9s/journeyman-fixture"} · GitHub MCP · read-only</p>
          <h1 className="h1">
            The apprentice <em>learned</em> a repo it had never seen —<br />
            {formatPct(cold.pass_rate)} → <em>{formatPct(warm.pass_rate)}</em> on frozen DEV,
            <br />
            with {Math.abs(parseFloat(tokenDelta))}% fewer tokens.
          </h1>
          <p className="lead" style={{ marginTop: 22, color: "var(--ink-2)" }}>
            Journeyman starts empty. It calls GitHub MCP under a read-only policy, journals every
            failure, distills a diffable playbook, and re-scores itself on the same frozen tasks —
            with a sealed hold-out gate before it promotes.
          </p>
        </div>
        <aside className="hero-side">
          <div className="hero-meta">
            <div className="cell">
              <span className="k">Task family</span>
              <span className="v">repo triage / grounding</span>
            </div>
            <div className="cell">
              <span className="k">Third-party</span>
              <span className="v">github MCP · readonly</span>
            </div>
            <div className="cell">
              <span className="k">Cheap brain</span>
              <span className="v">glm-4-7-flash</span>
            </div>
            <div className="cell">
              <span className="k">Escalate</span>
              <span className="v">gpt-5-nano · gated</span>
            </div>
          </div>
          {(report.neatlogs_trace_id || report.neatlogs_url) && !report.demo_snapshot ? (
            <a href={cockpitHref(report)} className="fine" target="_blank" rel="noreferrer">
              open trace in neatlogs →
            </a>
          ) : report.demo_snapshot ? (
            <span className="fine muted">neatlogs trace — populated on live run</span>
          ) : null}
        </aside>
      </div>

      <div className="section-header">
        <div className="head">
          <span className="kicker">01 · measured gain</span>
          <h2 className="h2">Three metrics, cold vs warm</h2>
        </div>
        <span className="fine">frozen DEV — 10 tasks — same MCP endpoints</span>
      </div>

      <div className="metrics">
        <Metric
          k="accuracy"
          value={formatPct(warm.pass_rate)}
          delta={accDelta >= 0 ? `+${(accDelta * 100).toFixed(1)} pp` : `${(accDelta * 100).toFixed(1)} pp`}
          deltaKind={accDelta > 0 ? "pos" : accDelta < 0 ? "neg" : "flat"}
          from={`from ${formatPct(cold.pass_rate)} · v0`}
          spark={versions.map((v) => v.score.pass_rate)}
          sparkKind="pos"
        />
        <Metric
          k="cost per task"
          value={`${(toolsOf(warm) / Math.max(1, warm.n)).toFixed(1)}`}
          unit="tools/task"
          delta={toolDelta}
          deltaKind={toolsOf(warm) < toolsOf(cold) ? "pos" : toolsOf(warm) > toolsOf(cold) ? "neg" : "flat"}
          from={`from ${(toolsOf(cold) / Math.max(1, cold.n)).toFixed(1)} · ${formatTokens(warm.tokens)} tok · ${formatCost(warm.cost)}`}
          spark={versions.map((v) => v.score.tool_calls / Math.max(1, v.score.n))}
          sparkKind="pos"
          invertSpark
        />
        <Metric
          k="wall latency"
          value={formatMs(speedOf(warm) / Math.max(1, warm.n))}
          unit="p50"
          delta={speedDelta}
          deltaKind={speedOf(warm) < speedOf(cold) ? "pos" : speedOf(warm) > speedOf(cold) ? "neg" : "flat"}
          from={`from ${formatMs(speedOf(cold) / Math.max(1, cold.n))} · v0`}
          spark={versions.map((v) => v.score.speed_ms / Math.max(1, v.score.n))}
          sparkKind="pos"
          invertSpark
        />
      </div>

      <div className="section" style={{ marginTop: 40 }}>
        <div className="section-header">
          <div className="head">
            <span className="kicker">02 · try it</span>
            <h2 className="h2">
              Hand it a task it has <em>never seen</em>.
            </h2>
          </div>
          <span className="fine">
            {apiUp ? "runs against the active playbook via the API" : "start python -m journeyman.server — then retry"}
          </span>
        </div>
        <ChallengeConsole source={source} apiUp={apiUp} activeVersion={report.pointer.active} />
      </div>

      <div className="section" style={{ marginTop: 40 }}>
        <div className="section-header">
          <div className="head">
            <span className="kicker">03 · versions</span>
            <h2 className="h2">The playbook grew, one merge at a time</h2>
          </div>
          <button type="button" className="pill" onClick={onGoLearn}>
            open learning →
          </button>
        </div>
        <VersionTimeline versions={versions} active={report.pointer.active} />
      </div>

      <div className="section" style={{ marginTop: 40 }}>
        <div className="section-header">
          <div className="head">
            <span className="kicker">04 · what it learned</span>
            <h2 className="h2">Facts distilled from GitHub MCP</h2>
          </div>
          <span className="fine">merged from failure traces on the DEV split only</span>
        </div>
        <div className="strip">
          {lessons.map((lesson, i) => (
            <div key={lesson.id + i} className="lesson">
              <span className="head">
                {lessonSubjects[i]?.tag ?? lesson.source} · {lesson.origin ?? "reflect"}
              </span>
              <span className="text">{lesson.text}</span>
              <span className="from">{lessonSubjects[i]?.from ?? `entry ${lesson.id}`}</span>
            </div>
          ))}
          {!lessons.length && (
            <div className="lesson">
              <span className="head">empty</span>
              <span className="text">no distilled lessons in this artifact yet</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function pickLessonHeads(lessons: Lesson[]): { tag: string; from: string }[] {
  return lessons.map((l) => {
    const t = l.text.toLowerCase();
    if (t.includes("dedupe") || t.includes("duplicate"))
      return { tag: "dedupe", from: "fixture: I1↔I9, I4↔I10" };
    if (t.includes("owner") || t.includes("codeowners"))
      return { tag: "owner map", from: "CODEOWNERS · src/**" };
    if (t.includes("stack trace") || t.includes("nil") || t.includes("crash"))
      return { tag: "labeler", from: "CONTRIBUTING.md" };
    if (t.includes("search") || t.includes("list"))
      return { tag: "policy", from: "search-before-list" };
    if (t.includes("area:") || t.includes("type:"))
      return { tag: "taxonomy", from: "labels API" };
    return { tag: l.source, from: `entry ${l.id}` };
  });
}

/* ─────────── Metric card ─────────── */

function Metric({
  k,
  value,
  unit,
  from,
  delta,
  deltaKind,
  spark,
  sparkKind,
  invertSpark,
}: {
  k: string;
  value: string;
  unit?: string;
  from: string;
  delta: string;
  deltaKind: "pos" | "neg" | "flat";
  spark: number[];
  sparkKind: "pos" | "neg";
  invertSpark?: boolean;
}) {
  const arrow = deltaKind === "pos" ? "↑" : deltaKind === "neg" ? "↓" : "→";
  return (
    <div className="metric">
      <span className="k">{k}</span>
      <span className="v">
        {value}
        {unit ? <span className="unit">{unit}</span> : null}
      </span>
      <span className={`delta ${deltaKind}`}>
        {arrow} {delta}
      </span>
      <span className="from">{from}</span>
      <div className="spark">
        <Spark values={spark} kind={sparkKind} invert={invertSpark} />
      </div>
    </div>
  );
}

function Spark({ values, kind, invert }: { values: number[]; kind: "pos" | "neg"; invert?: boolean }) {
  if (values.length < 2) return null;
  const max = Math.max(...values) || 1;
  const min = Math.min(...values);
  const span = max - min || max;
  return (
    <div className="spark-wrap">
      {values.map((v, i) => {
        const norm = span ? (v - min) / span : 0.5;
        const h = invert ? 1 - norm : norm;
        const heightPct = 25 + h * 75;
        const isLast = i === values.length - 1;
        return (
          <span
            key={i}
            className={`bar ${isLast ? "active" : ""} ${kind}`}
            style={{ height: `${heightPct}%` }}
          />
        );
      })}
    </div>
  );
}

/* ─────────── Challenge console ─────────── */

const CHALLENGE_PRESETS: {
  label: string;
  task_type: string;
  prompt: string;
  body: string;
  target?: string;
}[] = [
  {
    label: "label a fresh bug",
    task_type: "label",
    prompt: "What labels should this issue get, using this repo's taxonomy?",
    body: "Title: Panic on nil ctx in worker\nBody: We see a crash loop with a stack trace pointing at src/runtime/worker.py:88 when ctx becomes nil during shutdown.",
  },
  {
    label: "owner of a file",
    task_type: "owner",
    prompt: "Who is the logical owner of this file?",
    body: "src/billing/charge.py",
    target: "src/billing/charge.py",
  },
  {
    label: "duplicate check",
    task_type: "duplicate",
    prompt: "Is this issue a duplicate? If so, of which existing issue?",
    body: "Title: REST handler 500 on null JSON\nBody: POST /v1/things with a null body returns a 500 from src/api/routes.py.",
  },
  {
    label: "summarize open bugs",
    task_type: "summarize",
    prompt: "Summarize the open bugs in area:api. Cite issue numbers.",
    body: "",
  },
];

function ChallengeConsole({
  source,
  apiUp,
  activeVersion,
}: {
  source: Source;
  apiUp: boolean;
  activeVersion: string;
}) {
  const [taskType, setTaskType] = useState<string>(CHALLENGE_PRESETS[0].task_type);
  const [prompt, setPrompt] = useState<string>(CHALLENGE_PRESETS[0].prompt);
  const [body, setBody] = useState<string>(CHALLENGE_PRESETS[0].body);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const [error, setError] = useState<string>("");

  const usePreset = (p: (typeof CHALLENGE_PRESETS)[number]) => {
    setTaskType(p.task_type);
    setPrompt(p.prompt);
    setBody(p.body);
    setResult(null);
    setError("");
  };

  const submit = async () => {
    if (!prompt.trim()) return;
    setPending(true);
    setError("");
    setResult(null);
    try {
      const r = await postChallenge({
        prompt,
        task_type: taskType || undefined,
        body: body || undefined,
      });
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  };

  const apiOff = !apiUp;

  return (
    <div className="console">
      <div className="console-inputs">
        <div className="preset-row">
          {CHALLENGE_PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              className="chip"
              onClick={() => usePreset(p)}
              disabled={pending}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="console-grid">
          <label className="field">
            <span className="k">task type</span>
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
              disabled={pending}
            >
              <option value="">— any —</option>
              <option value="label">label</option>
              <option value="owner">owner</option>
              <option value="duplicate">duplicate</option>
              <option value="summarize">summarize</option>
              <option value="fix_pr">fix_pr</option>
            </select>
          </label>
          <label className="field">
            <span className="k">prompt</span>
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="What labels should this issue get?"
              disabled={pending}
            />
          </label>
        </div>
        <label className="field">
          <span className="k">context (issue body, file path, etc.)</span>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Paste an issue title + body, or a file path…"
            rows={4}
            disabled={pending}
          />
        </label>
        <div className="console-actions">
          <button
            type="button"
            className="btn primary"
            onClick={submit}
            disabled={pending || apiOff || !prompt.trim()}
            title={apiOff ? "connect the API to run" : "run against active playbook"}
          >
            {pending ? "running…" : "→ run through actor"}
          </button>
          <span className="fine">
            active: <span className="mono">{activeVersion}</span> ·{" "}
            {apiOff
              ? "no API — displaying " + (source === "snapshot" ? "demo snapshot" : "local report")
              : "hitting /api/challenge"}
          </span>
        </div>
        {error ? (
          <p className="fine" style={{ color: "var(--neg)" }}>
            {error}
          </p>
        ) : null}
      </div>

      {result ? <ChallengeResultCard result={result} /> : apiOff ? <ChallengeHint /> : null}
    </div>
  );
}

function ChallengeHint() {
  return (
    <div className="console-result muted">
      <span className="kicker">how to enable</span>
      <p className="fine">
        The try-it console talks to <code>POST /api/challenge</code> on the Python backend. Start{" "}
        <code>python -m journeyman.server</code> (port 8787) and refresh — Vite proxies it.
      </p>
    </div>
  );
}

function formatActorAnswer(answer: unknown, text: string): string {
  if (typeof answer === "string" && answer.trim()) return answer;
  if (answer && typeof answer === "object") {
    const rec = answer as Record<string, unknown>;
    const bits = [rec.labels, rec.owner, rec.duplicate, rec.pr, rec.text]
      .flat()
      .filter((value) => value !== undefined && value !== null && String(value).trim() && String(value) !== "undefined");
    if (bits.length) return bits.map(String).join(" · ");
  }
  const first = (text || "")
    .split("\n")
    .find((line) => line.trim() && !line.startsWith("From repo") && !line.includes("{'found'"));
  return first?.trim() || text || JSON.stringify(answer, null, 2);
}

function ChallengeResultCard({ result }: { result: ChallengeResult }) {
  const r = result.result;
  const answerText = formatActorAnswer(r.answer, r.text);
  return (
    <div className="console-result">
      <div className="console-result-head">
        <span className="kicker">agent answer</span>
        <div className="row">
          <span className="pill">{result.playbook_version}</span>
          <span className="pill">{r.model || "cheap"}</span>
          {r.escalated ? <span className="pill amber">escalated</span> : null}
        </div>
      </div>
      <pre className="pre">{answerText}</pre>
      <div className="console-result-meta">
        <div className="kv">
          <span className="k">tools</span>
          <span className="v">{r.tool_calls}</span>
        </div>
        <div className="kv">
          <span className="k">tokens</span>
          <span className="v">{formatTokens(r.tokens)}</span>
        </div>
        <div className="kv">
          <span className="k">cost</span>
          <span className="v">{formatCost(r.cost)}</span>
        </div>
        <div className="kv">
          <span className="k">latency</span>
          <span className="v">{formatMs(r.speed_ms)}</span>
        </div>
      </div>
      {r.rule_hits && r.rule_hits.length ? (
        <div>
          <span className="kicker" style={{ display: "block", marginTop: 12 }}>
            rules fired
          </span>
          <ul className="lessons">
            {r.rule_hits.map((h, i) => (
              <li key={i}>
                <code>{h.rule_id}</code> — {h.why}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {r.playbook_hits && r.playbook_hits.length ? (
        <div>
          <span className="kicker" style={{ display: "block", marginTop: 12 }}>
            playbook hits
          </span>
          <div className="row wrap">
            {r.playbook_hits.map((h, i) => (
              <span key={i} className="pill">
                {h}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {r.spans && r.spans.length ? (
        <div>
          <span className="kicker" style={{ display: "block", marginTop: 12 }}>
            spans
          </span>
          <ol className="mini-spans">
            {r.spans.map((s, i) => (
              <li key={i}>
                <span className="k">{s.kind}</span>
                <span className="n">{s.name}</span>
                <span className="dur">{s.duration_ms ? formatMs(s.duration_ms) : ""}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}

/* ─────────── Version timeline ─────────── */

function VersionTimeline({ versions, active }: { versions: VersionSnapshot[]; active: string }) {
  return (
    <div className="timeline">
      {versions.map((v) => (
        <div key={v.version} className={`node ${v.version === active ? "active" : ""}`}>
          <span className="tag">
            <span className="mono">{v.version}</span>
            <span>·</span>
            <span>{v.when}</span>
          </span>
          <span className="ver">{formatPct(v.score.pass_rate)}</span>
          <span className="why">{v.lesson ?? v.trigger ?? "—"}</span>
          <span className="pass">
            <strong>{v.score.successes}/{v.score.n}</strong> pass · {v.score.tool_calls}t · {formatTokens(v.score.tokens)}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─────────── Learning surface ─────────── */

function Learning({ report, apiUp, onRefresh }: { report: Report; apiUp: boolean; onRefresh: () => void }) {
  const versions = versionHistory(report);
  const devIds = DEV_IDS;
  const holdIds = HOLD_IDS;
  const coldMap = taskMatrix(report.task_results?.run1, devIds);
  const warmMap = taskMatrix(report.task_results?.run_n, devIds);
  const holdPrior = taskMatrix(report.task_results?.hold_prior, holdIds);
  const holdCand = taskMatrix(report.task_results?.hold_candidate, holdIds);
  const [running, setRunning] = useState(false);
  const [runErr, setRunErr] = useState("");

  const triggerRun = async () => {
    setRunning(true);
    setRunErr("");
    try {
      await postRun("offline");
      await onRefresh();
    } catch (e) {
      setRunErr((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="section">
      <div className="section-header">
        <div className="head">
          <span className="kicker">learning loop</span>
          <h2 className="h2">
            Each version is a <em>merge</em> triggered by a specific failure.
          </h2>
          <p className="fine" style={{ maxWidth: "52ch" }}>
            Reflect reads only DEV failure traces (never hold-out), synthesizes a diffable playbook
            entry, and re-scores. If DEV improves, the sealed hold-out is unlocked as a gate.
          </p>
        </div>
        <div className="stack" style={{ alignItems: "flex-end" }}>
          <button
            type="button"
            className="btn primary"
            onClick={triggerRun}
            disabled={!apiUp || running}
            title={!apiUp ? "start python -m journeyman.server" : "run the full DEV loop"}
          >
            {running ? "loop running…" : "→ run learning loop"}
          </button>
          {runErr ? (
            <span className="fine" style={{ color: "var(--neg)" }}>
              {runErr}
            </span>
          ) : (
            <span className="fine">
              {apiUp ? "cold → reflect → warm → hold-out" : "API not connected — view-only"}
            </span>
          )}
        </div>
      </div>

      <div className="two-col">
        <div className="stack">
          {versions.map((v, i) => (
            <VersionCard key={v.version} snapshot={v} prev={versions[i - 1]} />
          ))}
        </div>

        <div className="stack">
          <div className="panel">
            <div className="panel-title">
              <span className="kicker">DEV split · 10 tasks</span>
              <span className="fine">
                {countPass(warmMap, devIds)}/{devIds.length} pass
              </span>
            </div>
            <div className="matrix">
              <MatrixRow label="cold · v0" ids={devIds} map={coldMap} compareTo={warmMap} kind="before" />
              <MatrixRow label={`warm · ${report.pointer.active}`} ids={devIds} map={warmMap} compareTo={coldMap} kind="after" />
            </div>
            <div className="legend">
              <span className="swatch">
                <span className="sq pass" /> pass
              </span>
              <span className="swatch">
                <span className="sq fail" /> fail
              </span>
              <span className="swatch">
                <span className="sq flip" /> flipped after merge
              </span>
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">
              <span className="kicker">hold-out · sealed</span>
              <span className="fine">
                unlocked only at promote · {countPass(holdCand, holdIds)}/{holdIds.length} pass
              </span>
            </div>
            <div className="matrix">
              <MatrixRow label="prior" ids={holdIds} map={holdPrior} compareTo={holdCand} kind="before" />
              <MatrixRow label="candidate" ids={holdIds} map={holdCand} compareTo={holdPrior} kind="after" />
            </div>
            <p className="fine" style={{ marginTop: 10 }}>
              Hold-out traces never enter reflection or the playbook. Scored once, at promote.
            </p>
          </div>
        </div>
      </div>

      <div className="section-header" style={{ marginTop: 40 }}>
        <div className="head">
          <span className="kicker">playbook diff</span>
          <h2 className="h2">What Reflect merged</h2>
        </div>
        <span className="fine">{report.diff_path || "playbook diff"}</span>
      </div>
      <div className="panel flush">
        <Diff text={report.diff || "(no diff — empty run)"} />
      </div>
    </section>
  );
}

function countPass(map: Map<string, boolean>, ids: string[]): number {
  let n = 0;
  for (const id of ids) if (map.get(id)) n++;
  return n;
}

function MatrixRow({
  label,
  ids,
  map,
  compareTo,
  kind,
}: {
  label: string;
  ids: string[];
  map: Map<string, boolean>;
  compareTo: Map<string, boolean>;
  kind: "before" | "after";
}) {
  return (
    <div className="matrix-row">
      <span className="k">{label}</span>
      <div className="matrix-cells">
        {ids.map((id) => {
          const now = map.get(id);
          const other = compareTo.get(id);
          let cls = "cell";
          if (now === true) cls += " pass";
          else if (now === false) cls += " fail";
          if (kind === "after" && now === true && other === false) cls = "cell flip";
          const short = id.replace(/^(dev|hold)-0?/, "");
          return (
            <span key={id} className={cls} title={`${id} ${now === undefined ? "?" : now ? "pass" : "fail"}`}>
              {short}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function VersionCard({ snapshot, prev }: { snapshot: VersionSnapshot; prev: VersionSnapshot | undefined }) {
  const passDelta = prev ? (snapshot.score.pass_rate - prev.score.pass_rate) * 100 : 0;
  const toolDelta = prev ? snapshot.score.tool_calls - prev.score.tool_calls : 0;
  const passSign = passDelta >= 0 ? "+" : "";
  const toolSign = toolDelta >= 0 ? "+" : "";
  return (
    <article className="version-card">
      <div className="rail">
        <span className="ver">{snapshot.version}</span>
        <span className="when">{snapshot.when}</span>
        <span className="when" style={{ marginTop: 6 }}>
          {snapshot.playbook_size} rules
        </span>
      </div>
      <div className="body">
        <div>
          <span className="kicker" style={{ marginBottom: 6 }}>
            trigger
          </span>
          <div className="why">{snapshot.trigger ?? "—"}</div>
        </div>
        {snapshot.lesson ? (
          <div>
            <span className="kicker" style={{ marginBottom: 6 }}>
              merged lesson
            </span>
            <div className="why">{snapshot.lesson}</div>
          </div>
        ) : null}
        {snapshot.evidence ? (
          <div className="evidence">
            <span className="lbl">{snapshot.evidence.label}</span>
            <span>
              {snapshot.evidence.refs.map((r) => (
                <code key={r} style={{ marginRight: 6 }}>
                  {r}
                </code>
              ))}
            </span>
          </div>
        ) : null}
        <div className="row-metrics">
          <span>
            DEV <strong>{formatPct(snapshot.score.pass_rate)}</strong>
            {prev ? (
              <span style={{ color: passDelta >= 0 ? "var(--pos)" : "var(--neg)", marginLeft: 6 }}>
                {passSign}
                {passDelta.toFixed(1)}pp
              </span>
            ) : null}
          </span>
          <span>
            tools <strong>{snapshot.score.tool_calls}</strong>
            {prev ? (
              <span style={{ color: toolDelta <= 0 ? "var(--pos)" : "var(--neg)", marginLeft: 6 }}>
                {toolSign}
                {toolDelta}
              </span>
            ) : null}
          </span>
          <span>
            tokens <strong>{formatTokens(snapshot.score.tokens)}</strong>
          </span>
          <span>
            speed <strong>{formatMs(snapshot.score.speed_ms / Math.max(1, snapshot.score.n))}</strong>
          </span>
        </div>
      </div>
    </article>
  );
}

/* ─────────── Trace surface ─────────── */

function Trace({ report }: { report: Report }) {
  const spans: TraceSpan[] = (report.children || []) as TraceSpan[];
  const [selectedIdx, setSelected] = useState(0);
  const maxDur = useMemo(() => {
    let m = 0;
    for (const s of spans) m = Math.max(m, s.duration_ms ?? 0);
    return m;
  }, [spans]);
  const totalDur = useMemo(() => spans.reduce((a, s) => a + (s.duration_ms ?? 0), 0), [spans]);
  const totalCost = useMemo(() => spans.reduce((a, s) => a + (s.cost ?? 0), 0), [spans]);
  const totalTokens = useMemo(() => spans.reduce((a, s) => a + (s.tokens ?? 0), 0), [spans]);

  const sel = spans[selectedIdx];

  const coldTaskSample = pickSampleTask(report.task_results?.run1, "dev-05");
  const warmTaskSample = pickSampleTask(report.task_results?.run_n, "dev-05");

  return (
    <section className="section">
      <div className="section-header">
        <div className="head">
          <span className="kicker">execution trace</span>
          <h2 className="h2">
            <em>One task</em>, decomposed. Kind, cost, and router route per span.
          </h2>
          <p className="fine" style={{ maxWidth: "56ch" }}>
            Every hop is under the read-only GitHub MCP policy. The router prefers the cheap brain
            and only escalates on a logged quality-gate miss.
          </p>
        </div>
        <span className="fine">
          total {formatMs(totalDur)} · {formatCost(totalCost)} · {formatTokens(totalTokens)} tok
        </span>
      </div>

      <div className="trace">
        <div className="panel flush">
          <div className="wf-header">
            <span />
            <span>span</span>
            <span style={{ textAlign: "right" }}>ms</span>
            <span style={{ textAlign: "right" }}>tok</span>
            <span>latency</span>
          </div>
          {spans.length === 0 && (
            <div style={{ padding: 24, color: "var(--ink-4)", fontSize: 13 }}>
              no spans in this artifact
            </div>
          )}
          {spans.map((s, i) => (
            <div
              key={i}
              className={`wf-row ${i === selectedIdx ? "sel" : ""}`}
              onClick={() => setSelected(i)}
            >
              <span className={`kind ${kindClass(s.kind)}`} />
              <span className="name">
                <span className="n">{s.name}</span>
                <span className="k">
                  {s.kind}
                  {s.route ? ` · ${s.route}` : ""}
                </span>
              </span>
              <span className="n-mono">{s.duration_ms ? formatMs(s.duration_ms) : "—"}</span>
              <span className="n-mono dim">{s.tokens ? formatTokens(s.tokens) : "—"}</span>
              <span className="wf-bar">
                <span
                  className={`fill ${kindClass(s.kind)}`}
                  style={{ width: `${ratioBar(s.duration_ms ?? 0, maxDur || 1) * 100}%` }}
                />
              </span>
            </div>
          ))}
        </div>

        <aside className="trace-side">
          <div className="panel">
            <div className="panel-title">
              <span className="kicker">selected span</span>
              {sel?.route ? (
                <span className={`pill ${sel.route === "escalate" ? "amber" : ""}`}>
                  {sel.route === "escalate" ? "escalated" : "cheap"}
                </span>
              ) : null}
            </div>
            {sel ? (
              <>
                <div className="kv">
                  <span className="k">name</span>
                  <span className="v">{sel.name}</span>
                </div>
                <div className="kv">
                  <span className="k">kind</span>
                  <span className="v">{sel.kind}</span>
                </div>
                {sel.model ? (
                  <div className="kv">
                    <span className="k">model</span>
                    <span className="v">{sel.model}</span>
                  </div>
                ) : null}
                {sel.duration_ms !== undefined ? (
                  <div className="kv">
                    <span className="k">latency</span>
                    <span className="v">{formatMs(sel.duration_ms)}</span>
                  </div>
                ) : null}
                {sel.cost !== undefined ? (
                  <div className="kv">
                    <span className="k">cost</span>
                    <span className="v">{formatCost(sel.cost)}</span>
                  </div>
                ) : null}
                {sel.tokens !== undefined ? (
                  <div className="kv">
                    <span className="k">tokens</span>
                    <span className="v">{formatTokens(sel.tokens)}</span>
                  </div>
                ) : null}
                {sel.input !== undefined ? (
                  <div>
                    <span className="kicker" style={{ marginTop: 10, display: "block" }}>
                      input
                    </span>
                    <pre className="pre">{previewValue(sel.input)}</pre>
                  </div>
                ) : null}
                {sel.output !== undefined ? (
                  <div>
                    <span className="kicker" style={{ marginTop: 10, display: "block" }}>
                      output
                    </span>
                    <pre className="pre">{previewValue(sel.output)}</pre>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="fine">select a span to inspect</p>
            )}
          </div>

          <div className="panel">
            <div className="panel-title">
              <span className="kicker">policy</span>
              <span className="pill">readonly · github MCP</span>
            </div>
            <p className="fine">
              14 tools allowed · 42 denied by pattern. Any write attempt is blocked before egress.
            </p>
          </div>
        </aside>
      </div>

      <div className="section" style={{ marginTop: 40 }}>
        <div className="section-header">
          <div className="head">
            <span className="kicker">same task · v0 vs vN</span>
            <h2 className="h2">
              What the playbook <em>saves</em>: fewer hops, tighter answer.
            </h2>
          </div>
        </div>
        <div className="compare">
          <TaskCompareSide title="v0 · cold" task={coldTaskSample} />
          <TaskCompareSide title={`${report.pointer.active} · warm`} task={warmTaskSample} />
        </div>
      </div>
    </section>
  );
}

function pickSampleTask(results: TaskRunResult[] | undefined, id: string): TaskRunResult | undefined {
  if (!results) return undefined;
  return results.find((r) => r.id === id) ?? results[0];
}

function previewValue(v: unknown): string {
  if (typeof v === "string") return v.length > 500 ? v.slice(0, 500) + "…" : v;
  const json = JSON.stringify(v, null, 2);
  return json.length > 600 ? json.slice(0, 600) + "…" : json;
}

function kindClass(kind: string): string {
  const k = (kind || "").toLowerCase();
  if (k.includes("mcp") || k.includes("tool")) return "mcp";
  if (k.includes("model") || k.includes("chat") || k.includes("actor")) return "model";
  if (k.includes("cache") || k.includes("retriev") || k.includes("embed")) return "cache";
  if (k.includes("reflect") || k.includes("patch")) return "reflect";
  if (k.includes("policy") || k.includes("gate")) return "policy";
  return "";
}

function TaskCompareSide({ title, task }: { title: string; task: TaskRunResult | undefined }) {
  return (
    <div className="side">
      <div className="title">
        <div className="row">
          <span className="kicker">{title}</span>
          {task ? (
            <span className={`pill ${task.passed ? "pos" : "neg"}`}>{task.passed ? "pass" : "fail"}</span>
          ) : null}
        </div>
        <span className="fine">
          {task ? `${task.tool_calls ?? task.spans?.length ?? 0} tools · ${formatMs(task.duration_ms)} · ${formatTokens(task.tokens)} tok` : "—"}
        </span>
      </div>
      {task?.spans && task.spans.length ? (
        <ul>
          {task.spans.map((s, i) => (
            <li key={i}>
              <span className="idx">{String(i + 1).padStart(2, "0")}</span>
              <span>{s.name}</span>
              <span className="dur">{s.duration_ms ? formatMs(s.duration_ms) : ""}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="fine">no per-task span breakdown in this artifact</p>
      )}
      {task ? (
        <div style={{ marginTop: 12 }}>
          <span className="kicker" style={{ display: "block", marginBottom: 6 }}>
            answer
          </span>
          <pre className="pre">{previewValue(task.answer ?? "(no answer captured)")}</pre>
        </div>
      ) : null}
    </div>
  );
}

/* ─────────── Promote surface ─────────── */

function Promote({ report, apiUp, onRefresh }: { report: Report; apiUp: boolean; onRefresh: () => void }) {
  const devImproved = report.run_n.pass_rate >= report.run1.pass_rate && report.run_n.pass_rate > 0;
  const holdOK =
    report.hold_candidate !== null &&
    (report.hold_prior === null || report.hold_candidate.pass_rate >= report.hold_prior.pass_rate);
  const redteamOK = report.redteam === null || report.redteam.pass_rate >= 0.6;
  const [rolling, setRolling] = useState(false);
  const [rollErr, setRollErr] = useState("");

  const canRollback = !!report.pointer.prior;

  const doRollback = async () => {
    if (!canRollback) return;
    setRolling(true);
    setRollErr("");
    try {
      await postRollback();
      await onRefresh();
    } catch (e) {
      setRollErr((e as Error).message);
    } finally {
      setRolling(false);
    }
  };

  return (
    <section className="section">
      <div className="section-header">
        <div className="head">
          <span className="kicker">promote gate</span>
          <h2 className="h2">
            <em>Ship the playbook</em> only if every gate holds.
          </h2>
          <p className="fine" style={{ maxWidth: "56ch" }}>
            The active pointer is a version, not a build. Rollback restores prior in one write.
            Hold-out is a task set, not hidden issues — the actor could list the repo, but the
            harness never runs hold-out until this moment.
          </p>
        </div>
        <div className="stack" style={{ alignItems: "flex-end" }}>
          <span className={`pill ${report.promoted ? "pos" : "amber"}`}>
            {report.promoted ? "promoted" : "held"}
          </span>
          <button
            type="button"
            className="btn ghost"
            onClick={doRollback}
            disabled={!apiUp || !canRollback || rolling}
            title={
              !apiUp
                ? "start python -m journeyman.server"
                : canRollback
                  ? `restore ${report.pointer.prior}`
                  : "no prior version to roll back to"
            }
          >
            {rolling ? "rolling back…" : canRollback ? `↺ rollback to ${report.pointer.prior}` : "↺ rollback"}
          </button>
          {rollErr ? (
            <span className="fine" style={{ color: "var(--neg)" }}>
              {rollErr}
            </span>
          ) : null}
        </div>
      </div>

      <div className="pointer-line">
        <div className="p">
          <span className="k">prior</span>
          <span className="v">{report.pointer.prior ?? "—"}</span>
        </div>
        <div className={`p ${report.promoted ? "active" : ""}`}>
          <span className="k">active</span>
          <span className="v">{report.pointer.active}</span>
        </div>
        <div className="p">
          <span className="k">candidate</span>
          <span className="v">{report.pointer.candidate ?? report.candidate_version ?? "—"}</span>
        </div>
      </div>

      <div className="section" style={{ marginTop: 32 }}>
        <div className="gate">
          <GateRow
            on={devImproved}
            title="DEV pass rate did not regress"
            sub={`${report.run1.successes}/${report.run1.n} → ${report.run_n.successes}/${report.run_n.n}`}
            n={`${formatPct(report.run1.pass_rate)} → ${formatPct(report.run_n.pass_rate)}`}
          />
          <GateRow
            on={holdOK}
            title="Sealed hold-out held or improved"
            sub={
              report.hold_prior && report.hold_candidate
                ? `${report.hold_prior.successes}/${report.hold_prior.n} prior → ${report.hold_candidate.successes}/${report.hold_candidate.n} candidate`
                : report.hold_candidate
                  ? `first candidate: ${report.hold_candidate.successes}/${report.hold_candidate.n}`
                  : "not scored — DEV did not improve"
            }
            n={
              report.hold_candidate
                ? `${formatPct(report.hold_prior?.pass_rate)} → ${formatPct(report.hold_candidate.pass_rate)}`
                : "—"
            }
          />
          <GateRow
            on={redteamOK}
            title="Red-team on LIVE"
            sub={
              report.redteam
                ? `${report.redteam.successes}/${report.redteam.n} pass under adversarial prefixes`
                : "not run — pre-promote"
            }
            n={report.redteam ? formatPct(report.redteam.pass_rate) : "—"}
          />
          <GateRow
            on={true}
            title="Hold-out traces never trained the playbook"
            sub="TraceIngest.poll drops session_id==test, split=holdout, prompt_variant=candidate"
            n="invariant"
          />
        </div>
      </div>
    </section>
  );
}

function GateRow({ on, title, sub, n }: { on: boolean; title: string; sub: string; n: string }) {
  return (
    <div className={`gate-row ${on ? "on" : "off"}`}>
      <span className="mark">{on ? "✓" : "×"}</span>
      <span className="msg">
        {title}
        <span className="sub">{sub}</span>
      </span>
      <span className="n">{n}</span>
    </div>
  );
}

/* ─────────── Diff renderer ─────────── */

function Diff({ text }: { text: string }) {
  const lines = text.split(/\r?\n/);
  return (
    <div className="diff">
      {lines.map((line, i) => {
        if (line.startsWith("+++") || line.startsWith("---")) {
          return (
            <span key={i} className="hunk">
              {line}
            </span>
          );
        }
        if (line.startsWith("+")) {
          return (
            <span key={i} className="add">
              {line}
            </span>
          );
        }
        if (line.startsWith("-")) {
          return (
            <span key={i} className="del">
              {line}
            </span>
          );
        }
        if (line.startsWith("@@")) {
          return (
            <span key={i} className="hunk">
              {line}
            </span>
          );
        }
        return <span key={i}>{line || " "}</span>;
      })}
    </div>
  );
}

/* ─────────── Empty states ─────────── */

function EmptyLoading() {
  return (
    <div className="empty-state">
      <span className="kicker">loading</span>
      <p className="lead">Reading last-report.json…</p>
    </div>
  );
}

function EmptyErr() {
  return (
    <div className="empty-state">
      <span className="kicker">no artifact</span>
      <h2 className="h2">Nothing to show yet</h2>
      <p className="fine">
        This shell reads an artifact — it doesn’t run the loop. Generate one from the Python
        source of truth.
      </p>
      <code>python -m journeyman.demo.run --challenge frozen --mode offline</code>
      <p className="fine">Then refresh.</p>
    </div>
  );
}

/* ─────────── Constants ─────────── */

const DEV_IDS: string[] = [
  "dev-01",
  "dev-02",
  "dev-03",
  "dev-04",
  "dev-05",
  "dev-06",
  "dev-07",
  "dev-08",
  "dev-09",
  "dev-10",
];

const HOLD_IDS: string[] = ["hold-01", "hold-02", "hold-03", "hold-04", "hold-05", "hold-06"];

