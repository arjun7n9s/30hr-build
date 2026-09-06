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
  children: { name: string; kind: string; input?: unknown; output?: unknown }[];
  candidate_version?: string | null;
};

export type Lesson = {
  id: string;
  text: string;
  source: "entry" | "rule";
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

/** Human playbook lines for judges. Never CORE.md telemetry. */
export function humanLessons(report: Pick<Report, "playbook_entries" | "playbook_rules">): Lesson[] {
  const fromEntries: Lesson[] = [];
  for (const entry of report.playbook_entries ?? []) {
    if ((entry.tags ?? []).includes("weak")) continue;
    for (const chunk of splitEntryText(entry.text ?? "")) {
      if (!isHumanLesson(chunk)) continue;
      fromEntries.push({ id: entry.id, text: chunk.replace(/^Rule:\s*/i, ""), source: "entry" });
    }
  }

  const fromRules: Lesson[] = [];
  for (const rule of report.playbook_rules ?? []) {
    const raw = (rule.text ?? "").trim();
    if (!raw || isTelemetryLine(raw)) continue;
    const text = humanizeRuleText(raw);
    if (!isHumanLesson(text) && text.length > 280) continue;
    if (text.length < 12) continue;
    fromRules.push({ id: rule.id, text, source: "rule" });
  }

  // Prefer a mix: entry prose first, then distinct rule beliefs.
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

export function deltaLabel(before: number, after: number, { invert = false } = {}): string {
  const better = invert ? after < before : after > before;
  const worse = invert ? after > before : after < before;
  if (better) return "up";
  if (worse) return "down";
  return "flat";
}

export function formatCost(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  if (value >= 1) return value.toFixed(2);
  return value.toFixed(4);
}

export function formatPct(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 1000) / 10}%`;
}

export function toolsOf(score: Score): number {
  return score.tool_calls ?? 0;
}
