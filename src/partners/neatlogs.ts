import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { PartnerRole, TraceSpan } from "../types.js";
import { DATA_DIR, ensureDataDirs } from "../paths.js";
import { partnersOffline } from "./offline.js";

export type { PartnerRole, TraceSpan };
export type NeatSpan = TraceSpan;

const DIR = () => join(DATA_DIR, "neatlogs");

export function neatKey(): string | undefined {
  return process.env.NEATLOGS_API_KEY || process.env.NEATLOGS_WRITE_KEY || undefined;
}

export type NeatRecord = {
  id: string;
  name: string;
  run_id: string;
  family_id: string;
  role: PartnerRole;
  version?: number;
  task_id?: string;
  created_at: string;
  spans: NeatSpan[];
};

export function recordSpans(opts: {
  name: string;
  run_id: string;
  family_id: string;
  role: PartnerRole;
  version?: number;
  task_id?: string;
  spans: NeatSpan[];
}): { id: string; remote: boolean } {
  ensureDataDirs();
  mkdirSync(DIR(), { recursive: true });
  const id = [opts.run_id, opts.role, opts.task_id ?? "run"].join("-");
  const record: NeatRecord = {
    id,
    name: opts.name,
    run_id: opts.run_id,
    family_id: opts.family_id,
    role: opts.role,
    version: opts.version,
    task_id: opts.task_id,
    created_at: new Date().toISOString(),
    spans: opts.spans,
  };
  writeFileSync(join(DIR(), `${id}.json`), JSON.stringify(record, null, 2));
  const key = neatKey();
  if (key && !partnersOffline()) {
    void exportRemote(record, key);
    return { id, remote: true };
  }
  return { id, remote: false };
}

export function listNeatlogs(opts?: { runId?: string; familyId?: string }): NeatRecord[] {
  ensureDataDirs();
  mkdirSync(DIR(), { recursive: true });
  return readdirSync(DIR())
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(readFileSync(join(DIR(), f), "utf8")) as NeatRecord)
    .filter((row) => (opts?.runId ? row.run_id === opts.runId : true))
    .filter((row) => (opts?.familyId ? row.family_id === opts.familyId : true))
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

async function exportRemote(record: NeatRecord, key: string): Promise<void> {
  try {
    await fetch("https://ingest.neatlogs.com/v1/trace", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: record.name,
        project: "journeyman",
        attributes: {
          "neatlogs.session.id": record.family_id,
        },
        children: record.spans.map((s) => ({
          name: s.name,
          kind: s.kind,
          tool_name: s.tool_name,
          model: s.model,
          input: s.input,
          output: s.output,
          tokens: s.tokens,
          duration_ms: s.duration_ms,
          status: s.status,
          error: s.error,
          passed: s.gate_miss === undefined ? undefined : !s.gate_miss,
          attributes: {
            "neatlogs.agent.role": s.role,
            "neatlogs.llm.provider": s.provider,
          },
          metadata: {
            run_id: s.run_id,
            version: s.version,
            playbook_hits: s.playbook_hits,
            cost_usd: s.cost_usd,
          },
        })),
      }),
    });
  } catch {
    // local SoR still holds the spans
  }
}

export function hasLocalStore(): boolean {
  return existsSync(DIR());
}
