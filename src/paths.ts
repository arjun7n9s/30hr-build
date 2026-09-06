import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const ROOT = join(here, "..");
export const POLICY_PATH = join(ROOT, "policy.yaml");
export const EVAL_DEV_PATH = join(ROOT, "eval", "dev.json");
export const EVAL_HOLDOUT_PATH = join(ROOT, "eval", "holdout.json");
export const EVAL_NUMBERS_PATH = join(ROOT, "eval", "numbers.json");
export const PLAYBOOKS_DIR = join(ROOT, "playbooks");
export const DATA_DIR = join(ROOT, "data");
export const NEATLOGS_DIR = join(DATA_DIR, "neatlogs");
export const TRACES_DIR = join(DATA_DIR, "traces");
export const RUNS_DIR = join(DATA_DIR, "runs");
export const DATA_PLAYBOOKS_DIR = join(DATA_DIR, "playbooks");
export const JOURNAL_PATH = join(DATA_DIR, "journal.md");
export const SCRIPTS_PATH = join(DATA_DIR, "scripts.json");
export const STATE_PATH = join(DATA_DIR, "state.json");
export const WEB_DIST = join(ROOT, "dist", "web");

export function ensureDataDirs(): void {
  for (const dir of [DATA_DIR, TRACES_DIR, RUNS_DIR, DATA_PLAYBOOKS_DIR, NEATLOGS_DIR]) {
    mkdirSync(dir, { recursive: true });
  }
}
