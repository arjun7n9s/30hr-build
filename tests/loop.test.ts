import { describe, expect, it } from "vitest";
import { loadCatalog } from "../src/catalog.js";
import { runEvalFile } from "../src/harness.js";
import { loadEvalFile } from "../src/catalog.js";
import { EVAL_DEV_PATH } from "../src/paths.js";
import { emptyFacts, parsePlaybook } from "../src/playbook.js";
import { loadFacts } from "../src/store.js";
import { mockGithub } from "./mock-mcp.js";

describe("learning loop", () => {
  it("reflection writes a grounded playbook and later DEV is more accurate", async () => {
    const catalog = loadCatalog();
    const file = loadEvalFile(EVAL_DEV_PATH);
    const v0 = await runEvalFile({
      file,
      split: "dev",
      facts: emptyFacts(0),
      catalog,
      tools: mockGithub(),
      reflect: true,
    });
    expect(v0.reflected_version).toBeGreaterThan(0);
    const learned = loadFacts(v0.reflected_version!);
    expect(learned.empty).toBe(false);
    expect(learned.rules.stack_trace_bug).toBe(true);
    expect(learned.owners["src/billing"]).toBe("billing");

    const vN = await runEvalFile({
      file,
      split: "dev",
      facts: learned,
      catalog,
      tools: mockGithub(),
      reflect: false,
    });
    expect(vN.accuracy).toBeGreaterThan(v0.accuracy);
    expect(vN.accuracy).toBeGreaterThanOrEqual(0.7);
  });

  it("parsePlaybook keeps v0 empty", () => {
    const facts = parsePlaybook("# Playbook v0\n\nEmpty. No repo facts yet.\n", 0);
    expect(facts.empty).toBe(true);
    expect(facts.search_before_list).toBe(false);
  });
});
