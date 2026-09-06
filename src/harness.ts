import type { EvalFile, KeyCatalog, PlaybookFacts, RunRecord, Split, TaskResult, ToolCaller } from "./types.js";
import { runActor } from "./actor.js";
import { loadCatalog, loadEvalFile } from "./catalog.js";
import { EVAL_DEV_PATH, EVAL_HOLDOUT_PATH } from "./paths.js";
import { scoreTask, mean } from "./score.js";
import { applyBudget, loadFacts, loadState, newId, saveRun, saveState } from "./store.js";
import { writeTrace } from "./partners/sink.js";
import { synthesizePatch } from "./patch.js";
import { reflectDev } from "./reflect.js";
import { costRouter } from "./router.js";

export class HoldoutSealedError extends Error {
  constructor(message = "hold-out is sealed until Promote") {
    super(message);
    this.name = "HoldoutSealedError";
  }
}

export class ChallengeHoldoutError extends Error {
  constructor() {
    super("Challenge cannot run or append hold-out tasks");
    this.name = "ChallengeHoldoutError";
  }
}

export async function runSplit(opts: {
  split: "dev" | "holdout";
  playbookVersion: number;
  tools: ToolCaller;
  catalog?: KeyCatalog;
  reflect?: boolean;
  allowHoldout?: boolean;
}): Promise<RunRecord> {
  if (opts.split === "holdout" && !opts.allowHoldout) {
    throw new HoldoutSealedError();
  }
  const evalPath = opts.split === "dev" ? EVAL_DEV_PATH : EVAL_HOLDOUT_PATH;
  const file = loadEvalFile(evalPath);
  const catalog = opts.catalog ?? loadCatalog();
  const facts = loadFacts(opts.playbookVersion);
  return runEvalFile({
    file,
    split: opts.split,
    facts,
    catalog,
    tools: opts.tools,
    reflect: Boolean(opts.reflect && opts.split === "dev"),
  });
}

export async function runEvalFile(opts: {
  file: EvalFile;
  split: Split;
  facts: PlaybookFacts;
  catalog: KeyCatalog;
  tools: ToolCaller;
  reflect: boolean;
}): Promise<RunRecord> {
  if (opts.split === "challenge") {
    throw new ChallengeHoldoutError();
  }
  const runId = newId("run");
  const stateNow = loadState();
  const family_id =
    opts.split === "dev" && stateNow.last_family_id && stateNow.last_patch
      ? stateNow.last_family_id
      : runId;
  const started = Date.now();
  const tasks: TaskResult[] = [];
  const traces = [];

  for (const task of opts.file.tasks) {
    costRouter(task, opts.facts);
    const trace = await runActor({
      task,
      facts: opts.facts,
      catalog: opts.catalog,
      tools: opts.tools,
      split: opts.split,
      runId,
      familyId: family_id,
    });
    const accuracy = scoreTask(task, trace.answer, opts.catalog);
    trace.accuracy = accuracy;
    writeTrace(trace);
    traces.push(trace);
    tasks.push({
      task_id: task.id,
      type: task.type,
      accuracy,
      cost: trace.cost,
      speed_ms: trace.speed_ms,
      answer: trace.answer,
      expected: task.expected,
      trace_id: trace.id,
    });
    writeTrace({
      id: newId("trace"),
      run_id: runId,
      family_id,
      task_id: task.id,
      playbook_version: opts.facts.version,
      split: opts.split,
      role: "eval",
      steps: [],
      answer: trace.answer,
      cost: trace.cost,
      speed_ms: trace.speed_ms,
      accuracy,
      spans: [
        {
          name: `score ${task.id}`,
          kind: "EVALUATOR",
          role: "eval",
          run_id: runId,
          family_id,
          task_id: task.id,
          version: opts.facts.version,
          duration_ms: trace.speed_ms,
          status: accuracy >= 1 ? "OK" : "ERROR",
          output: { accuracy, answer: trace.answer, expected: task.expected },
        },
      ],
    });
  }

  const run: RunRecord = {
    id: runId,
    family_id,
    split: opts.split,
    playbook_version: opts.facts.version,
    created_at: new Date().toISOString(),
    accuracy: mean(tasks.map((t) => t.accuracy)),
    cost: {
      tool_calls: tasks.reduce((n, t) => n + t.cost.tool_calls, 0),
      tokens: tasks.reduce((n, t) => n + t.cost.tokens, 0),
      dollars: tasks.reduce((n, t) => n + (t.cost.dollars ?? 0), 0),
    },
    speed_ms: Date.now() - started,
    reliability: {
      errors: traces.reduce((n, t) => n + t.steps.filter((s) => s.error && !s.denied).length, 0),
      retries: 0,
    },
    tasks,
    holdout_allowed: opts.split === "holdout",
  };

  if (opts.reflect && opts.split === "dev") {
    const reflected = await reflectDev({
      run,
      traces,
      prior: opts.facts,
      catalog: opts.catalog,
      tools: opts.tools,
    });
    run.reflected_version = reflected.version;
    const state = loadState();
    applyBudget(state, run.accuracy);
    if (state.budget.exhausted) {
      state.candidate_version = reflected.version;
      state.last_patch = { version: reflected.version, reason: "budget exhausted — no further patch", improved: false };
    } else {
      const patch = await synthesizePatch({ run, traces, prior: loadFacts(reflected.version) });
      if ("version" in patch) {
        state.candidate_version = patch.version;
        state.last_patch = { version: patch.version, reason: patch.reason, improved: false };
      } else {
        state.candidate_version = reflected.version;
        state.last_patch = { version: reflected.version, reason: patch.reason, improved: true };
      }
    }
    state.last_dev_run_id = run.id;
    state.last_family_id = family_id;
    state.last_rag_hits = traces.flatMap((t) => t.playbook_hits ?? []).slice(0, 12);
    saveState(state);
  } else if (opts.split === "holdout") {
    const state = loadState();
    state.last_holdout_run_id = run.id;
    saveState(state);
  }

  saveRun(run);
  return run;
}

export async function runChallenge(opts: {
  prompt: string;
  type?: import("./types.js").TaskType;
  github?: import("./types.js").GithubRef;
  tools: ToolCaller;
  playbookVersion?: number;
}): Promise<{ trace: import("./types.js").Trace; accuracy?: number }> {
  if (opts.github?.issue_key?.startsWith("hold-") || /hold-?out/i.test(opts.prompt)) {
    throw new ChallengeHoldoutError();
  }
  const catalog = loadCatalog();
  const state = loadState();
  const version = opts.playbookVersion ?? state.active_version;
  const facts = loadFacts(version);
  const task = {
    id: newId("chal"),
    type: opts.type ?? inferType(opts.prompt),
    prompt: opts.prompt,
    github: opts.github ?? {},
  };
  costRouter(task, facts);
  const runId = newId("chalrun");
  const trace = await runActor({
    task,
    facts,
    catalog,
    tools: opts.tools,
    split: "challenge",
    runId,
    familyId: runId,
  });
  writeTrace(trace);
  return { trace };
}

export function promoteVersion(version: number, holdoutRun?: RunRecord): AppPromoteResult {
  const state = loadState();
  if (state.budget.exhausted) {
    return { ok: false, reason: "budget exhausted — will not promote" };
  }
  if (!holdoutRun || holdoutRun.split !== "holdout" || holdoutRun.playbook_version !== version) {
    return { ok: false, reason: "run hold-out on this version before promote" };
  }
  if (holdoutRun.accuracy < 0.5) {
    return { ok: false, reason: `hold-out accuracy ${holdoutRun.accuracy.toFixed(3)} is below 0.5` };
  }
  state.prior_version = state.active_version;
  state.active_version = version;
  state.candidate_version = version;
  saveState(state);
  return { ok: true, active_version: version };
}

export function rollbackVersion(): AppPromoteResult {
  const state = loadState();
  if (state.prior_version === null || state.prior_version === undefined) {
    return { ok: false, reason: "no prior version to restore" };
  }
  const previous = state.active_version;
  state.active_version = state.prior_version;
  state.prior_version = previous;
  saveState(state);
  return { ok: true, active_version: state.active_version };
}

/** Reject leaves the actor on the current active version. No extra rollback chrome. */
export function rejectVersion(version: number): AppPromoteResult {
  const state = loadState();
  if (state.candidate_version === version) state.candidate_version = null;
  saveState(state);
  return { ok: true, active_version: state.active_version };
}

export type AppPromoteResult =
  | { ok: true; active_version: number }
  | { ok: false; reason: string };

function inferType(prompt: string): import("./types.js").TaskType {
  const p = prompt.toLowerCase();
  if (p.includes("duplicate")) return "duplicate";
  if (p.includes("owner") || p.includes("codeowner")) return "owner";
  if (p.includes("summar")) return "summarize";
  if (p.includes("which pr") || p.includes("fixed")) return "fix_pr";
  return "label";
}
