import { existsSync, readFileSync } from "node:fs";
import type { EvalFile, KeyCatalog } from "./types.js";
import { EVAL_DEV_PATH, EVAL_HOLDOUT_PATH, EVAL_NUMBERS_PATH } from "./paths.js";

const ISSUE_TITLES: Record<string, string> = {
  I1: "API returns 500 on empty payload",
  I2: "Add invoice PDF export",
  I3: "README typo in install section",
  I4: "Runtime worker leaks memory after 2h",
  I5: "Crash loop on nil context",
  I6: "Dark mode toggle",
  I7: "Charge webhook retries twice",
  I8: "Document env vars",
  I9: "API returns 500 when body is empty",
  I10: "Worker OOM after long run",
  I11: "OpenAPI spec missing 400 examples",
  I12: "Billing cron double-charges on retry",
  I13: "Add CSV export for invoices",
  I14: "Panic in worker when ctx canceled",
  I15: "Fix typo in contributing guide",
  I16: "UI button misaligned on settings",
  I17: "REST handler 500 on null JSON",
  I18: "Rate limit headers not documented",
};

const PR_TITLES: Record<string, { title: string; closes?: string }> = {
  P1: { title: "Fix empty payload 500 in API", closes: "I1" },
  P2: { title: "Cap runtime worker memory", closes: "I4" },
  P3: { title: "Idempotent billing webhook", closes: "I7" },
  P4: { title: "Settings page layout" },
};

export function loadEvalFile(path: string): EvalFile {
  return JSON.parse(readFileSync(path, "utf8")) as EvalFile;
}

export function loadCatalog(devPath = EVAL_DEV_PATH, holdoutPath = EVAL_HOLDOUT_PATH): KeyCatalog {
  const files = [loadEvalFile(devPath), loadEvalFile(holdoutPath)];
  const repo = files[0]?.repo ?? "arjun7n9s/journeyman-fixture";
  const [owner, name] = repo.split("/");
  const issues: KeyCatalog["issues"] = {};
  const prs: KeyCatalog["prs"] = {};

  for (const [key, title] of Object.entries(ISSUE_TITLES)) {
    issues[key] = { number: 0, title };
  }
  for (const [key, meta] of Object.entries(PR_TITLES)) {
    prs[key] = { number: 0, title: meta.title, closes: meta.closes };
  }

  if (existsSync(EVAL_NUMBERS_PATH)) {
    const harvested = JSON.parse(readFileSync(EVAL_NUMBERS_PATH, "utf8")) as {
      issues?: Record<string, number>;
      prs?: Record<string, number>;
    };
    for (const [key, number] of Object.entries(harvested.issues ?? {})) {
      if (number > 0) issues[key] = { number, title: issues[key]?.title || ISSUE_TITLES[key] || key };
    }
    for (const [key, number] of Object.entries(harvested.prs ?? {})) {
      if (number > 0) {
        prs[key] = {
          number,
          title: prs[key]?.title || PR_TITLES[key]?.title || key,
          closes: prs[key]?.closes || PR_TITLES[key]?.closes,
        };
      }
    }
  }

  for (const file of files) {
    for (const task of file.tasks) {
      const g = task.github ?? {};
      if (g.issue_key) {
        issues[g.issue_key] = {
          number: g.issue_number && g.issue_number > 0 ? g.issue_number : issues[g.issue_key]?.number ?? 0,
          title: g.issue_title || issues[g.issue_key]?.title || ISSUE_TITLES[g.issue_key] || g.issue_key,
        };
      }
      if (g.pr_key) {
        prs[g.pr_key] = {
          number: g.pr_number && g.pr_number > 0 ? g.pr_number : prs[g.pr_key]?.number ?? 0,
          title: prs[g.pr_key]?.title || PR_TITLES[g.pr_key]?.title || g.pr_key,
          closes: prs[g.pr_key]?.closes || PR_TITLES[g.pr_key]?.closes,
        };
      }
    }
  }

  return { repo, owner, name, issues, prs };
}

export function titleForIssue(catalog: KeyCatalog, key?: string, fallback?: string): string {
  if (key && catalog.issues[key]?.title) return catalog.issues[key].title;
  return fallback ?? "";
}

export { ISSUE_TITLES, PR_TITLES };
