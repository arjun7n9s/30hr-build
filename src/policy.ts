import { readFileSync } from "node:fs";
import { parse } from "yaml";
import type { PolicyDoc } from "./types.js";
import { POLICY_PATH } from "./paths.js";

const DENIED_SUBSTRINGS = [
  "write",
  "secret",
  "workflow",
  "deploy",
  "admin",
  "push",
  "force",
];

export function loadPolicy(path = POLICY_PATH): PolicyDoc {
  return parse(readFileSync(path, "utf8")) as PolicyDoc;
}

function globMatch(pattern: string, value: string): boolean {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, "\u0000")
    .replace(/\*/g, "[^/]*")
    .replace(/\u0000/g, ".*");
  return new RegExp(`^${escaped}$`, "i").test(value);
}

function nameDenied(policy: PolicyDoc, tool: string): boolean {
  const lower = tool.toLowerCase();
  if (policy.deny.tools.some((t) => t.toLowerCase() === lower)) return true;
  if (policy.deny.name_patterns.some((p) => globMatch(p, tool))) return true;
  if (DENIED_SUBSTRINGS.some((s) => lower.includes(s))) {
    if (!policy.allow.tools.some((t) => t.toLowerCase() === lower)) return true;
  }
  return false;
}

export function pathAllowed(policy: PolicyDoc, filePath: string | undefined): boolean {
  if (!filePath) return false;
  const normalized = filePath.replace(/\\/g, "/").replace(/^\.\//, "");
  return policy.allow.file_paths.some((rule) => {
    if (rule.endsWith("/**")) {
      const prefix = rule.slice(0, -3);
      return normalized === prefix || normalized.startsWith(`${prefix}/`);
    }
    return globMatch(rule, normalized) || normalized.toLowerCase() === rule.toLowerCase();
  });
}

export function checkTool(
  policy: PolicyDoc,
  tool: string,
  args: Record<string, unknown> = {},
): { ok: true } | { ok: false; reason: string } {
  if (nameDenied(policy, tool)) {
    return { ok: false, reason: `denied by policy: ${tool}` };
  }
  if (!policy.allow.tools.some((t) => t.toLowerCase() === tool.toLowerCase())) {
    return { ok: false, reason: `not on allowlist: ${tool}` };
  }
  if (tool === "get_file_contents" || tool === "get_repository_tree") {
    const filePath = typeof args.path === "string" ? args.path : "";
    if (tool === "get_file_contents" && !pathAllowed(policy, filePath)) {
      return { ok: false, reason: `file path not allowed: ${filePath || "(empty)"}` };
    }
    if (tool === "get_repository_tree" && filePath && !pathAllowed(policy, filePath)) {
      return { ok: false, reason: `tree path not allowed: ${filePath}` };
    }
  }
  return { ok: true };
}

export function githubToken(): string | undefined {
  return process.env.GITHUB_TOKEN || process.env.GH_TOKEN || undefined;
}
