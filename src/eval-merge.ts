import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { EvalFile, EvalTask } from "./types.js";
import { EVAL_DEV_PATH, EVAL_HOLDOUT_PATH, EVAL_NUMBERS_PATH, ROOT } from "./paths.js";
import { loadEvalFile } from "./catalog.js";

function siblingEvalPaths(): string[] {
  const parent = dirname(ROOT);
  const names = [
    "30hr-build-3",
    "30hr-build-4",
    "30hr-build-5",
    "30hr-build-6",
    "30hr-build-orchestrator",
    "orchestrator",
  ];
  const files: string[] = [];
  for (const name of names) {
    for (const file of ["eval/dev.json", "eval/holdout.json"]) {
      const path = resolve(parent, name, file);
      if (existsSync(path)) files.push(path);
    }
  }
  return files;
}

function harvestKeys(file: EvalFile): { issues: Record<string, number>; prs: Record<string, number> } {
  const issues: Record<string, number> = {};
  const prs: Record<string, number> = {};
  for (const task of file.tasks) {
    const g = task.github ?? {};
    if (g.issue_key && (g.issue_number ?? 0) > 0) issues[g.issue_key] = g.issue_number!;
    if (g.pr_key && (g.pr_number ?? 0) > 0) prs[g.pr_key] = g.pr_number!;
    const expected = task.expected as Record<string, unknown> | undefined;
    if (expected) {
      if (typeof expected.duplicate_of_key === "string" && Number(expected.duplicate_of) > 0) {
        issues[expected.duplicate_of_key] = Number(expected.duplicate_of);
      }
      if (typeof expected.pr_key === "string" && Number(expected.pr ?? expected.pr_number) > 0) {
        prs[expected.pr_key] = Number(expected.pr ?? expected.pr_number);
      }
    }
  }
  return { issues, prs };
}

function applyHarvest(
  github: EvalTask["github"],
  harvest: { issues: Record<string, number>; prs: Record<string, number> },
): EvalTask["github"] {
  const next = { ...github };
  if (next.issue_key && !(next.issue_number && next.issue_number > 0) && harvest.issues[next.issue_key]) {
    next.issue_number = harvest.issues[next.issue_key];
  }
  if (next.pr_key && !(next.pr_number && next.pr_number > 0) && harvest.prs[next.pr_key]) {
    next.pr_number = harvest.prs[next.pr_key];
  }
  return next;
}

function mergeGithub(local: EvalTask["github"], incoming: EvalTask["github"]): EvalTask["github"] {
  const next = { ...local };
  if (next.issue_key && (!next.issue_number || next.issue_number === 0) && incoming.issue_number && incoming.issue_number > 0) {
    next.issue_number = incoming.issue_number;
  }
  if ((next.pr_key || incoming.pr_key) && (!next.pr_number || next.pr_number === 0) && incoming.pr_number && incoming.pr_number > 0) {
    next.pr_key = next.pr_key || incoming.pr_key;
    next.pr_number = incoming.pr_number;
  }
  if (!next.issue_title && incoming.issue_title) next.issue_title = incoming.issue_title;
  return next;
}

export function mergeEvalFile(localPath: string, incoming: EvalFile): { changed: boolean; assigned: number } {
  const local = loadEvalFile(localPath);
  let assigned = 0;
  let changed = false;
  if (incoming.repo) local.repo = incoming.repo;
  const harvest = harvestKeys(incoming);
  const byId = new Map(incoming.tasks.map((t) => [t.id, t]));
  for (const task of local.tasks) {
    const other = byId.get(task.id);
    const before = JSON.stringify(task.github);
    if (other) task.github = mergeGithub(task.github, other.github);
    task.github = applyHarvest(task.github, harvest);
    if (JSON.stringify(task.github) !== before) {
      changed = true;
      assigned += 1;
    }
  }
  if (changed) writeFileSync(localPath, `${JSON.stringify(local, null, 2)}\n`);
  return { changed, assigned };
}

export function pollFixtureEval(): {
  sources: string[];
  merged: { path: string; assigned: number }[];
} {
  const sources = siblingEvalPaths();
  const merged: { path: string; assigned: number }[] = [];
  const harvest = { issues: {} as Record<string, number>, prs: {} as Record<string, number> };
  for (const source of sources) {
    let incoming: EvalFile;
    try {
      incoming = JSON.parse(readFileSync(source, "utf8")) as EvalFile;
    } catch {
      continue;
    }
    const keys = harvestKeys(incoming);
    Object.assign(harvest.issues, keys.issues);
    Object.assign(harvest.prs, keys.prs);
    const target = source.endsWith("holdout.json") ? EVAL_HOLDOUT_PATH : EVAL_DEV_PATH;
    const result = mergeEvalFile(target, incoming);
    if (result.assigned) merged.push({ path: source, assigned: result.assigned });
  }
  if (Object.keys(harvest.issues).length || Object.keys(harvest.prs).length) {
    const prior = existsSync(EVAL_NUMBERS_PATH)
      ? (JSON.parse(readFileSync(EVAL_NUMBERS_PATH, "utf8")) as typeof harvest)
      : { issues: {}, prs: {} };
    const next = {
      issues: { ...prior.issues, ...harvest.issues },
      prs: { ...prior.prs, ...harvest.prs },
    };
    writeFileSync(EVAL_NUMBERS_PATH, `${JSON.stringify(next, null, 2)}\n`);
  }
  return { sources, merged };
}

export function numbersStillZero(): boolean {
  const files = [loadEvalFile(EVAL_DEV_PATH), loadEvalFile(EVAL_HOLDOUT_PATH)];
  return files.some((file) =>
    file.tasks.some((t) => {
      if (t.github.issue_key && !(t.github.issue_number && t.github.issue_number > 0)) return true;
      if (t.github.pr_key && !(t.github.pr_number && t.github.pr_number > 0)) return true;
      return false;
    }),
  );
}

export function evalSnapshot(): { repo: string; zeros: boolean; tasks: { id: string; issue_number?: number; pr_number?: number }[] } {
  const dev = loadEvalFile(EVAL_DEV_PATH);
  return {
    repo: dev.repo,
    zeros: numbersStillZero(),
    tasks: [...dev.tasks, ...loadEvalFile(EVAL_HOLDOUT_PATH).tasks].map((t) => ({
      id: t.id,
      issue_number: t.github.issue_number,
      pr_number: t.github.pr_number,
    })),
  };
}
