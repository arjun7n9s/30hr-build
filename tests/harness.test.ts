import { describe, expect, it } from "vitest";
import { runActor } from "../src/actor.js";
import { loadCatalog } from "../src/catalog.js";
import { ChallengeHoldoutError, HoldoutSealedError, promoteVersion, rejectVersion, runChallenge, runSplit } from "../src/harness.js";
import { emptyFacts } from "../src/playbook.js";
import { mockGithub } from "./mock-mcp.js";

describe("harness gates", () => {
  it("refuses hold-out until promote allows it", async () => {
    await expect(
      runSplit({ split: "holdout", playbookVersion: 0, tools: mockGithub(), allowHoldout: false }),
    ).rejects.toBeInstanceOf(HoldoutSealedError);
  });

  it("refuses Challenge prompts that ask for hold-out", async () => {
    await expect(
      runChallenge({ prompt: "run the hold-out set", tools: mockGithub() }),
    ).rejects.toBeInstanceOf(ChallengeHoldoutError);
  });

  it("will not promote without a hold-out run", () => {
    const result = promoteVersion(1);
    expect(result.ok).toBe(false);
  });

  it("reject leaves the actor on the previous active version", () => {
    const before = promoteVersion(1);
    expect(before.ok).toBe(false);
    const rejected = rejectVersion(1);
    expect(rejected.ok).toBe(true);
    if (rejected.ok) expect(rejected.active_version).toBe(0);
  });
});

describe("actor v0", () => {
  it("lists instead of searching and misses area labels", async () => {
    const tools = mockGithub();
    const catalog = loadCatalog();
    const trace = await runActor({
      task: {
        id: "dev-01",
        type: "label",
        prompt: "What labels should this issue get, using this repo's taxonomy?",
        github: { issue_key: "I1", issue_number: 0, issue_title: "API returns 500 on empty payload" },
        expected: { labels: ["area:api", "type:bug"] },
      },
      facts: emptyFacts(0),
      catalog,
      tools,
      split: "dev",
      runId: "run-test",
    });
    expect(tools.calls.some((c) => c.name === "list_issues")).toBe(true);
    expect(trace.answer.labels).toEqual(["type:bug"]);
  });
});
