import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { promoteVersion, rejectVersion, rollbackVersion } from "../src/harness.js";
import { synthesizePatch } from "../src/patch.js";
import { loadState, saveState } from "../src/store.js";
import { emptyFacts } from "../src/playbook.js";
import type { RunRecord } from "../src/types.js";

const run: RunRecord = {
  id: "run-p",
  split: "dev",
  playbook_version: 0,
  created_at: "2026-09-06T00:00:00.000Z",
  accuracy: 0.2,
  cost: { tool_calls: 8, tokens: 20 },
  speed_ms: 30,
  tasks: [
    { task_id: "dev-01", type: "label", accuracy: 0, cost: { tool_calls: 2, tokens: 5 }, speed_ms: 5, answer: {}, trace_id: "a" },
    { task_id: "dev-07", type: "owner", accuracy: 0, cost: { tool_calls: 2, tokens: 5 }, speed_ms: 5, answer: {}, trace_id: "b" },
  ],
};

describe("patch + rollback", () => {
  afterEach(() => {
    const state = loadState();
    state.budget = { max_cycles: 5, used: 0, last_dev_accuracy: 0, exhausted: false };
    state.active_version = 0;
    state.prior_version = null;
    state.candidate_version = null;
    saveState(state);
  });

  it("proposes a candidate from DEV fail patterns", async () => {
    const patch = await synthesizePatch({ run, traces: [], prior: emptyFacts(0) });
    expect("version" in patch).toBe(true);
    if ("version" in patch) {
      expect(patch.version).toBeGreaterThan(0);
      expect(patch.reason).toMatch(/miss/);
    }
  });

  it("rollback restores the prior active pointer", () => {
    const state = loadState();
    state.active_version = 0;
    state.prior_version = null;
    state.budget.exhausted = false;
    saveState(state);
    const holdout: RunRecord = {
      ...run,
      id: "run-h",
      split: "holdout",
      playbook_version: 2,
      accuracy: 0.8,
      tasks: [],
    };
    const dir = mkdtempSync(join(tmpdir(), "jm-"));
    writeFileSync(join(dir, "unused.json"), "{}");
    const approved = promoteVersion(2, holdout);
    expect(approved.ok).toBe(true);
    if (approved.ok) expect(approved.active_version).toBe(2);
    expect(loadState().prior_version).toBe(0);
    const rolled = rollbackVersion();
    expect(rolled.ok).toBe(true);
    if (rolled.ok) expect(rolled.active_version).toBe(0);
    expect(loadState().prior_version).toBe(2);
  });

  it("does not promote when budget is exhausted", () => {
    const state = loadState();
    state.budget.exhausted = true;
    saveState(state);
    const result = promoteVersion(1);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/budget exhausted/i);
    rejectVersion(1);
  });
});
