import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { AppState, PlaybookFacts, RunRecord, Trace } from "./types.js";
import {
  DATA_PLAYBOOKS_DIR,
  PLAYBOOKS_DIR,
  RUNS_DIR,
  STATE_PATH,
  TRACES_DIR,
  ensureDataDirs,
} from "./paths.js";
import { parsePlaybook } from "./playbook.js";

const DEFAULT_STATE: AppState = {
  active_version: 0,
  candidate_version: null,
  prior_version: null,
  budget: { max_cycles: 5, used: 0, last_dev_accuracy: 0, exhausted: false },
  last_dev_run_id: null,
  last_holdout_run_id: null,
  last_family_id: null,
  last_rag_hits: [],
  last_patch: null,
};

export function bootStore(): AppState {
  ensureDataDirs();
  const v0src = join(PLAYBOOKS_DIR, "v0.md");
  const v0dst = join(DATA_PLAYBOOKS_DIR, "v0.md");
  if (existsSync(v0src) && !existsSync(v0dst)) {
    writeFileSync(v0dst, readFileSync(v0src, "utf8"));
  }
  return loadState();
}

export function loadState(): AppState {
  ensureDataDirs();
  if (!existsSync(STATE_PATH)) {
    writeFileSync(STATE_PATH, JSON.stringify(DEFAULT_STATE, null, 2));
    return { ...DEFAULT_STATE, budget: { ...DEFAULT_STATE.budget } };
  }
  return { ...DEFAULT_STATE, ...JSON.parse(readFileSync(STATE_PATH, "utf8")) };
}

export function saveState(state: AppState): void {
  ensureDataDirs();
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2));
}

export function newId(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}`;
}

export function saveTrace(trace: Trace): void {
  ensureDataDirs();
  writeFileSync(join(TRACES_DIR, `${trace.id}.json`), JSON.stringify(trace, null, 2));
}

export function saveRun(run: RunRecord): void {
  ensureDataDirs();
  writeFileSync(join(RUNS_DIR, `${run.id}.json`), JSON.stringify(run, null, 2));
}

export function listRuns(): RunRecord[] {
  ensureDataDirs();
  return readdirSync(RUNS_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(readFileSync(join(RUNS_DIR, f), "utf8")) as RunRecord)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function getRun(id: string): RunRecord | undefined {
  const path = join(RUNS_DIR, `${id}.json`);
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf8")) as RunRecord) : undefined;
}

export function listTraces(runId?: string): Trace[] {
  ensureDataDirs();
  return readdirSync(TRACES_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(readFileSync(join(TRACES_DIR, f), "utf8")) as Trace)
    .filter((t) => (runId ? t.run_id === runId : true))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function getTrace(id: string): Trace | undefined {
  const path = join(TRACES_DIR, `${id}.json`);
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf8")) as Trace) : undefined;
}

export function playbookPath(version: number): string {
  return join(DATA_PLAYBOOKS_DIR, `v${version}.md`);
}

export function listPlaybookVersions(): number[] {
  ensureDataDirs();
  const versions = new Set<number>([0]);
  for (const dir of [DATA_PLAYBOOKS_DIR, PLAYBOOKS_DIR]) {
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir)) {
      const m = f.match(/^v(\d+)\.md$/);
      if (m) versions.add(Number(m[1]));
    }
  }
  return [...versions].sort((a, b) => a - b);
}

export function readPlaybookMarkdown(version: number): string {
  const dataPath = playbookPath(version);
  if (existsSync(dataPath)) return readFileSync(dataPath, "utf8");
  const committed = join(PLAYBOOKS_DIR, `v${version}.md`);
  if (existsSync(committed)) return readFileSync(committed, "utf8");
  if (version === 0) return "# Playbook v0\n\nEmpty. No repo facts yet.\n";
  return "";
}

export function writePlaybook(version: number, markdown: string): void {
  ensureDataDirs();
  writeFileSync(playbookPath(version), markdown);
}

export function loadFacts(version: number): PlaybookFacts {
  return parsePlaybook(readPlaybookMarkdown(version), version);
}

export function nextPlaybookVersion(): number {
  const versions = listPlaybookVersions();
  return (versions[versions.length - 1] ?? 0) + 1;
}

export function applyBudget(state: AppState, devAccuracy: number): AppState {
  const improved = devAccuracy > state.budget.last_dev_accuracy + 1e-9;
  const used = improved ? 0 : state.budget.used + 1;
  state.budget.used = used;
  state.budget.last_dev_accuracy = Math.max(state.budget.last_dev_accuracy, devAccuracy);
  state.budget.exhausted = used >= state.budget.max_cycles;
  return state;
}
