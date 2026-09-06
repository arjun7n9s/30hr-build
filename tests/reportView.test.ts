import { describe, expect, it } from "vitest";
import {
  challengeLessons,
  cockpitHref,
  journalLessons,
  humanLessons,
  isTelemetryLine,
  systemLogLines,
} from "../web/src/reportView";

const JOURNAL = `# Journal

## Lessons

- Run1 DEV 0.2143 with weak playbook weak-0
- Reflect merged 2 entries from 11 DEV-fail spans into cand-a0ceb7b7. Retrieved: helpful. Derived 12 rules from arjun7n9s/journeyman-fixture: WHEN path contains ['src/api/'] THEN set owner=api. Mined 14 rules from corpus soil: label-258ab07617 WHEN body contains ['routes'] THEN add labels=area:api.
- promoted cand-a0ceb7b7 DEV 1.0 holdout prior 0.0 candidate 1.0
`;

const ENTRIES = [
  {
    id: "helpful",
    text: "Be helpful and confident. Guess if you are unsure.",
    tags: ["weak", "retrieved"],
  },
  {
    id: "candidate-rule",
    text:
      "Answer only from retrieved evidence. If evidence is missing, say so.\n\n" +
      "Rule: cite evidence or refuse when tools are empty. Do not invent facts when tools return nothing.\n" +
      "When asked `What labels should this issue get?` do not invent. Failed with `From repo evidence:`.\n" +
      "get_file_contents: {'found': True, 'path': 'CONTRIBUTING.md', 'content': '# Contributing'}. Cite tools. If missing, say so.",
    tags: ["candidate", "evidence"],
  },
];

const RULES = [
  {
    id: "owner-billing",
    text: "WHEN path contains ['src/billing/'] THEN set owner=billing",
    origin: "derived",
  },
  {
    id: "label-api",
    text: "WHEN body contains ['routes'] THEN add labels=area:api",
    origin: "mined",
  },
];

describe("reportView", () => {
  it("treats CORE.md persist_lesson lines as telemetry", () => {
    expect(isTelemetryLine("Run1 DEV 0.2143 with weak playbook weak-0")).toBe(true);
    expect(isTelemetryLine("- Reflect merged 2 entries from 11 DEV-fail spans")).toBe(true);
    expect(isTelemetryLine("promoted cand-a0ceb7b7 DEV 1.0")).toBe(true);
    expect(isTelemetryLine("Derived 12 rules from the workspace")).toBe(true);
    expect(isTelemetryLine("Mined 14 rules from corpus soil")).toBe(true);
    expect(isTelemetryLine("Answer only from retrieved evidence.")).toBe(false);
  });

  it("extracts human playbook lessons and never the journal dump", () => {
    const lessons = humanLessons({ playbook_entries: ENTRIES, playbook_rules: RULES });
    const texts = lessons.map((lesson) => lesson.text);
    expect(texts.some((text) => /Be helpful and confident/.test(text))).toBe(false);
    expect(texts.some((text) => /Failed with/.test(text))).toBe(false);
    expect(texts.some((text) => /get_file_contents:/.test(text))).toBe(false);
    expect(texts.some((text) => /Run1 DEV/.test(text))).toBe(false);
    expect(texts.some((text) => /retrieved evidence/.test(text))).toBe(true);
    expect(texts.some((text) => /cite evidence/.test(text))).toBe(true);
    expect(texts.some((text) => /src\/billing/.test(text))).toBe(true);
    expect(challengeLessons({ playbook_entries: ENTRIES, playbook_rules: RULES }).length).toBeLessThanOrEqual(4);
    expect(challengeLessons({ playbook_entries: ENTRIES, playbook_rules: RULES }).length).toBeGreaterThanOrEqual(2);
    expect(journalLessons({ playbook_entries: ENTRIES, playbook_rules: RULES }).length).toBeLessThanOrEqual(8);
  });

  it("parses journal telemetry into a system log and leaves lessons empty without playbook text", () => {
    const log = systemLogLines(JOURNAL);
    expect(log.some((line) => line.startsWith("Run1 DEV"))).toBe(true);
    expect(log.some((line) => line.startsWith("Reflect merged"))).toBe(true);
    expect(log.some((line) => line.startsWith("promoted "))).toBe(true);
    expect(humanLessons({ playbook_entries: [], playbook_rules: [] })).toEqual([]);
  });

  it("rewrites stale /?trace_id= cockpit links to /traces/{id}", () => {
    expect(
      cockpitHref({
        neatlogs_trace_id: "1fa771b7ae56cb6972b66336fc1f142d",
        neatlogs_url: "https://app.neatlogs.com/?trace_id=1fa771b7ae56cb6972b66336fc1f142d",
      }),
    ).toBe(
      "https://app.neatlogs.com/traces/1fa771b7ae56cb6972b66336fc1f142d?orgId=8bd3fd8b-e753-4ace-8eeb-da3006f631f3&projectId=66d21721-995d-49b1-83e1-0427e9b56059",
    );
  });
});
