/** Presentation helpers for last-report.json. Artifact reader only — no agent loop. */

export type Score = {
  pass_rate: number;
  successes: number;
  n: number;
  cost: number;
  tokens: number;
  split: string;
  speed_ms?: number;
  tool_calls?: number;
  passed?: string[];
};

export type PlaybookEntry = {
  id: string;
  text: string;
  tags?: string[];
};

export type PlaybookRule = {
  id: string;
  text: string;
  tags?: string[];
  kind?: string;
  origin?: string;
  source?: string;
};

export type TraceSpan = {
  name: string;
  kind: string;
  input?: unknown;
  output?: unknown;
  duration_ms?: number;
  cost?: number;
  tokens?: number;
  model?: string;
  route?: "cheap" | "escalate" | string;
};

export type VersionSnapshot = {
  version: string;
  when: string;
  trigger?: string;
  lesson?: string;
  evidence?: { label: string; refs: string[] } | null;
  score: {
    pass_rate: number;
    successes: number;
    n: number;
    tool_calls: number;
    tokens: number;
    speed_ms: number;
    cost?: number;
  };
  playbook_size: number;
};

export type TaskRunResult = {
  id: string;
  type?: string;
  target?: string;
  passed?: boolean;
  ok?: boolean;
  duration_ms?: number;
  tool_calls?: number;
  tokens?: number;
  cost?: number;
  answer?: unknown;
  expected?: unknown;
  spans?: TraceSpan[];
};

export type Report = {
  challenge_id: string;
  mode: string;
  promoted: boolean;
  repo?: string;
  run1: Score;
  run_n: Score;
  hold_prior: Score | null;
  hold_candidate: Score | null;
  pointer: { active: string; candidate: string | null; prior: string | null };
  neatlogs_trace_id: string | null;
  neatlogs_url: string;
  journal_path: string;
  diff_path: string;
  journal: string;
  diff: string;
  playbook_entries: PlaybookEntry[];
  playbook_rules?: PlaybookRule[];
  redteam: { n: number; successes: number; pass_rate: number } | null;
  children: TraceSpan[];
  candidate_version?: string | null;
  version_history?: VersionSnapshot[];
  task_results?: {
    run1?: TaskRunResult[];
    run_n?: TaskRunResult[];
    hold_prior?: TaskRunResult[];
    hold_candidate?: TaskRunResult[];
  };
  demo_snapshot?: boolean;
  generated_at?: string;
};

export type Lesson = {
  id: string;
  text: string;
  source: "entry" | "rule";
  origin?: string;
  tags?: string[];
};

const TELEMETRY_LINE =
  /^(?:[-*]\s*)?(?:Run\d+\s+DEV\b|Reflect merged\b|promoted\s|Derived\s|Mined\s|candidate held\b|postmortem\s|# Journal\b|## (?:Lessons|Insights|Warnings)\b)/i;

const FAILURE_DUMP = /When asked .+ do not invent\.\s*Failed with/i;
const WEAK_ADVICE = /be helpful and confident|guess if you are unsure/i;
const TOOL_DUMP =
  /\{['"]found['"]|get_file_contents:|pull_request_read:|issue_read:|list_issues:|From repo evidence/i;

export function isTelemetryLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  return TELEMETRY_LINE.test(trimmed);
}

export function humanizeRuleText(text: string): string {
  const cleaned = text
    .replace(/^WHEN\s+/i, "If ")
    .replace(/\s+THEN\s+/i, ", ")
    .replace(/\['([^']+)'\]/g, "$1")
    .replace(/\["([^"]+)"\]/g, "$1")
    .replace(/\bcontains\b/g, "mentions")
    .replace(/\bset owner=/g, "set owner to ")
    .replace(/\badd labels=/g, "add label ")
    .replace(/\bset labels=/g, "set label ")
    .trim();
  return cleaned.replace(/,\s*$/, "").replace(/\s+/g, " ");
}

function splitEntryText(text: string): string[] {
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean);
}

function isHumanLesson(text: string): boolean {
  const line = text.trim();
  if (line.length < 12 || line.length > 280) return false;
  if (isTelemetryLine(line)) return false;
  if (FAILURE_DUMP.test(line)) return false;
  if (WEAK_ADVICE.test(line)) return false;
  if (TOOL_DUMP.test(line)) return false;
  return true;
}

function uniqueLessons(lessons: Lesson[]): Lesson[] {
  const seen = new Set<string>();
  const out: Lesson[] = [];
  for (const lesson of lessons) {
    const key = lesson.text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(lesson);
  }
  return out;
}

export function humanLessons(report: Pick<Report, "playbook_entries" | "playbook_rules">): Lesson[] {
  const fromEntries: Lesson[] = [];
  for (const entry of report.playbook_entries ?? []) {
    if ((entry.tags ?? []).includes("weak")) continue;
    for (const chunk of splitEntryText(entry.text ?? "")) {
      if (!isHumanLesson(chunk)) continue;
      fromEntries.push({
        id: entry.id,
        text: chunk.replace(/^Rule:\s*/i, ""),
        source: "entry",
        tags: entry.tags,
      });
    }
  }

  const fromRules: Lesson[] = [];
  for (const rule of report.playbook_rules ?? []) {
    const raw = (rule.text ?? "").trim();
    if (!raw || isTelemetryLine(raw)) continue;
    const text = humanizeRuleText(raw);
    if (!isHumanLesson(text) && text.length > 280) continue;
    if (text.length < 12) continue;
    fromRules.push({
      id: rule.id,
      text,
      source: "rule",
      origin: rule.origin ?? rule.source,
      tags: rule.tags,
    });
  }

  return uniqueLessons([...fromEntries, ...fromRules]);
}

export function challengeLessons(report: Pick<Report, "playbook_entries" | "playbook_rules">): Lesson[] {
  return humanLessons(report).slice(0, 4);
}

export function journalLessons(report: Pick<Report, "playbook_entries" | "playbook_rules">): Lesson[] {
  return humanLessons(report).slice(0, 8);
}

export function systemLogLines(journal: string): string[] {
  if (!journal.trim()) return [];
  return journal
    .split(/\r?\n/)
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter((line) => isTelemetryLine(line) && !/^#/.test(line));
}

export function isWeakPlaybook(report: Pick<Report, "playbook_entries" | "pointer">): boolean {
  const entries = report.playbook_entries ?? [];
  if (entries.length === 0) return true;
  if (entries.every((entry) => (entry.tags ?? []).includes("weak"))) return true;
  const active = (report.pointer?.active ?? "").toLowerCase();
  return active === "weak-0" || active === "v0" || active.startsWith("weak");
}

export function deltaLabel(
  before: number,
  after: number,
  { invert = false } = {},
): "up" | "down" | "flat" {
  const better = invert ? after < before : after > before;
  const worse = invert ? after > before : after < before;
  if (better) return "up";
  if (worse) return "down";
  return "flat";
}

export function formatCost(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "$0";
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

export function formatPct(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 1000) / 10}%`;
}

export function formatMs(value?: number): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)}ms`;
}

export function formatTokens(value?: number): string {
  if (value === undefined) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function toolsOf(score: Score): number {
  return score.tool_calls ?? 0;
}

const NEATLOGS_APP = "https://app.neatlogs.com";
const NEATLOGS_ORG = "8bd3fd8b-e753-4ace-8eeb-da3006f631f3";
const NEATLOGS_PROJECT = "66d21721-995d-49b1-83e1-0427e9b56059";

export function cockpitHref(report: Pick<Report, "neatlogs_trace_id" | "neatlogs_url">): string {
  const raw = report.neatlogs_url || "";
  if (raw.includes("/traces/")) return raw;
  const fromQuery = raw.match(/[?&]trace_id=([^&]+)/)?.[1];
  const id = report.neatlogs_trace_id || fromQuery;
  if (!id) return NEATLOGS_APP;
  return `${NEATLOGS_APP}/traces/${id}?orgId=${NEATLOGS_ORG}&projectId=${NEATLOGS_PROJECT}`;
}

export function speedOf(score: Score): number {
  return score.speed_ms ?? 0;
}

export function deltaPct(before: number, after: number): string {
  if (before === 0 && after === 0) return "0%";
  if (before === 0) return "+∞";
  const pct = ((after - before) / Math.abs(before)) * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(pct >= 10 || pct <= -10 ? 0 : 1)}%`;
}

export function ratioBar(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0.02, Math.min(1, value / max));
}

/** Map DEV task ids to pass/fail for a given run. */
export function taskMatrix(
  results: TaskRunResult[] | undefined,
  taskIds: string[],
): Map<string, boolean> {
  const map = new Map<string, boolean>();
  if (!results) return map;
  const idx = new Map(results.map((r) => [r.id, r]));
  for (const id of taskIds) {
    const hit = idx.get(id);
    if (!hit) continue;
    const p = hit.passed ?? hit.ok;
    map.set(id, !!p);
  }
  return map;
}

/** Version history — either explicit array or derived from run1/run_n. */
export function versionHistory(report: Report): VersionSnapshot[] {
  if (report.version_history && report.version_history.length > 0) {
    return report.version_history;
  }
  return [
    {
      version: report.pointer.prior ?? "v0",
      when: "cold start",
      trigger: "empty playbook",
      lesson: "no prior lessons",
      evidence: null,
      score: {
        pass_rate: report.run1.pass_rate,
        successes: report.run1.successes,
        n: report.run1.n,
        tool_calls: toolsOf(report.run1),
        tokens: report.run1.tokens,
        speed_ms: speedOf(report.run1),
        cost: report.run1.cost,
      },
      playbook_size: 0,
    },
    {
      version: report.pointer.active,
      when: "post-reflect",
      trigger: "DEV failure analysis",
      lesson: "merged playbook from failed traces",
      evidence: null,
      score: {
        pass_rate: report.run_n.pass_rate,
        successes: report.run_n.successes,
        n: report.run_n.n,
        tool_calls: toolsOf(report.run_n),
        tokens: report.run_n.tokens,
        speed_ms: speedOf(report.run_n),
        cost: report.run_n.cost,
      },
      playbook_size: report.playbook_entries.length,
    },
  ];
}
