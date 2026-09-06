import type { ActorAnswer, EvalTask, Expected, KeyCatalog } from "./types.js";

function uniqSorted(xs: string[]): string[] {
  return [...new Set(xs.map((x) => x.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

export function sameLabelSet(got: string[] | undefined, expected: string[] | undefined): boolean {
  if (!expected) return false;
  return uniqSorted(got ?? []).join("\0") === uniqSorted(expected).join("\0");
}

function catalogIssueNumber(catalog: KeyCatalog | undefined, key: string): number | undefined {
  const n = catalog?.issues[key]?.number;
  return n && n > 0 ? n : undefined;
}

function catalogPrNumber(catalog: KeyCatalog | undefined, key: string): number | undefined {
  const n = catalog?.prs[key]?.number;
  return n && n > 0 ? n : undefined;
}

function asKey(value: string | number | undefined): string | undefined {
  if (value === undefined || value === null) return undefined;
  return String(value);
}

export function scoreTask(task: EvalTask, answer: ActorAnswer, catalog?: KeyCatalog): number {
  const expected = task.expected ?? {};
  switch (task.type) {
    case "label":
      return sameLabelSet(answer.labels, expected.labels) ? 1 : 0;
    case "duplicate":
      return matchRef(answer.duplicate_of, expected.duplicate_of, catalog, "issue") ? 1 : 0;
    case "owner":
      return (answer.owner ?? "").trim().toLowerCase() === (expected.owner ?? "").trim().toLowerCase()
        ? 1
        : 0;
    case "summarize":
      return keysPresent(answer, expected) ? 1 : 0;
    case "fix_pr":
      return matchRef(answer.pr, expected.pr, catalog, "pr") ? 1 : 0;
    default:
      return 0;
  }
}

function matchRef(
  got: string | number | undefined,
  expected: string | number | undefined,
  catalog: KeyCatalog | undefined,
  kind: "issue" | "pr",
): boolean {
  if (got === undefined || expected === undefined) return false;
  const gotS = asKey(got)!;
  const expS = asKey(expected)!;
  if (gotS.toLowerCase() === expS.toLowerCase()) return true;

  const gotN = Number(gotS);
  const expN = Number(expS);
  if (Number.isFinite(gotN) && Number.isFinite(expN) && gotN > 0 && expN > 0 && gotN === expN) {
    return true;
  }

  if (kind === "issue") {
    const expNum = typeof expected === "string" ? catalogIssueNumber(catalog, expected) : expN;
    const gotNum = typeof got === "string" && got.startsWith("I") ? catalogIssueNumber(catalog, got) : gotN;
    if (expNum && gotNum && expNum === gotNum) return true;
    if (typeof expected === "string" && gotN > 0 && catalogIssueNumber(catalog, expected) === gotN) return true;
    if (typeof got === "string" && expN > 0 && catalogIssueNumber(catalog, got) === expN) return true;
  } else {
    const expNum = typeof expected === "string" ? catalogPrNumber(catalog, expected) : expN;
    const gotNum = typeof got === "string" && got.startsWith("P") ? catalogPrNumber(catalog, got) : gotN;
    if (expNum && gotNum && expNum === gotNum) return true;
    if (typeof expected === "string" && gotN > 0 && catalogPrNumber(catalog, expected) === gotN) return true;
    if (typeof got === "string" && expN > 0 && catalogPrNumber(catalog, got) === expN) return true;
  }
  return false;
}

function keysPresent(answer: ActorAnswer, expected: Expected): boolean {
  const need = expected.keys ?? [];
  if (!need.length) return false;
  const blob = `${(answer.keys ?? []).join(" ")} ${answer.text ?? ""}`.toUpperCase();
  return need.every((k) => blob.includes(String(k).toUpperCase()));
}

export function mean(xs: number[]): number {
  if (!xs.length) return 0;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

export function estimateTokens(value: unknown): number {
  const n = JSON.stringify(value ?? "").length;
  return Math.max(1, Math.ceil(n / 4));
}
