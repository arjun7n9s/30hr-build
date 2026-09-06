import { useEffect, useState } from "react";

type Tab = "challenge" | "runs" | "playbook" | "journal" | "traces" | "promote";

type Score = {
  pass_rate: number;
  successes: number;
  n: number;
  cost: number;
  tokens: number;
  split: string;
};

type Report = {
  challenge_id: string;
  mode: string;
  promoted: boolean;
  repo?: string;
  run1: Score;
  run_n: Score;
  hold_prior: Score | null;
  hold_candidate: Score | null;
  pointer: { active: string; candidate: string | null; prior: string | null };
  neatlogs_trace_id: string | null;
  neatlogs_url: string;
  journal_path: string;
  diff_path: string;
  journal: string;
  diff: string;
  playbook_entries: { id: string; text: string; tags: string[] }[];
  redteam: { n: number; successes: number; pass_rate: number } | null;
  children: { name: string; kind: string; input?: unknown; output?: unknown }[];
};

const TABS: { id: Tab; label: string }[] = [
  { id: "challenge", label: "Challenge" },
  { id: "runs", label: "Runs" },
  { id: "traces", label: "Trace" },
  { id: "playbook", label: "Playbook" },
  { id: "journal", label: "Journal" },
  { id: "promote", label: "Promote" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("runs");
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
    <div className="paper">
      <div className="grain" />
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

        {report && tab === "challenge" && <Challenge report={report} />}
        {report && tab === "runs" && <Runs report={report} />}
        {report && tab === "playbook" && <Playbook report={report} />}
        {report && tab === "journal" && <Journal report={report} />}
        {report && tab === "traces" && <Traces report={report} />}
        {report && tab === "promote" && <Promote report={report} />}
      </div>
    </div>
  );
}

function Challenge({ report }: { report: Report }) {
  return (
    <section>
      <p className="kicker">Frozen eval. Hold-out stays sealed until promote.</p>
      <div className="panel">
        <p>
          Challenge <strong>{report.challenge_id}</strong> on {report.repo}.
        </p>
        <p>
          DEV n={report.run1.n} · hold-out n={report.hold_candidate?.n ?? "sealed until promote"}.
        </p>
        <p>Mode {report.mode}. The learning loop is Python, not this page.</p>
      </div>
    </section>
  );
}

function Runs({ report }: { report: Report }) {
  return (
    <section>
      <div className="score-wrap">
        <div className="big-score">
          <div className="trip" />
          <p className="kicker">RunN DEV</p>
          <div className="metric">{pct(report.run_n.pass_rate)}</div>
          <p>
            cost {report.run_n.cost} · {report.run_n.tokens} tok · {report.promoted ? "PROMOTED" : "HELD"}
          </p>
        </div>
        <div className="small-score">
          <p className="kicker">Run1 DEV</p>
          <div className="metric" style={{ fontSize: "2.1rem" }}>
            {pct(report.run1.pass_rate)}
          </div>
          <p>
            cost {report.run1.cost} · {report.run1.tokens} tok
          </p>
        </div>
      </div>
    </section>
  );
}

function Playbook({ report }: { report: Report }) {
  return (
    <section>
      <p className="kicker">Diffable entries after Reflect. Candidate until promote.</p>
      <div className="panel">
        <pre>
          {report.playbook_entries.map((entry) => `# ${entry.id}\n${entry.text}`).join("\n\n") || "empty"}
        </pre>
      </div>
      <div className="panel">
        <p className="kicker">{report.diff_path}</p>
        <pre>{report.diff || ""}</pre>
      </div>
    </section>
  );
}

function Journal({ report }: { report: Report }) {
  return (
    <section>
      <p className="kicker">{report.journal_path}</p>
      <div className="panel">
        <pre>{report.journal || "No lessons yet."}</pre>
      </div>
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
      <div className="panel">
        <p>
          Decision: <strong>{report.promoted ? "PROMOTED" : "HELD"}</strong>
        </p>
        <p>
          Hold-out prior {pct(report.hold_prior?.pass_rate)} · candidate {pct(report.hold_candidate?.pass_rate)}
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

function pct(value?: number): string {
  if (value === undefined) return "—";
  return `${Math.round(value * 1000) / 10}%`;
}
