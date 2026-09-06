import { describe, expect, it } from "vitest";
import { scoreTask } from "../src/score.js";
import type { EvalTask, KeyCatalog } from "../src/types.js";

const catalog: KeyCatalog = {
  repo: "arjun7n9s/journeyman-fixture",
  owner: "arjun7n9s",
  name: "journeyman-fixture",
  issues: {
    I1: { number: 0, title: "API returns 500 on empty payload" },
    I9: { number: 0, title: "API returns 500 when body is empty" },
  },
  prs: { P1: { number: 0, title: "Fix empty payload 500 in API", closes: "I1" } },
};

describe("score", () => {
  it("labels are exact-set", () => {
    const task: EvalTask = {
      id: "dev-01",
      type: "label",
      prompt: "",
      github: {},
      expected: { labels: ["area:api", "type:bug"] },
    };
    expect(scoreTask(task, { labels: ["type:bug", "area:api"] }, catalog)).toBe(1);
    expect(scoreTask(task, { labels: ["type:bug"] }, catalog)).toBe(0);
  });

  it("matches duplicate and PR by stable keys when numbers are 0", () => {
    const dup: EvalTask = {
      id: "dev-05",
      type: "duplicate",
      prompt: "",
      github: { issue_key: "I9" },
      expected: { duplicate_of: "I1" },
    };
    expect(scoreTask(dup, { duplicate_of: "I1" }, catalog)).toBe(1);
    const pr: EvalTask = {
      id: "dev-10",
      type: "fix_pr",
      prompt: "",
      github: { issue_key: "I1" },
      expected: { pr: "P1" },
    };
    expect(scoreTask(pr, { pr: "P1" }, catalog)).toBe(1);
  });

  it("summarize requires keys present", () => {
    const task: EvalTask = {
      id: "dev-09",
      type: "summarize",
      prompt: "",
      github: {},
      expected: { keys: ["I1"] },
    };
    expect(scoreTask(task, { keys: ["I1", "I9"], text: "I1 still open" }, catalog)).toBe(1);
    expect(scoreTask(task, { text: "no bugs" }, catalog)).toBe(0);
  });
});
