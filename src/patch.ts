import type { PlaybookFacts, RunRecord, Trace } from "./types.js";
import { complete, patchGate } from "./partners/brain.js";
import { writeTrace } from "./partners/sink.js";
import { renderPlaybook } from "./playbook.js";
import { newId, nextPlaybookVersion, writePlaybook } from "./store.js";

export async function synthesizePatch(opts: {
  run: RunRecord;
  traces: Trace[];
  prior: PlaybookFacts;
}): Promise<{ version: number; reason: string } | { skipped: true; reason: string }> {
  const failed = opts.run.tasks.filter((t) => t.accuracy < 1);
  if (!failed.length) {
    return { skipped: true, reason: "DEV already exact — no patch" };
  }
  const lessons = failed.map((task) => {
    if (task.type === "label") return `label miss ${task.task_id}: apply CONTRIBUTING path/area rules before guessing`;
    if (task.type === "duplicate") return `duplicate miss ${task.task_id}: search by title overlap, prefer the earlier issue`;
    if (task.type === "owner") return `owner miss ${task.task_id}: map src/{area} to the logical area name, not the GitHub handle`;
    if (task.type === "summarize") return `summarize miss ${task.task_id}: mention required issue keys from the filtered set`;
    return `fix_pr miss ${task.task_id}: match the PR that closes the issue or shares the path`;
  });
  const family_id = opts.run.family_id ?? opts.run.id;
  const brain = await complete({
    role: "patch",
    run_id: opts.run.id,
    family_id,
    version: opts.prior.version,
    system: "Propose short playbook patch lessons from DEV fails. One lesson per line.",
    prompt: [
      `DEV ${opts.run.id} accuracy=${opts.run.accuracy.toFixed(3)}`,
      `heuristic:\n${lessons.join("\n")}`,
      opts.prior.markdown ? `playbook:\n${opts.prior.markdown.slice(0, 1500)}` : "playbook empty",
    ].join("\n"),
    gate: patchGate,
  });
  if (brain.text) {
    const extra = brain.text
      .split(/\r?\n/)
      .map((l) => l.replace(/^[-*]\s*/, "").trim())
      .filter((l) => l.length > 8);
    lessons.push(...extra.slice(0, 4));
  }
  writeTrace({
    id: newId("trace"),
    run_id: opts.run.id,
    family_id,
    task_id: "patch",
    playbook_version: opts.prior.version,
    split: "dev",
    role: "patch",
    steps: [],
    spans: brain.spans,
    answer: { text: lessons.join("\n") },
    cost: { tool_calls: 0, tokens: brain.tokens, dollars: brain.dollars },
    speed_ms: brain.latency_ms,
    partners: brain.calls,
  });
  const version = nextPlaybookVersion();
  const markdown = renderPlaybook({
    version,
    repo: opts.prior.repo,
    labels: opts.prior.labels,
    owners: opts.prior.owners,
    grounded: !opts.prior.empty,
    contributing: opts.prior.markdown.includes("CONTRIBUTING") ? opts.prior.markdown : undefined,
    notes: [
      `patch from DEV ${opts.run.id} accuracy=${opts.run.accuracy.toFixed(3)}`,
      ...lessons,
      "search before list-all",
    ],
  });
  writePlaybook(version, markdown);
  return { version, reason: lessons[0] ?? "patch from fail patterns" };
}
