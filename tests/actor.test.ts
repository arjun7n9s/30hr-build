import { describe, expect, it } from "vitest";
import { playbookLabels } from "../src/actor.js";
import { parsePlaybook } from "../src/playbook.js";

describe("playbook labels", () => {
  const facts = parsePlaybook(
    [
      "# Playbook v1",
      "repo: arjun7n9s/journeyman-fixture",
      "## Labels",
      "- type:bug",
      "## Label rules",
      "- stack trace → `type:bug`",
      "- crash/nil/OOM → `priority:p0`",
      "- path `src/billing|runtime|api|ui` → matching `area:*`",
      "- docs/typo/README → `type:docs`",
      "- feature ask → type:feat",
    ].join("\n"),
    1,
  );

  it("is not empty after rules land", () => {
    expect(facts.empty).toBe(false);
    expect(facts.rules.stack_trace_bug).toBe(true);
  });

  it("applies fixture taxonomy", () => {
    expect(playbookLabels("stack trace src/api/routes.py empty payload", facts)).toEqual([
      "area:api",
      "type:bug",
    ]);
    expect(playbookLabels("Add invoice PDF export billing/invoice", facts)).toEqual([
      "area:billing",
      "type:feat",
    ]);
    expect(playbookLabels("README typo in install section", facts)).toEqual(["type:docs"]);
    expect(playbookLabels("Crash loop on nil context src/runtime/worker.py", facts)).toEqual([
      "area:runtime",
      "priority:p0",
      "type:bug",
    ]);
  });
});
