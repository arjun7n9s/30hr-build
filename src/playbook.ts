import type { PlaybookFacts } from "./types.js";

const EMPTY_RULES = {
  stack_trace_bug: false,
  crash_nil_oom_p0: false,
  path_area: false,
  docs_typo_readme: false,
  feat_from_ask: false,
};

export function emptyFacts(version = 0, markdown = ""): PlaybookFacts {
  return {
    version,
    empty: true,
    labels: [],
    owners: {},
    search_before_list: false,
    rules: { ...EMPTY_RULES },
    markdown,
  };
}

export function parsePlaybook(markdown: string, version: number): PlaybookFacts {
  const text = markdown ?? "";
  if (!text.trim() || /Empty\. No repo facts/i.test(text) || /^# Playbook v0\b/m.test(text) && !/## Labels/i.test(text)) {
    const facts = emptyFacts(version, text);
    facts.search_before_list = /search before list/i.test(text);
    return facts;
  }

  const labels = [...text.matchAll(/^\s*-\s*((?:type|area|priority):[a-z0-9]+)/gim)].map((m) => m[1]);
  const owners: Record<string, string> = {};
  for (const m of text.matchAll(/src\/(billing|runtime|api|ui)\s*→\s*(\w+)/gi)) {
    owners[`src/${m[1]}`] = m[2].toLowerCase();
  }
  const repo = text.match(/repo:\s*(\S+)/i)?.[1];

  return {
    version,
    empty: labels.length === 0 && Object.keys(owners).length === 0 && !/stack trace/i.test(text),
    repo,
    labels: [...new Set(labels)],
    owners,
    search_before_list: /search before list/i.test(text),
    rules: {
      stack_trace_bug: /stack trace\s*→\s*`?type:bug`?/i.test(text),
      crash_nil_oom_p0: /crash\/nil\/oom\s*→\s*`?priority:p0`?/i.test(text),
      path_area: /src\/billing\|runtime\|api\|ui/i.test(text) || /path.*area:\*/i.test(text),
      docs_typo_readme: /docs\/typo\/readme\s*→\s*`?type:docs`?/i.test(text),
      feat_from_ask: /feature ask|type:feat/i.test(text),
    },
    markdown: text,
  };
}

export function renderPlaybook(input: {
  version: number;
  repo?: string;
  labels: string[];
  owners: Record<string, string>;
  contributing?: string;
  grounded: boolean;
  notes: string[];
}): string {
  const ownerLines = Object.entries(input.owners)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([path, owner]) => `- ${path} → ${owner}`);
  const labelLines = [...new Set(input.labels)].sort().map((l) => `- ${l}`);
  const rules = input.grounded
    ? [
        "## Label rules",
        "- stack trace → `type:bug`",
        "- crash/nil/OOM → `priority:p0`",
        "- path `src/billing|runtime|api|ui` → matching `area:*`",
        "- docs/typo/README → `type:docs`",
        "- billing/invoice feature ask → `type:feat` + `area:billing`",
        "- UI feature / settings / toggle → `type:feat` + `area:ui`",
        "",
      ]
    : ["## Label rules", "- (not grounded yet — CONTRIBUTING.md not fetched)", ""];
  return [
    `# Playbook v${input.version}`,
    "",
    `repo: ${input.repo ?? "arjun7n9s/journeyman-fixture"}`,
    "",
    "## Labels",
    ...(labelLines.length ? labelLines : ["- (none observed)"]),
    "",
    ...rules,
    "## Owners",
    ...(ownerLines.length ? ownerLines : ["- (none observed)"]),
    "",
    "## Tool strategy",
    "- search before list-all",
    "- fetch CONTRIBUTING.md and CODEOWNERS once, then apply facts",
    "- `issue_read` when the number is known; otherwise `search_issues` by title",
    "",
    "## Notes",
    ...input.notes.map((n) => `- ${n}`),
    "",
    input.contributing ? `## CONTRIBUTING excerpt\n\n${input.contributing.slice(0, 2000)}\n` : "",
  ].join("\n");
}
