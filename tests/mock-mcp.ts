import type { ToolCaller } from "../src/types.js";

const ISSUES = [
  { key: "I1", number: 1, title: "API returns 500 on empty payload", body: "stack trace\n  File src/api/routes.py line 12", labels: ["type:bug", "area:api"] },
  { key: "I2", number: 2, title: "Add invoice PDF export", body: "billing/invoice feature ask", labels: ["type:feat", "area:billing"] },
  { key: "I3", number: 3, title: "README typo in install section", body: "docs/typo in README", labels: ["type:docs"] },
  { key: "I4", number: 4, title: "Runtime worker leaks memory after 2h", body: "stack in src/runtime/worker.py", labels: ["type:bug", "area:runtime"] },
  { key: "I5", number: 5, title: "Crash loop on nil context", body: "crash + nil + src/runtime/worker.py", labels: ["type:bug", "area:runtime", "priority:p0"] },
  { key: "I6", number: 6, title: "Dark mode toggle", body: "UI feature", labels: ["type:feat", "area:ui"] },
  { key: "I7", number: 7, title: "Charge webhook retries twice", body: "src/billing/charge.py", labels: ["type:bug", "area:billing"] },
  { key: "I8", number: 8, title: "Document env vars", body: "docs", labels: ["type:docs"] },
  { key: "I9", number: 9, title: "API returns 500 when body is empty", body: "same bug as empty payload, src/api/routes.py", labels: ["type:bug", "area:api"] },
  { key: "I10", number: 10, title: "Worker OOM after long run", body: "same as leak, src/runtime/worker.py", labels: ["type:bug", "area:runtime"] },
  { key: "I11", number: 11, title: "OpenAPI spec missing 400 examples", body: "docs + api", labels: ["type:docs", "area:api"] },
  { key: "I12", number: 12, title: "Billing cron double-charges on retry", body: "src/billing/charge.py crash", labels: ["type:bug", "area:billing", "priority:p0"] },
  { key: "I13", number: 13, title: "Add CSV export for invoices", body: "billing/invoice feature ask", labels: ["type:feat", "area:billing"] },
  { key: "I14", number: 14, title: "Panic in worker when ctx canceled", body: "crash + nil + src/runtime/worker.py", labels: ["type:bug", "area:runtime", "priority:p0"] },
  { key: "I15", number: 15, title: "Fix typo in contributing guide", body: "docs typo CONTRIBUTING", labels: ["type:docs"] },
  { key: "I16", number: 16, title: "UI button misaligned on settings", body: "ui bug src/ui/app.tsx", labels: ["type:bug", "area:ui"] },
  { key: "I17", number: 17, title: "REST handler 500 on null JSON", body: "stack trace src/api/routes.py", labels: ["type:bug", "area:api"] },
  { key: "I18", number: 18, title: "Rate limit headers not documented", body: "docs+api", labels: ["type:docs", "area:api"] },
];

const PRS = [
  { key: "P1", number: 1, title: "Fix empty payload 500 in API", body: "Closes #1", files: ["src/api/routes.py"] },
  { key: "P2", number: 2, title: "Cap runtime worker memory", body: "Closes #4", files: ["src/runtime/worker.py"] },
  { key: "P3", number: 3, title: "Idempotent billing webhook", body: "Closes #7", files: ["src/billing/charge.py"] },
  { key: "P4", number: 4, title: "Settings page layout", body: "", files: ["src/ui/app.tsx"] },
];

const FILES: Record<string, string> = {
  "CONTRIBUTING.md": [
    "Label rules:",
    "stack trace → type:bug",
    "crash/nil/OOM → priority:p0",
    "path src/billing|runtime|api|ui → matching area:*",
    "docs/typo/README → type:docs",
  ].join("\n"),
  CODEOWNERS: [
    "/src/billing/ @arjun7n9s",
    "/src/runtime/ @arjun7n9s",
    "/src/api/ @arjun7n9s",
    "/src/ui/ @arjun7n9s",
  ].join("\n"),
};

const LABELS = [
  "type:bug",
  "type:feat",
  "type:docs",
  "area:api",
  "area:runtime",
  "area:billing",
  "area:ui",
  "priority:p0",
  "priority:p1",
];

function wrap(data: unknown) {
  return { content: [{ type: "text", text: JSON.stringify(data) }] };
}

export function mockGithub(): ToolCaller & { calls: { name: string; args: Record<string, unknown> }[] } {
  const calls: { name: string; args: Record<string, unknown> }[] = [];
  return {
    calls,
    async call(name, args) {
      calls.push({ name, args });
      if (name === "list_issues") {
        return wrap(ISSUES.map((i) => ({ number: i.number, title: i.title, body: i.body, labels: i.labels })));
      }
      if (name === "search_issues") {
        const q = String(args.query ?? "").toLowerCase();
        const words = q.split(/[^a-z0-9:]+/).filter((w) => w.length > 2);
        const hits = ISSUES.filter((i) => {
          const blob = `${i.title} ${i.body} ${i.labels.join(" ")}`.toLowerCase();
          return words.some((w) => blob.includes(w) || blob.includes(w.replace("type:", "").replace("area:", "")));
        });
        return wrap({ items: hits.map((i) => ({ number: i.number, title: i.title, body: i.body, labels: i.labels })) });
      }
      if (name === "issue_read") {
        const n = Number(args.issue_number);
        const hit = ISSUES.find((i) => i.number === n);
        return wrap(hit ?? {});
      }
      if (name === "list_pull_requests") {
        return wrap(PRS.map((p) => ({ number: p.number, title: p.title, body: p.body })));
      }
      if (name === "search_pull_requests") {
        const q = String(args.query ?? "").toLowerCase();
        const hits = PRS.filter((p) => `${p.title} ${p.body}`.toLowerCase().includes(q) || q.split(/\s+/).some((w) => w && p.title.toLowerCase().includes(w)));
        return wrap({ items: hits.map((p) => ({ number: p.number, title: p.title, body: p.body })) });
      }
      if (name === "get_file_contents") {
        const path = String(args.path);
        const text = FILES[path];
        if (!text) throw new Error(`missing ${path}`);
        return wrap({ content: Buffer.from(text).toString("base64") });
      }
      if (name === "list_label") {
        return wrap(LABELS.map((name) => ({ name })));
      }
      if (name === "search_repositories") {
        return wrap({ items: [{ full_name: "arjun7n9s/journeyman-fixture" }] });
      }
      throw new Error(`unexpected tool ${name}`);
    },
  };
}

export { ISSUES, PRS, FILES };
