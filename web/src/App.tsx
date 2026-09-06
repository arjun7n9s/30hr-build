import { useEffect, useState, type ReactNode } from "react";
import {
  type Lesson,
  type Report,
  type Score,
  challengeLessons,
  journalLessons,
  deltaLabel,
  formatCost,
  formatPct,
  humanLessons,
  isWeakPlaybook,
  systemLogLines,
  toolsOf,
} from "./reportView";

type Tab = "challenge" | "runs" | "playbook" | "journal" | "traces" | "promote";

const TABS: { id: Tab; label: string }[] = [
  { id: "challenge", label: "Challenge" },
  { id: "runs", label: "Runs" },
  { id: "traces", label: "Trace" },
  { id: "playbook", label: "Playbook" },
  { id: "journal", label: "Journal" },
  { id: "promote", label: "Promote" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("challenge");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/last-report.json")
      .then(async (res) => {
        if (!res.ok) throw new Error("no last-report.json — run python -m journeyman.demo.run");
        return (await res.json()) as Report;
      })
      .then(setReport)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="app">
      <div className="shell">
        <header className="top">
          <div>
            <p className="kicker">Python source of truth · artifact reader</p>
            <h1>Journeyman</h1>
          </div>
          <div className="meta">
            <div>{report?.repo ?? "arjun7n9s/journeyman-fixture"}</div>
            <div>mode {report?.mode ?? "—"}</div>
            <div>active {report?.pointer.active ?? "—"}</div>
          </div>
        </header>

        <nav className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={`tab ${tab === item.id ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {error && (
          <p className="err">
            {error}. This shell does not run the loop. Use{" "}
            <code>python -m journeyman.demo.run --challenge frozen --mode offline</code>.
          </p>
        )}

        {report && tab === "challenge" && <Challenge report={report} onOpenPlaybook={() => setTab("playbook")} />}
        {report && tab === "runs" && <Runs report={report} />}
        {report && tab === "playbook" && <Playbook report={report} />}
        {report && tab === "journal" && <Journal report={report} />}
        {report && tab === "traces" && <Traces report={report} />}
        {report && tab === "promote" && <Promote report={report} />}
      </div>
    </div>
  );
}

function Challenge({ report, onOpenPlaybook }: { report: Report; onOpenPlaybook: () => void }) {
  const lessons = challengeLessons(report);
  const cold = report.run1;
  const warm = report.run_n;
  const passDelta = deltaLabel(cold.pass_rate, warm.pass_rate);
  const costDelta = deltaLabel(cold.cost, warm.cost, { invert: true });
  const toolDelta = deltaLabel(toolsOf(cold), toolsOf(warm), { invert: true });
  const startedWeak =
    (report.pointer.prior ?? "weak-0").toLowerCase().startsWith("weak") ||
    isWeakPlaybook({ ...report, pointer: { ...report.pointer, active: report.pointer.prior ?? "weak-0" } });

  return (
    <section>
      <p className="kicker">
        Challenge {report.challenge_id} · {report.repo} · Cold → Learn → Warm
      </p>
      <p className="seal">Hold-out never trained the playbook.</p>

      <div className="story">
        <article className="step">
          <p className="kicker">1 · Cold</p>
          <h2>Run1 DEV, empty playbook</h2>
          <p className="lede">
            First pass on frozen DEV with {startedWeak ? "a weak / empty playbook" : "the prior playbook"}.
          </p>
          <ScoreLine score={cold} />
          <p className="fine">
            {cold.successes}/{cold.n} passed · playbook {report.pointer.prior ?? "weak-0"}
          </p>
        </article>

        <article className="step">
          <p className="kicker">2 · Learn</p>
          <h2>Human lessons from the playbook</h2>
          <LessonList
            lessons={lessons}
            empty={
              <>
                No human lessons in this artifact. Run{" "}
                <code>python -m journeyman.demo.run --challenge frozen --mode offline</code> then refresh.
              </>
            }
          />
          <button type="button" className="ghost" onClick={onOpenPlaybook}>
            Open Playbook
          </button>
        </article>

        <article className="step">
          <p className="kicker">3 · Warm</p>
          <h2>RunN vs Run1</h2>
          <p className="lede">
            DEV pass {arrow(passDelta)} · cost {arrow(costDelta)} · tools {arrow(toolDelta)}. Hold-out stayed sealed
            until promote.
          </p>
          <Scoreboard run1={cold} runN={warm} promoted={report.promoted} />
          <p className="fine">
            {report.hold_candidate
              ? `Hold-out scored only at promote: prior ${formatPct(report.hold_prior?.pass_rate)} → candidate ${formatPct(report.hold_candidate.pass_rate)}.`
              : "Hold-out sealed until a candidate improves DEV."}{" "}
            Hold-out never trained the playbook.
          </p>
          {report.neatlogs_url ? (
            <p>
              <a href={report.neatlogs_url}>Open Neatlogs</a>
            </p>
          ) : null}
        </article>
      </div>
    </section>
  );
}

function ScoreLine({ score }: { score: Score }) {
  return (
    <p className="score-line">
      <strong>{formatPct(score.pass_rate)}</strong> pass · cost {formatCost(score.cost)} · {toolsOf(score)} tools ·{" "}
      {score.tokens} tok
    </p>
  );
}

function Scoreboard({ run1, runN, promoted }: { run1: Score; runN: Score; promoted: boolean }) {
  const rows: { label: string; a: string; b: string; note: string }[] = [
    {
      label: "DEV pass",
      a: `${formatPct(run1.pass_rate)} (${run1.successes}/${run1.n})`,
      b: `${formatPct(runN.pass_rate)} (${runN.successes}/${runN.n})`,
      note: arrow(deltaLabel(run1.pass_rate, runN.pass_rate)),
    },
    {
      label: "Cost",
      a: formatCost(run1.cost),
      b: formatCost(runN.cost),
      note: arrow(deltaLabel(run1.cost, runN.cost, { invert: true })),
    },
    {
      label: "Tools",
      a: String(toolsOf(run1)),
      b: String(toolsOf(runN)),
      note: arrow(deltaLabel(toolsOf(run1), toolsOf(runN), { invert: true })),
    },
  ];
  return (
    <table className="board">
      <thead>
        <tr>
          <th></th>
          <th>Run1 cold</th>
          <th>RunN warm</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td>{row.label}</td>
            <td>{row.a}</td>
            <td>
              <strong>{row.b}</strong>
            </td>
            <td className="hold">{row.note}</td>
          </tr>
        ))}
      </tbody>
      <caption>{promoted ? "Promoted after sealed hold-out." : "Held — candidate did not clear the gate."}</caption>
    </table>
  );
}

function LessonList({ lessons, empty }: { lessons: Lesson[]; empty: ReactNode }) {
  if (!lessons.length) {
    return <p className="empty">{empty}</p>;
  }
  return (
    <ul className="lessons">
      {lessons.map((lesson) => (
        <li key={`${lesson.source}-${lesson.id}-${lesson.text.slice(0, 24)}`}>{lesson.text}</li>
      ))}
    </ul>
  );
}

function Runs({ report }: { report: Report }) {
  return (
    <section>
      <div className="score-wrap">
        <div className="big-score">
          <div className="trip" />
          <p className="kicker">RunN DEV</p>
          <div className="metric">{formatPct(report.run_n.pass_rate)}</div>
          <p>
            cost {formatCost(report.run_n.cost)} · {report.run_n.tokens} tok · {toolsOf(report.run_n)} tools ·{" "}
            {report.promoted ? "PROMOTED" : "HELD"}
          </p>
        </div>
        <div className="small-score">
          <p className="kicker">Run1 DEV</p>
          <div className="metric" style={{ fontSize: "2.1rem" }}>
            {formatPct(report.run1.pass_rate)}
          </div>
          <p>
            cost {formatCost(report.run1.cost)} · {report.run1.tokens} tok · {toolsOf(report.run1)} tools
          </p>
        </div>
      </div>
    </section>
  );
}

function Playbook({ report }: { report: Report }) {
  const lessons = humanLessons(report);
  return (
    <section>
      <p className="kicker">Diffable entries after Reflect. Candidate until promote.</p>
      <div className="panel">
        {lessons.length ? (
          <LessonList lessons={lessons} empty="empty" />
        ) : (
          <pre>
            {report.playbook_entries.map((entry) => `# ${entry.id}\n${entry.text}`).join("\n\n") || "empty"}
          </pre>
        )}
      </div>
      <div className="panel">
        <p className="kicker">{report.diff_path}</p>
        <pre>{report.diff || ""}</pre>
      </div>
    </section>
  );
}

function Journal({ report }: { report: Report }) {
  const lessons = journalLessons(report);
  const log = systemLogLines(report.journal ?? "");
  return (
    <section>
      <p className="kicker">Lessons are playbook text. Pipeline telemetry stays in System log.</p>
      <div className="panel">
        <h2>Lessons</h2>
        <LessonList
          lessons={lessons}
          empty={
            <>
              No human lessons yet. Run{" "}
              <code>python -m journeyman.demo.run --challenge frozen --mode offline</code> so Reflect can write
              playbook entries.
            </>
          }
        />
      </div>
      {log.length > 0 && (
        <details className="panel system-log">
          <summary>
            <span className="kicker">System log</span>
            <span className="fine"> CORE.md / persist_lesson telemetry — not the lesson list</span>
          </summary>
          <pre>{log.join("\n")}</pre>
        </details>
      )}
    </section>
  );
}

function Traces({ report }: { report: Report }) {
  return (
    <section>
      <p className="kicker">Neatlogs is system of record. Children are the flushed ingest tree.</p>
      <div className="panel">
        <p>trace_id {report.neatlogs_trace_id || "(unset — no NEATLOGS_API_KEY)"}</p>
        {report.neatlogs_url ? (
          <p>
            <a href={report.neatlogs_url}>Open cockpit</a>
          </p>
        ) : null}
        <pre>{JSON.stringify(report.children ?? [], null, 2)}</pre>
      </div>
    </section>
  );
}

function Promote({ report }: { report: Report }) {
  return (
    <section>
      <p className="kicker">Gate is Actor re-eval on frozen JSON. This tab does not promote.</p>
      <p className="seal">Hold-out never trained the playbook.</p>
      <div className="panel">
        <p>
          Decision: <strong>{report.promoted ? "PROMOTED" : "HELD"}</strong>
        </p>
        <p>
          Hold-out prior {formatPct(report.hold_prior?.pass_rate)} · candidate {formatPct(report.hold_candidate?.pass_rate)}
        </p>
        <p>
          Active {report.pointer.active} · prior {report.pointer.prior ?? "—"} · candidate {report.pointer.candidate ?? "—"}
        </p>
        <p>
          RedTeam on LIVE:{" "}
          {report.redteam
            ? `${report.redteam.successes}/${report.redteam.n} pass=${report.redteam.pass_rate}`
            : "not run"}
        </p>
        <p>Rollback is the prior pointer written by the Python run.</p>
      </div>
    </section>
  );
}

function arrow(delta: string): string {
  if (delta === "up") return "↑";
  if (delta === "down") return "↓";
  return "→";
}
