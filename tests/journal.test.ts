import { describe, expect, it } from "vitest";
import { appendJournalLesson, readJournal } from "../src/journal.js";
import type { RunRecord } from "../src/types.js";

function run(split: "dev" | "holdout", accuracy = 0.4): RunRecord {
  return {
    id: "run-j",
    split,
    playbook_version: 0,
    created_at: "2026-09-06T00:00:00.000Z",
    accuracy,
    cost: { tool_calls: 3, tokens: 10 },
    speed_ms: 12,
    tasks: [{ task_id: "dev-01", type: "label", accuracy: 0, cost: { tool_calls: 1, tokens: 4 }, speed_ms: 4, answer: {}, trace_id: "t" }],
  };
}

describe("journal", () => {
  it("appends DEV lessons and refuses hold-out writes", () => {
    const first = appendJournalLesson({
      run: run("dev"),
      traces: [],
      playbookVersion: 1,
      notes: ["search before list-all"],
    });
    const before = first.markdown;
    const second = appendJournalLesson({
      run: { ...run("dev"), id: "run-j2" },
      traces: [],
      playbookVersion: 2,
      notes: ["owners are directory names"],
    });
    expect(second.markdown.startsWith(before.trimEnd())).toBe(true);
    expect(second.markdown).toContain("search before list-all");
    expect(second.markdown).toContain("owners are directory names");
    expect(() =>
      appendJournalLesson({
        run: run("holdout"),
        traces: [],
        playbookVersion: 3,
        notes: ["must not land"],
      }),
    ).toThrow(/hold-out/);
    expect(readJournal()).not.toContain("must not land");
  });
});
