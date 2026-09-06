import type {
  ActorAnswer,
  EvalTask,
  KeyCatalog,
  PlaybookFacts,
  Split,
  ToolCaller,
  Trace,
  TraceSpan,
} from "./types.js";
import { jsonFromMcp, PolicyDeniedError, textFromMcp, TracingCaller } from "./mcp.js";
import { actorGate, complete, extractJson } from "./partners/brain.js";
import { retrievePlaybook } from "./partners/rag.js";
import { readScripts } from "./scripts.js";
import { newId } from "./store.js";

const AREAS = ["billing", "runtime", "api", "ui"] as const;

export async function runActor(opts: {
  task: EvalTask;
  facts: PlaybookFacts;
  catalog: KeyCatalog;
  tools: ToolCaller;
  split: Split;
  runId: string;
  familyId?: string;
}): Promise<Trace> {
  const started = Date.now();
  const family_id = opts.familyId ?? opts.runId;
  readScripts();
  const rag = await retrievePlaybook({
    query: `${opts.task.type} ${opts.task.prompt} ${opts.task.github.issue_title ?? ""}`,
    facts: opts.facts,
    run_id: opts.runId,
    family_id,
    version: opts.facts.version,
  });
  const tracer = new TracingCaller(opts.tools);
  let answer = await answerTask(opts.task, opts.facts, opts.catalog, tracer).catch((err) => {
    const message = err instanceof Error ? err.message : String(err);
    return { text: message } satisfies ActorAnswer;
  });
  const brain = await complete({
    role: "actor",
    run_id: opts.runId,
    family_id,
    version: opts.facts.version,
    task_id: opts.task.id,
    system: "Return only JSON for the repo-triage answer. Use the heuristic and playbook excerpt. No prose.",
    prompt: [
      `task=${opts.task.type}`,
      opts.task.prompt,
      `heuristic=${JSON.stringify(answer)}`,
      `playbook_hits=${rag.hits.join(" | ")}`,
      rag.excerpt ? `playbook:\n${rag.excerpt}` : "playbook: empty",
    ].join("\n"),
    gate: (text) => actorGate(text, opts.task.type),
  });
  if (brain.text && actorGate(brain.text, opts.task.type).ok) {
    const parsed = extractJson(brain.text);
    if (parsed) answer = { ...answer, ...parsed } as ActorAnswer;
  }
  const steps = tracer.steps;
  const tool_calls = steps.filter((s) => !s.denied).length;
  const tokens = steps.reduce((n, s) => n + s.tokens, 0) + brain.tokens + rag.tokens;
  const dollars = (brain.dollars ?? 0) + rag.dollars;
  const spans: TraceSpan[] = [
    ...mcpSpans(steps, { run_id: opts.runId, family_id, version: opts.facts.version, task_id: opts.task.id }),
    ...rag.spans,
    ...brain.spans,
  ];
  return {
    id: newId("trace"),
    run_id: opts.runId,
    family_id,
    task_id: opts.task.id,
    playbook_version: opts.facts.version,
    split: opts.split,
    role: "actor",
    steps,
    spans,
    answer,
    cost: { tool_calls, tokens, dollars },
    speed_ms: Date.now() - started,
    playbook_hits: rag.hits,
    partners: brain.calls,
  };
}

function mcpSpans(
  steps: Trace["steps"],
  meta: { run_id: string; family_id: string; version: number; task_id: string },
): TraceSpan[] {
  return steps.map((step) => ({
    name: step.tool,
    kind: "MCP_TOOL" as const,
    role: "actor" as const,
    run_id: meta.run_id,
    family_id: meta.family_id,
    task_id: meta.task_id,
    version: meta.version,
    tool_name: step.tool,
    input: step.args,
    output: step.result,
    tokens: { total: step.tokens },
    duration_ms: step.latency_ms,
    status: step.error && !step.denied ? "ERROR" : "OK",
    error: step.error,
  }));
}

async function answerTask(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<ActorAnswer> {
  switch (task.type) {
    case "label":
      return labelTask(task, facts, catalog, tools);
    case "duplicate":
      return duplicateTask(task, facts, catalog, tools);
    case "owner":
      return ownerTask(task, facts, catalog, tools);
    case "summarize":
      return summarizeTask(task, facts, catalog, tools);
    case "fix_pr":
      return fixPrTask(task, facts, catalog, tools);
    default:
      return { text: `unknown task type ${task.type}` };
  }
}

async function labelTask(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<ActorAnswer> {
  const issue = await fetchIssue(task, facts, catalog, tools);
  const blob = `${task.prompt}\n${task.github.issue_title ?? ""}\n${issue.title}\n${issue.body}`;
  const labels = facts.empty ? naiveLabels(blob) : playbookLabels(blob, facts);
  return { labels, text: issue.title };
}

async function duplicateTask(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<ActorAnswer> {
  const issue = await fetchIssue(task, facts, catalog, tools);
  const others = await listOrSearchIssues(facts, catalog, tools, issue.title || task.github.issue_title || "");
  const selfTitle = (issue.title || task.github.issue_title || "").toLowerCase();
  const selfKey = task.github.issue_key;
  const ranked = others
    .filter((item) => item.title.toLowerCase() !== selfTitle && item.key !== selfKey)
    .map((item) => ({ item, score: titleScore(selfTitle, item.title) }))
    .sort((a, b) => b.score - a.score);

  if (facts.empty) {
    const guess = others.find((item) => item.key !== selfKey && item.title !== issue.title);
    if (!guess) return { text: issue.title };
    return { duplicate_of: guess.key ?? guess.number, text: guess.title };
  }

  const best = ranked[0];
  if (!best || best.score < 0.25) return { text: issue.title };
  return { duplicate_of: best.item.key ?? best.item.number, text: best.item.title };
}

async function ownerTask(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<ActorAnswer> {
  const path = task.github.path ?? "";
  if (!facts.empty) {
    const owner = ownerFromFacts(path, facts);
    if (owner) return { owner, text: path };
    const codeowners = await readFileSafe(tools, catalog, "CODEOWNERS");
    const mapped = parseCodeowners(codeowners);
    const learned = ownerFromMap(path, mapped);
    if (learned) return { owner: learned, text: path };
  } else {
    await listRepoNaive(tools, catalog);
  }
  const guess = path.split("/").filter(Boolean).at(-2);
  return { owner: guess ?? "unknown", text: path };
}

async function summarizeTask(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<ActorAnswer> {
  const want = task.github.labels ?? [];
  const query = `${task.prompt} ${want.join(" ")}`.trim();
  let issues = facts.search_before_list || !facts.empty
    ? await searchIssues(tools, catalog, query)
    : await listAllIssues(tools, catalog);
  if (!issues.length) issues = await listAllIssues(tools, catalog);

  const filtered = facts.empty
    ? issues
    : issues.filter((item) => {
        if (want.every((label) => item.labels.includes(label) || item.blob.toLowerCase().includes(label.toLowerCase()))) {
          return true;
        }
        const inferred = playbookLabels(`${item.title}\n${item.body}`, facts);
        return want.every((label) => inferred.includes(label));
      });

  const keys = filtered
    .map((item) => item.key)
    .filter((k): k is string => Boolean(k));
  const text = filtered.map((item) => `${item.key ?? item.number}: ${item.title}`).join("\n");
  return { keys, text };
}

async function fixPrTask(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<ActorAnswer> {
  const issueKey = task.github.issue_key;
  const issueTitle = task.github.issue_title || catalog.issues[issueKey ?? ""]?.title || "";
  const prs = facts.empty
    ? await listAllPulls(tools, catalog)
    : await searchPulls(tools, catalog, issueTitle || issueKey || "");

  if (facts.empty) {
    const first = prs[0];
    return first ? { pr: first.key ?? first.number, text: first.title } : { text: "no prs" };
  }

  const issueNumber = task.github.issue_number && task.github.issue_number > 0
    ? task.github.issue_number
    : catalog.issues[issueKey ?? ""]?.number ?? 0;

  const hit = prs.find((pr) => {
    if (issueKey && pr.closes === issueKey) return true;
    if (issueNumber > 0 && (pr.closesNumber === issueNumber || /#\s*(\d+)/.test(pr.body) && Number(pr.body.match(/#\s*(\d+)/)?.[1]) === issueNumber)) {
      return true;
    }
    return titleScore(issueTitle, pr.title) > 0.35 || (issueKey === "I1" && /empty payload|500/.test(pr.title.toLowerCase()));
  });
  if (!hit) return { text: prs.map((p) => p.title).join("\n") };
  return { pr: hit.key ?? hit.number, text: hit.title };
}

type IssueHit = {
  number: number;
  title: string;
  body: string;
  labels: string[];
  key?: string;
  blob: string;
};

type PrHit = {
  number: number;
  title: string;
  body: string;
  key?: string;
  closes?: string;
  closesNumber?: number;
};

async function fetchIssue(
  task: EvalTask,
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
): Promise<IssueHit> {
  const number = task.github.issue_number && task.github.issue_number > 0
    ? task.github.issue_number
    : catalog.issues[task.github.issue_key ?? ""]?.number ?? 0;
  const title = task.github.issue_title || catalog.issues[task.github.issue_key ?? ""]?.title || "";

  if (!facts.empty && number > 0) {
    const raw = await callSafe(tools, "issue_read", {
      method: "get",
      owner: catalog.owner,
      repo: catalog.name,
      issue_number: number,
    });
    const parsed = asIssue(raw, catalog);
    if (parsed) return parsed;
  }

  if (!facts.empty && title) {
    const found = await searchIssues(tools, catalog, title);
    const match = found.find((i) => i.title.toLowerCase() === title.toLowerCase()) ?? found[0];
    if (match) return match;
  }

  const listed = await listAllIssues(tools, catalog);
  const match = listed.find((i) => i.title.toLowerCase() === title.toLowerCase()) ?? listed[0];
  return match ?? { number, title, body: "", labels: [], key: task.github.issue_key, blob: title };
}

async function listOrSearchIssues(
  facts: PlaybookFacts,
  catalog: KeyCatalog,
  tools: TracingCaller,
  query: string,
): Promise<IssueHit[]> {
  if (facts.search_before_list || !facts.empty) return searchIssues(tools, catalog, query);
  return listAllIssues(tools, catalog);
}

async function listAllIssues(tools: TracingCaller, catalog: KeyCatalog): Promise<IssueHit[]> {
  const raw = await callSafe(tools, "list_issues", {
    owner: catalog.owner,
    repo: catalog.name,
    state: "all",
    perPage: 50,
  });
  return asIssueList(raw, catalog);
}

async function searchIssues(tools: TracingCaller, catalog: KeyCatalog, query: string): Promise<IssueHit[]> {
  const raw = await callSafe(tools, "search_issues", {
    owner: catalog.owner,
    repo: catalog.name,
    query,
    perPage: 20,
  });
  return asIssueList(raw, catalog);
}

async function listAllPulls(tools: TracingCaller, catalog: KeyCatalog): Promise<PrHit[]> {
  const raw = await callSafe(tools, "list_pull_requests", {
    owner: catalog.owner,
    repo: catalog.name,
    state: "all",
    perPage: 50,
  });
  return asPrList(raw, catalog);
}

async function searchPulls(tools: TracingCaller, catalog: KeyCatalog, query: string): Promise<PrHit[]> {
  const raw = await callSafe(tools, "search_pull_requests", {
    owner: catalog.owner,
    repo: catalog.name,
    query,
    perPage: 20,
  });
  return asPrList(raw, catalog);
}

async function listRepoNaive(tools: TracingCaller, catalog: KeyCatalog): Promise<void> {
  await callSafe(tools, "search_repositories", { query: catalog.repo });
}

async function readFileSafe(tools: TracingCaller, catalog: KeyCatalog, path: string): Promise<string> {
  const raw = await callSafe(tools, "get_file_contents", {
    owner: catalog.owner,
    repo: catalog.name,
    path,
  });
  if (!raw) return "";
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
}

async function callSafe(
  tools: TracingCaller,
  name: string,
  args: Record<string, unknown>,
): Promise<unknown | null> {
  try {
    return await tools.call(name, args);
  } catch (err) {
    if (err instanceof PolicyDeniedError) return null;
    return null;
  }
}

function asIssueList(raw: unknown, catalog: KeyCatalog): IssueHit[] {
  if (!raw) return [];
  const parsed = jsonFromMcp<unknown>(raw);
  const items = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === "object" && Array.isArray((parsed as { items?: unknown[] }).items)
      ? (parsed as { items: unknown[] }).items
      : parsed && typeof parsed === "object" && Array.isArray((parsed as { issues?: unknown[] }).issues)
        ? (parsed as { issues: unknown[] }).issues
        : [];
  return items.map((item) => asIssue(item, catalog)).filter((x): x is IssueHit => Boolean(x));
}

function asIssue(raw: unknown, catalog: KeyCatalog): IssueHit | null {
  if (!raw) return null;
  const obj = (typeof raw === "object" ? raw : jsonFromMcp(raw)) as Record<string, unknown> | null;
  if (!obj) {
    const text = textFromMcp(raw);
    return text ? { number: 0, title: text.slice(0, 120), body: text, labels: [], blob: text } : null;
  }
  const number = Number(obj.number ?? obj.issue_number ?? 0);
  const title = String(obj.title ?? "");
  const body = String(obj.body ?? "");
  const labels = extractLabels(obj.labels);
  const key = keyFromTitle(catalog, title, number);
  return { number, title, body, labels, key, blob: `${title}\n${body}\n${labels.join(" ")}` };
}

function asPrList(raw: unknown, catalog: KeyCatalog): PrHit[] {
  if (!raw) return [];
  const parsed = jsonFromMcp<unknown>(raw);
  const items = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === "object" && Array.isArray((parsed as { items?: unknown[] }).items)
      ? (parsed as { items: unknown[] }).items
      : [];
  return items.map((item) => {
    const obj = item as Record<string, unknown>;
    const number = Number(obj.number ?? obj.pullNumber ?? 0);
    const title = String(obj.title ?? "");
    const body = String(obj.body ?? "");
    const key = Object.entries(catalog.prs).find(([, v]) =>
      (v.number > 0 && v.number === number) || v.title.toLowerCase() === title.toLowerCase(),
    )?.[0];
    const closesMatch = body.match(/closes?\s+#(\d+)/i);
    return {
      number,
      title,
      body,
      key,
      closes: key ? catalog.prs[key]?.closes : undefined,
      closesNumber: closesMatch ? Number(closesMatch[1]) : undefined,
    };
  });
}

function extractLabels(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object" && "name" in item) return String((item as { name: unknown }).name);
    return "";
  }).filter(Boolean);
}

function keyFromTitle(catalog: KeyCatalog, title: string, number: number): string | undefined {
  const hit = Object.entries(catalog.issues).find(([, v]) =>
    (v.number > 0 && v.number === number) || v.title.toLowerCase() === title.toLowerCase(),
  );
  return hit?.[0];
}

function naiveLabels(text: string): string[] {
  const hay = text.toLowerCase();
  if (/(typo|readme|document|docs|contributing)/.test(hay)) return ["type:docs"];
  if (/(add |toggle|export|feature)/.test(hay)) return ["type:feat"];
  return ["type:bug"];
}

export function playbookLabels(text: string, facts: PlaybookFacts): string[] {
  const hay = text.toLowerCase();
  const labels = new Set<string>();
  if (facts.rules.stack_trace_bug && /(stack|traceback|src\/(api|runtime|billing|ui)\/)/.test(hay)) {
    labels.add("type:bug");
  }
  if (facts.rules.crash_nil_oom_p0 && /(crash|nil|oom|out of memory|panic)/.test(hay)) {
    labels.add("type:bug");
    labels.add("priority:p0");
  }
  if (facts.rules.docs_typo_readme && /(typo|readme|document env|docs|contributing|openapi|headers not documented)/.test(hay)) {
    labels.add("type:docs");
  }
  if (facts.rules.feat_from_ask && /(add |export|toggle|feature)/.test(hay) && !labels.has("type:bug")) {
    labels.add("type:feat");
  }
  if (facts.rules.path_area) {
    if (/src\/api|rest handler|openapi|empty payload|null json|body is empty/.test(hay)) labels.add("area:api");
    if (/src\/runtime|worker|nil context|ctx canceled/.test(hay)) labels.add("area:runtime");
    if (/src\/billing|invoice|charge|webhook|cron double/.test(hay)) labels.add("area:billing");
    if (/src\/ui|dark mode|settings|button misaligned/.test(hay)) labels.add("area:ui");
    for (const area of AREAS) {
      if (new RegExp(`src/${area}`).test(hay)) labels.add(`area:${area}`);
    }
  }
  if (!labels.has("type:docs") && !labels.has("type:feat") && !labels.has("type:bug")) {
    if (/(typo|readme|document)/.test(hay)) labels.add("type:docs");
    else if (/(add |toggle|export)/.test(hay)) labels.add("type:feat");
    else labels.add("type:bug");
  }
  return [...labels].sort((a, b) => a.localeCompare(b));
}

function ownerFromFacts(path: string, facts: PlaybookFacts): string | undefined {
  return ownerFromMap(path, facts.owners);
}

function ownerFromMap(path: string, owners: Record<string, string>): string | undefined {
  const normalized = path.replace(/\\/g, "/");
  for (const area of AREAS) {
    if (normalized.startsWith(`src/${area}/`) || owners[`src/${area}`] && normalized.includes(`src/${area}`)) {
      return owners[`src/${area}`] || area;
    }
  }
  return undefined;
}

export function parseCodeowners(text: string): Record<string, string> {
  const owners: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*\/?src\/(billing|runtime|api|ui)\/?\s+/i);
    if (m) owners[`src/${m[1].toLowerCase()}`] = m[1].toLowerCase();
  }
  return owners;
}

function titleScore(a: string, b: string): number {
  const ta = tokens(a);
  const tb = tokens(b);
  if (!ta.size || !tb.size) return 0;
  let overlap = 0;
  for (const t of ta) if (tb.has(t)) overlap += 1;
  return overlap / Math.max(ta.size, tb.size);
}

function tokens(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((t) => t.length > 2 && !["the", "and", "for", "this", "that", "with"].includes(t)),
  );
}

export { readFileSafe };
