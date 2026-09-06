import { useEffect, useMemo, useState } from "react";

type Tab = "challenge" | "runs" | "playbook" | "journal" | "traces" | "promote";

type Run = {
  id: string;
  split: "dev" | "holdout" | "challenge";
  playbook_version: number;
  created_at: string;
  accuracy: number;
  cost: { tool_calls: number; tokens: number; dollars?: number };
  speed_ms: number;
  tasks: { task_id: string; accuracy: number; type: string }[];
  reflected_version?: number;
};

type TraceStep = {
  tool: string;
  args: Record<string, unknown>;
  result?: unknown;
  error?: string;
  denied?: boolean;
  latency_ms: number;
  tokens: number;
};

type Trace = {
  id: string;
  run_id: string;
  task_id: string;
  playbook_version: number;
  split: string;
  steps: TraceStep[];
  answer: Record<string, unknown>;
  cost: { tool_calls: number; tokens: number };
  speed_ms: number;
  accuracy?: number;
};

type NeatSpan = {
  name: string;
  kind: string;
  role: string;
  tool_name?: string;
  model?: string;
  provider?: string;
  duration_ms: number;
  tokens?: { total?: number };
  cost_usd?: number;
  status: string;
  error?: string;
  gate_miss?: boolean;
  playbook_hits?: string[];
  input?: unknown;
  output?: unknown;
};

type NeatRecord = {
  id: string;
  name: string;
  run_id: string;
  family_id: string;
  role: string;
  version?: number;
  created_at: string;
  spans: NeatSpan[];
};

type State = {
  active_version: number;
  candidate_version: number | null;
  prior_version: number | null;
  budget: { max_cycles: number; used: number; exhausted: boolean; last_dev_accuracy: number };
  last_patch?: { version: number; reason: string; improved: boolean } | null;
  last_family_id?: string | null;
  last_rag_hits?: string[];
  playbooks: number[];
  eval: { repo: string; zeros: boolean };
  token: boolean;
  partners?: { tensormux: boolean; neatlogs: boolean; openai: boolean };
};

const TABS: { id: Tab; label: string }[] = [
  { id: "challenge", label: "Challenge" },
  { id: "runs", label: "Runs" },
  { id: "playbook", label: "Playbook" },
  { id: "journal", label: "Journal" },
  { id: "traces", label: "Traces" },
  { id: "promote", label: "Promote" },
];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || body.reason || res.statusText);
  return body as T;
}

export function App() {
  const [tab, setTab] = useState<Tab>("runs");
  const [state, setState] = useState<State | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");

  async function refresh() {
    const next = await api<State>("/api/state");
    const listed = await api<{ runs: Run[] }>("/api/runs");
    setState(next);
    setRuns(listed.runs);
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="paper">
      <div className="grain" />
      <div className="shell">
        <header className="top">
          <div>
            <p className="kicker">Automated agent engineering</p>
            <h1>Journeyman</h1>
          </div>
          <div className="meta">
            <div>active v{state?.active_version ?? 0}</div>
            <div>{state?.eval.repo ?? "arjun7n9s/journeyman-fixture"}</div>
            <div>{state?.token ? "MCP token set" : "set GITHUB_TOKEN"}</div>
            <div>{state?.partners?.tensormux ? "TensorMux set" : "set TMX_API_KEY"}</div>
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

        {state?.eval.zeros && (
          <div className="warn">
            Eval issue/PR numbers are still 0. The fixture worker has not merged real GitHub numbers yet. Schema is kept; polling sibling eval files.
          </div>
        )}
        {error && <p className="err">{error}</p>}

        {tab === "challenge" && <Challenge onDone={refresh} />}
        {tab === "runs" && <Runs runs={runs} onRun={refresh} />}
        {tab === "playbook" && <Playbook />}
        {tab === "journal" && <Journal />}
        {tab === "traces" && <Traces />}
        {tab === "promote" && <Promote state={state} runs={runs} onDone={refresh} />}
      </div>
    </div>
  );
}

function Challenge({ onDone }: { onDone: () => Promise<void> }) {
  const [prompt, setPrompt] = useState("What labels should this issue get, using this repo's taxonomy?\n\nAPI returns 500 on empty payload");
  const [type, setType] = useState("label");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Trace | null>(null);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const body = await api<{ trace: Trace }>("/api/challenge", {
        method: "POST",
        body: JSON.stringify({ prompt, type }),
      });
      setResult(body.trace);
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <p className="kicker">Read-only classify / answer. Does not write hold-out.</p>
      <div className="panel">
        <label>
          Task type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="label">label</option>
            <option value="duplicate">duplicate</option>
            <option value="owner">owner</option>
            <option value="summarize">summarize</option>
            <option value="fix_pr">fix_pr</option>
          </select>
        </label>
        <label>
          Prompt
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </label>
        <div className="row" style={{ marginTop: "1rem" }}>
          <button className="stamp" disabled={busy} onClick={submit}>
            {busy ? "Running…" : "Ask →"}
          </button>
        </div>
      </div>
      {error && <p className="err">{error}</p>}
      {result && (
        <div className="panel">
          <p className="kicker">Answer</p>
          <p className="answer">{JSON.stringify(result.answer)}</p>
          <p>
            {result.cost.tool_calls} tools · {result.cost.tokens} tokens · {result.speed_ms} ms
          </p>
        </div>
      )}
    </section>
  );
}

function Runs({ runs, onRun }: { runs: Run[]; onRun: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const v0 = runs.find((r) => r.split === "dev" && r.playbook_version === 0);
  const later = [...runs].reverse().find((r) => r.split === "dev" && r.playbook_version > 0);

  async function runDev() {
    setBusy(true);
    setError("");
    try {
      await api("/api/eval/dev", { method: "POST", body: JSON.stringify({ reflect: true }) });
      await onRun();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="row" style={{ marginBottom: "1rem" }}>
        <button className="stamp" disabled={busy} onClick={runDev}>
          {busy ? "Running DEV…" : "Run DEV + reflect →"}
        </button>
        <span className="kicker">v0 empty playbook vs later versions. Hold-out stays sealed.</span>
      </div>
      {error && <p className="err">{error}</p>}
      <div className="score-wrap">
        <div className="big-score">
          <div className="trip" />
          <p className="kicker">Latest learned DEV</p>
          <div className="metric">{pct(later?.accuracy)}</div>
          <p>
            v{later?.playbook_version ?? "—"} · {later?.cost.tool_calls ?? "—"} tools · {later?.speed_ms ?? "—"} ms
          </p>
        </div>
        <div className="small-score">
          <p className="kicker">v0 baseline</p>
          <div className="metric" style={{ fontSize: "2.1rem" }}>
            {pct(v0?.accuracy)}
          </div>
          <p>
            {v0?.cost.tool_calls ?? "—"} tools · {v0?.speed_ms ?? "—"} ms
          </p>
        </div>
      </div>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Split</th>
              <th>Playbook</th>
              <th>Accuracy</th>
              <th>Cost</th>
              <th>Speed</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 && (
              <tr>
                <td colSpan={6}>No runs yet.</td>
              </tr>
            )}
            {[...runs].reverse().map((run) => (
              <tr key={run.id}>
                <td>{run.id}</td>
                <td className={run.split === "holdout" ? "hold" : "dev"}>{run.split}</td>
                <td>v{run.playbook_version}</td>
                <td>{pct(run.accuracy)}</td>
                <td>
                  {run.cost.tool_calls} tools / {run.cost.tokens} tok
                  {run.cost.dollars ? ` / $${run.cost.dollars.toFixed(5)}` : ""}
                </td>
                <td>{run.speed_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Playbook() {
  const [versions, setVersions] = useState<{ version: number; markdown: string }[]>([]);
  const [active, setActive] = useState(0);
  const [pick, setPick] = useState(0);
  const [hits, setHits] = useState<string[]>([]);

  useEffect(() => {
    api<{ versions: { version: number; markdown: string }[]; active: number }>("/api/playbooks")
      .then((body) => {
        setVersions(body.versions);
        setActive(body.active);
        setPick(body.active);
      })
      .catch(() => undefined);
    api<{ hits: string[] }>(`/api/rag?q=${encodeURIComponent("label rules owners search")}`)
      .then((body) => setHits(body.hits))
      .catch(() => undefined);
  }, []);

  const current = versions.find((v) => v.version === pick);

  return (
    <section>
      <p className="kicker">Active v{active}. Dump is the live markdown. RAG-retrieved facts below.</p>
      <div className="row" style={{ marginBottom: "0.8rem" }}>
        {versions.map((v) => (
          <button key={v.version} className="ghost" onClick={() => setPick(v.version)}>
            v{v.version}
          </button>
        ))}
      </div>
      {hits.length > 0 && (
        <p className="kicker" style={{ marginBottom: "0.6rem" }}>
          Retrieved: {hits.join(" · ")}
        </p>
      )}
      <div className="panel">
        <pre>{current?.markdown || "No playbook."}</pre>
      </div>
    </section>
  );
}

function Journal() {
  const [markdown, setMarkdown] = useState("");

  useEffect(() => {
    api<{ markdown: string }>("/api/journal")
      .then((body) => setMarkdown(body.markdown))
      .catch(() => undefined);
  }, []);

  return (
    <section>
      <p className="kicker">Append-only. Reflection writes here. Hold-out never does.</p>
      <div className="panel">
        <pre>{markdown || "No lessons yet."}</pre>
      </div>
    </section>
  );
}

function Traces() {
  const [records, setRecords] = useState<NeatRecord[]>([]);
  const [pick, setPick] = useState<string>("");
  const [step, setStep] = useState(0);

  useEffect(() => {
    api<{ records: NeatRecord[] }>("/api/neatlogs")
      .then((body) => {
        setRecords(body.records);
        setPick(body.records.at(-1)?.id ?? "");
        setStep(0);
      })
      .catch(() => undefined);
  }, []);

  const families = [...new Set(records.map((r) => r.family_id))];
  const current = records.find((t) => t.id === pick);
  const spans = current?.spans ?? [];
  const span = spans[step];

  return (
    <section>
      <p className="kicker">Neatlogs cockpit. Same family before/after a patch. Tools, models, gates.</p>
      {families.length > 1 && (
        <p className="kicker" style={{ marginBottom: "0.6rem" }}>
          Families: {families.length}
        </p>
      )}
      <div className="row" style={{ marginBottom: "0.8rem" }}>
        <select
          value={pick}
          onChange={(e) => {
            setPick(e.target.value);
            setStep(0);
          }}
        >
          {records.map((t) => (
            <option key={t.id} value={t.id}>
              {t.family_id} · {t.role} · {t.name}
            </option>
          ))}
        </select>
      </div>
      {current && (
        <div className="panel">
          <p className="kicker">
            {current.role} · family {current.family_id} · span {spans.length ? step + 1 : 0} / {spans.length}
          </p>
          {span ? (
            <>
              <p className="answer">
                {span.kind} · {span.name}
                {span.gate_miss ? " (gate miss)" : ""}
              </p>
              <p>
                {span.duration_ms} ms
                {span.tokens?.total ? ` · ${span.tokens.total} tok` : ""}
                {span.cost_usd ? ` · $${span.cost_usd.toFixed(6)}` : ""}
                {span.provider ? ` · ${span.provider}` : ""}
                {span.model ? ` ${span.model}` : ""}
                {span.error ? ` · ${span.error}` : ""}
              </p>
              {span.playbook_hits?.length ? <p>hits: {span.playbook_hits.join(", ")}</p> : null}
              <pre>{JSON.stringify({ input: span.input, output: span.output }, null, 2)}</pre>
            </>
          ) : (
            <p>No spans.</p>
          )}
          <div className="row" style={{ marginTop: "0.8rem" }}>
            <button className="ghost" disabled={step <= 0} onClick={() => setStep((n) => Math.max(0, n - 1))}>
              Prev
            </button>
            <button
              className="ghost"
              disabled={step >= spans.length - 1}
              onClick={() => setStep((n) => Math.min(spans.length - 1, n + 1))}
            >
              Next
            </button>
          </div>
        </div>
      )}
      <div className="panel">
        <p className="kicker">Raw</p>
        <pre>{current ? JSON.stringify(current, null, 2) : "No Neatlogs yet. Run DEV or Challenge."}</pre>
      </div>
    </section>
  );
}

function Promote({
  state,
  runs,
  onDone,
}: {
  state: State | null;
  runs: Run[];
  onDone: () => Promise<void>;
}) {
  const candidate = state?.candidate_version ?? state?.active_version ?? 0;
  const [version, setVersion] = useState(candidate);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const holdout = useMemo(
    () => [...runs].reverse().find((r) => r.split === "holdout" && r.playbook_version === version),
    [runs, version],
  );
  const dev = useMemo(
    () => [...runs].reverse().find((r) => r.split === "dev" && r.playbook_version === version),
    [runs, version],
  );

  useEffect(() => {
    setVersion(candidate);
  }, [candidate]);

  async function runHoldout() {
    setBusy("holdout");
    setError("");
    try {
      await api("/api/eval/holdout", {
        method: "POST",
        body: JSON.stringify({ playbook_version: version }),
      });
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function decide(action: "approve" | "reject" | "rollback") {
    setBusy(action);
    setError("");
    try {
      if (action === "approve" && !holdout) throw new Error("run hold-out first");
      await api("/api/promote", {
        method: "POST",
        body: JSON.stringify({
          action,
          playbook_version: version,
          holdout_run_id: holdout?.id,
        }),
      });
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <section>
      <p className="kicker">Hold-out is candidate-only. Approve activates. Rollback restores the prior pointer.</p>
      {state?.budget.exhausted && <div className="warn">Budget exhausted. Will not promote.</div>}
      {state?.last_patch && <p className="kicker">Patch: {state.last_patch.reason}</p>}
      <div className="panel">
        <label>
          Candidate version
          <input type="number" value={version} onChange={(e) => setVersion(Number(e.target.value))} />
        </label>
        <p>
          DEV headline {pct(dev?.accuracy)} · {dev?.cost.tool_calls ?? "—"} tools · {dev?.speed_ms ?? "—"} ms
        </p>
        <p>
          Hold-out headline {pct(holdout?.accuracy)} · {holdout?.cost.tool_calls ?? "—"} tools · {holdout?.speed_ms ?? "—"} ms
        </p>
        <p>Active v{state?.active_version ?? 0} · prior v{state?.prior_version ?? "—"}</p>
        <div className="row" style={{ marginTop: "1rem" }}>
          <button className="ghost" disabled={Boolean(busy)} onClick={runHoldout}>
            {busy === "holdout" ? "Running hold-out…" : "Run hold-out"}
          </button>
          <button className="ghost" disabled={Boolean(busy)} onClick={() => decide("reject")}>
            {busy === "reject" ? "Rejecting…" : "Reject"}
          </button>
          <button className="ghost" disabled={Boolean(busy) || state?.prior_version === null} onClick={() => decide("rollback")}>
            {busy === "rollback" ? "Rolling back…" : "Rollback"}
          </button>
          <button className="stamp" disabled={Boolean(busy) || state?.budget.exhausted} onClick={() => decide("approve")}>
            {busy === "approve" ? "Approving…" : "Approve →"}
          </button>
        </div>
      </div>
      {error && <p className="err">{error}</p>}
    </section>
  );
}

function pct(value?: number): string {
  if (value === undefined) return "—";
  return `${Math.round(value * 1000) / 10}%`;
}
