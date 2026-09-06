import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { JOURNAL_PATH, ensureDataDirs } from "./paths.js";
import type { RunRecord, Trace } from "./types.js";

const HEADER = "# Playbook Journal\n\nAppend-only lessons from DEV reflection. Hold-out never writes here.\n\n";

export function readJournal(): string {
  ensureDataDirs();
  if (!existsSync(JOURNAL_PATH)) return HEADER;
  return readFileSync(JOURNAL_PATH, "utf8");
}

export function appendJournalLesson(opts: {
  run: RunRecord;
  traces: Trace[];
  playbookVersion: number;
  notes: string[];
}): { appended: string; markdown: string } {
  if (opts.run.split !== "dev") {
    throw new Error("hold-out and challenge must not append the journal");
  }
  const failed = opts.run.tasks.filter((t) => t.accuracy < 1).map((t) => t.task_id);
  const lesson = [
    `## ${opts.run.created_at} · DEV ${opts.run.id} → playbook v${opts.playbookVersion}`,
    "",
    `- accuracy ${opts.run.accuracy.toFixed(3)} · ${opts.run.cost.tool_calls} tools · ${opts.run.speed_ms} ms`,
    `- failed: ${failed.length ? failed.join(", ") : "(none)"}`,
    ...opts.notes.map((n) => `- ${n}`),
    "",
  ].join("\n");
  const prior = readJournal();
  const markdown = `${prior.endsWith("\n") ? prior : `${prior}\n`}${lesson}`;
  writeFileSync(JOURNAL_PATH, markdown);
  return { appended: lesson, markdown };
}
