import type { KeyCatalog, PlaybookFacts, RunRecord, ToolCaller, Trace } from "./types.js";
import { jsonFromMcp, textFromMcp } from "./mcp.js";
import { parseCodeowners } from "./actor.js";
import { complete, reflectGate } from "./partners/brain.js";
import { writeTrace } from "./partners/sink.js";
import { renderPlaybook } from "./playbook.js";
import { appendJournalLesson } from "./journal.js";
import { newId, nextPlaybookVersion, writePlaybook } from "./store.js";
import { readScripts, writeScripts } from "./scripts.js";

export async function reflectDev(opts: {
  run: RunRecord;
  traces: Trace[];
  prior: PlaybookFacts;
  catalog: KeyCatalog;
  tools: ToolCaller;
}): Promise<{ version: number; markdown: string }> {
  const contributing = await readAllowed(opts.tools, opts.catalog, "CONTRIBUTING.md");
  const codeowners = await readAllowed(opts.tools, opts.catalog, "CODEOWNERS");
  const labels = await listLabels(opts.tools, opts.catalog);

  const owners = {
    ...opts.prior.owners,
    ...parseCodeowners(codeowners),
  };

  const observedLabels = new Set(opts.prior.labels);
  for (const name of labels) observedLabels.add(name);
  for (const def of [
    "type:bug",
    "type:feat",
    "type:docs",
    "area:api",
    "area:runtime",
    "area:billing",
    "area:ui",
    "priority:p0",
    "priority:p1",
  ]) {
    if (contributing.includes(def) || labels.includes(def)) observedLabels.add(def);
  }
  const grounded = Boolean(contributing && /stack trace|type:bug|priority:p0/i.test(contributing));

  const listCalls = opts.traces.reduce(
    (n, t) => n + t.steps.filter((s) => s.tool === "list_issues" || s.tool === "list_pull_requests").length,
    0,
  );
  const notes = [
    `from DEV run ${opts.run.id} accuracy=${opts.run.accuracy.toFixed(3)} cost=${opts.run.cost.tool_calls} tools`,
    listCalls > 4
      ? "list-all was expensive; next run should search before list-all"
      : "prefer targeted issue_read / search_issues",
    contributing ? "CONTRIBUTING.md fetched and merged" : "CONTRIBUTING.md missing or MCP failed — keep trying next DEV",
    codeowners ? "CODEOWNERS fetched; logical owners are directory names, not GitHub handles" : "CODEOWNERS missing",
  ];
  const family_id = opts.run.family_id ?? opts.run.id;
  const brain = await complete({
    role: "reflect",
    run_id: opts.run.id,
    family_id,
    version: opts.prior.version,
    system: "Return short playbook / journal notes. One lesson per line.",
    prompt: [
      `DEV accuracy=${opts.run.accuracy.toFixed(3)} tools=${opts.run.cost.tool_calls}`,
      `failed=${opts.run.tasks.filter((t) => t.accuracy < 1).map((t) => t.task_id).join(",") || "(none)"}`,
      `heuristic notes:\n${notes.join("\n")}`,
      contributing ? `CONTRIBUTING excerpt:\n${contributing.slice(0, 1200)}` : "CONTRIBUTING missing",
    ].join("\n"),
    gate: reflectGate,
  });
  if (brain.text) {
    const extra = brain.text
      .split(/\r?\n/)
      .map((l) => l.replace(/^[-*]\s*/, "").trim())
      .filter((l) => l.length > 8 && !notes.includes(l));
    notes.push(...extra.slice(0, 6));
  }
  writeTrace({
    id: newId("trace"),
    run_id: opts.run.id,
    family_id,
    task_id: "reflect",
    playbook_version: opts.prior.version,
    split: "dev",
    role: "reflect",
    steps: [],
    spans: brain.spans,
    answer: { text: notes.join("\n") },
    cost: { tool_calls: 0, tokens: brain.tokens, dollars: brain.dollars },
    speed_ms: brain.latency_ms,
    partners: brain.calls,
  });

  const version = nextPlaybookVersion();
  const markdown = renderPlaybook({
    version,
    repo: opts.catalog.repo,
    labels: [...observedLabels],
    owners,
    contributing: contributing || undefined,
    grounded,
    notes,
  });
  writePlaybook(version, markdown);
  appendJournalLesson({
    run: opts.run,
    traces: opts.traces,
    playbookVersion: version,
    notes,
  });
  const scripts = readScripts();
  writeScripts(scripts);
  return { version, markdown };
}

async function readAllowed(tools: ToolCaller, catalog: KeyCatalog, path: string): Promise<string> {
  try {
    const raw = await tools.call("get_file_contents", {
      owner: catalog.owner,
      repo: catalog.name,
      path,
    });
    const parsed = jsonFromMcp<{ content?: string; text?: string }>(raw);
    if (parsed?.content) {
      try {
        return Buffer.from(parsed.content, "base64").toString("utf8");
      } catch {
        return parsed.content;
      }
    }
    if (parsed?.text) return parsed.text;
    return textFromMcp(raw);
  } catch {
    return "";
  }
}

async function listLabels(tools: ToolCaller, catalog: KeyCatalog): Promise<string[]> {
  try {
    const raw = await tools.call("list_label", { owner: catalog.owner, repo: catalog.name });
    const parsed = jsonFromMcp<unknown>(raw);
    const items = Array.isArray(parsed)
      ? parsed
      : parsed && typeof parsed === "object" && Array.isArray((parsed as { labels?: unknown[] }).labels)
        ? (parsed as { labels: unknown[] }).labels
        : [];
    return items
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "name" in item) return String((item as { name: unknown }).name);
        return "";
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}
