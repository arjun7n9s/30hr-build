import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { mergeEvalFile } from "../src/eval-merge.js";
import type { EvalFile } from "../src/types.js";

describe("eval merge", () => {
  it("copies real GitHub numbers and never invents them", () => {
    const dir = mkdtempSync(join(tmpdir(), "journeyman-"));
    const localPath = join(dir, "dev.json");
    const local: EvalFile = {
      split: "dev",
      repo: "arjun7n9s/journeyman-fixture",
      tasks: [
        {
          id: "dev-01",
          type: "label",
          prompt: "x",
          github: { issue_key: "I1", issue_number: 0 },
        },
      ],
    };
    writeFileSync(localPath, JSON.stringify(local));
    const zero = mergeEvalFile(localPath, {
      ...local,
      tasks: [{ ...local.tasks[0], github: { issue_key: "I1", issue_number: 0 } }],
    });
    expect(zero.assigned).toBe(0);
    expect(JSON.parse(readFileSync(localPath, "utf8")).tasks[0].github.issue_number).toBe(0);

    const merged = mergeEvalFile(localPath, {
      ...local,
      tasks: [{ ...local.tasks[0], github: { issue_key: "I1", issue_number: 41 } }],
    });
    expect(merged.assigned).toBe(1);
    expect(JSON.parse(readFileSync(localPath, "utf8")).tasks[0].github.issue_number).toBe(41);
  });
});
