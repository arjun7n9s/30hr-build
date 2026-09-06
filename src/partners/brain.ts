import type { PartnerCall, PartnerRole, TaskType, TraceSpan } from "../types.js";
import { openaiChat } from "./openai.js";
import { tensormuxChat } from "./tensormux.js";

export type BrainResult = {
  text: string;
  skipped: boolean;
  transport_error: boolean;
  escalated: boolean;
  gate_miss: boolean;
  escalate_reason?: string;
  provider: "tensormux" | "openai" | null;
  model?: string;
  tokens: number;
  dollars: number;
  latency_ms: number;
  calls: PartnerCall[];
  spans: TraceSpan[];
};

export type QualityGate = {
  ok: boolean;
  reason: string;
};

export function actorGate(text: string, type: TaskType): QualityGate {
  const parsed = extractJson(text);
  if (!parsed) return { ok: false, reason: "actor_invalid_json" };
  if (type === "label" && Array.isArray(parsed.labels)) return { ok: true, reason: "ok" };
  if (type === "duplicate" && parsed.duplicate_of != null) return { ok: true, reason: "ok" };
  if (type === "owner" && typeof parsed.owner === "string" && parsed.owner.trim()) return { ok: true, reason: "ok" };
  if (type === "summarize" && (Array.isArray(parsed.keys) || typeof parsed.text === "string")) {
    return { ok: true, reason: "ok" };
  }
  if (type === "fix_pr" && parsed.pr != null) return { ok: true, reason: "ok" };
  return { ok: false, reason: "actor_invalid_json" };
}

export function reflectGate(text: string): QualityGate {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.replace(/^[-*]\s*/, "").trim())
    .filter((l) => l.length > 8);
  if (lines.length >= 1 && /search|playbook|contributing|codeowners|label|owner|issue/i.test(text)) {
    return { ok: true, reason: "ok" };
  }
  return { ok: false, reason: "reflect_unparseable_playbook_diff" };
}

export function patchGate(text: string): QualityGate {
  if (text.trim().length >= 20 && /miss|search|label|owner|duplicate|playbook|patch/i.test(text)) {
    return { ok: true, reason: "ok" };
  }
  return { ok: false, reason: "patch_empty_candidate" };
}

export function extractJson(text: string): Record<string, unknown> | null {
  const trimmed = text.trim();
  const tryParse = (raw: string): Record<string, unknown> | null => {
    try {
      const value = JSON.parse(raw);
      return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  };
  const direct = tryParse(trimmed);
  if (direct) return direct;
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start >= 0 && end > start) return tryParse(trimmed.slice(start, end + 1));
  return null;
}

export async function complete(opts: {
  role: PartnerRole;
  prompt: string;
  system?: string;
  gate: (text: string) => QualityGate;
  run_id: string;
  family_id: string;
  version?: number;
  task_id?: string;
  fetchImpl?: typeof fetch;
  tmxKey?: string;
  openaiKey?: string;
}): Promise<BrainResult> {
  const messages: { role: "system" | "user"; content: string }[] = [];
  if (opts.system) messages.push({ role: "system", content: opts.system });
  messages.push({ role: "user", content: opts.prompt });

  const empty: BrainResult = {
    text: "",
    skipped: true,
    transport_error: false,
    escalated: false,
    gate_miss: false,
    provider: null,
    tokens: 0,
    dollars: 0,
    latency_ms: 0,
    calls: [],
    spans: [],
  };

  let tmx;
  try {
    tmx = await tensormuxChat(messages, { fetchImpl: opts.fetchImpl, apiKey: opts.tmxKey });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ...empty,
      skipped: false,
      transport_error: true,
      spans: [
        llmSpan({
          name: "tensormux",
          role: opts.role,
          run_id: opts.run_id,
          family_id: opts.family_id,
          version: opts.version,
          task_id: opts.task_id,
          provider: "tensormux",
          model: "glm-4-7-flash",
          status: "ERROR",
          error: message,
          duration_ms: 0,
        }),
      ],
    };
  }

  if ("skipped" in tmx) {
    return empty;
  }

  const firstGate = opts.gate(tmx.text);
  const firstCall: PartnerCall = {
    provider: "tensormux",
    model: tmx.model,
    role: opts.role,
    tokens: tmx.usage.total,
    latency_ms: tmx.usage.latency_ms,
    cost_usd: tmx.usage.cost_usd,
    gate_miss: !firstGate.ok,
    escalated: false,
    escalate_reason: firstGate.ok ? undefined : firstGate.reason,
  };
  const spans: TraceSpan[] = [
    llmSpan({
      name: "tensormux",
      role: opts.role,
      run_id: opts.run_id,
      family_id: opts.family_id,
      version: opts.version,
      task_id: opts.task_id,
      provider: "tensormux",
      model: tmx.model,
      tokens: { prompt: tmx.usage.prompt, completion: tmx.usage.completion, total: tmx.usage.total },
      cost_usd: tmx.usage.cost_usd,
      duration_ms: tmx.usage.latency_ms,
      status: "OK",
      output: tmx.text.slice(0, 2000),
      gate_miss: !firstGate.ok,
    }),
  ];

  if (firstGate.ok) {
    return {
      text: tmx.text,
      skipped: false,
      transport_error: false,
      escalated: false,
      gate_miss: false,
      provider: "tensormux",
      model: tmx.model,
      tokens: tmx.usage.total,
      dollars: tmx.usage.cost_usd,
      latency_ms: tmx.usage.latency_ms,
      calls: [firstCall],
      spans,
    };
  }

  spans.push({
    name: "quality-gate",
    kind: "GUARDRAIL",
    role: opts.role,
    run_id: opts.run_id,
    family_id: opts.family_id,
    task_id: opts.task_id,
    version: opts.version,
    duration_ms: 0,
    status: "ERROR",
    gate_miss: true,
    error: firstGate.reason,
    output: {
      escalate_reason: firstGate.reason,
      from_provider: "tensormux",
      from_model: tmx.model,
      to_provider: "openai",
      to_model: "gpt-5-nano",
      role: opts.role,
    },
  });

  let oai;
  try {
    oai = await openaiChat(messages, { fetchImpl: opts.fetchImpl, apiKey: opts.openaiKey });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    spans.push(
      llmSpan({
        name: "openai",
        role: opts.role,
        run_id: opts.run_id,
        family_id: opts.family_id,
        version: opts.version,
        task_id: opts.task_id,
        provider: "openai",
        model: "gpt-5-nano",
        status: "ERROR",
        error: message,
        duration_ms: 0,
      }),
    );
    return {
      text: tmx.text,
      skipped: false,
      transport_error: false,
      escalated: false,
      gate_miss: true,
      escalate_reason: firstGate.reason,
      provider: "tensormux",
      model: tmx.model,
      tokens: tmx.usage.total,
      dollars: tmx.usage.cost_usd,
      latency_ms: tmx.usage.latency_ms,
      calls: [firstCall],
      spans,
    };
  }

  if ("skipped" in oai) {
    return {
      text: tmx.text,
      skipped: false,
      transport_error: false,
      escalated: false,
      gate_miss: true,
      escalate_reason: firstGate.reason,
      provider: "tensormux",
      model: tmx.model,
      tokens: tmx.usage.total,
      dollars: tmx.usage.cost_usd,
      latency_ms: tmx.usage.latency_ms,
      calls: [firstCall],
      spans,
    };
  }

  const second: PartnerCall = {
    provider: "openai",
    model: oai.model,
    role: opts.role,
    tokens: oai.total,
    latency_ms: oai.latency_ms,
    cost_usd: oai.cost_usd,
    gate_miss: true,
    escalated: true,
    escalate_reason: firstGate.reason,
  };
  spans.push(
    llmSpan({
      name: "openai",
      role: opts.role,
      run_id: opts.run_id,
      family_id: opts.family_id,
      version: opts.version,
      task_id: opts.task_id,
      provider: "openai",
      model: oai.model,
      tokens: { prompt: oai.prompt, completion: oai.completion, total: oai.total },
      cost_usd: oai.cost_usd,
      duration_ms: oai.latency_ms,
      status: "OK",
      output: oai.text.slice(0, 2000),
    }),
  );

  return {
    text: oai.text,
    skipped: false,
    transport_error: false,
    escalated: true,
    gate_miss: true,
    escalate_reason: firstGate.reason,
    provider: "openai",
    model: oai.model,
    tokens: tmx.usage.total + oai.total,
    dollars: tmx.usage.cost_usd + oai.cost_usd,
    latency_ms: tmx.usage.latency_ms + oai.latency_ms,
    calls: [firstCall, second],
    spans,
  };
}

function llmSpan(input: {
  name: string;
  role: PartnerRole;
  run_id: string;
  family_id: string;
  version?: number;
  task_id?: string;
  provider: "tensormux" | "openai";
  model: string;
  tokens?: { prompt?: number; completion?: number; total?: number };
  cost_usd?: number;
  duration_ms: number;
  status: "OK" | "ERROR";
  error?: string;
  output?: unknown;
  gate_miss?: boolean;
}): TraceSpan {
  return {
    name: input.name,
    kind: "LLM",
    role: input.role,
    run_id: input.run_id,
    family_id: input.family_id,
    task_id: input.task_id,
    version: input.version,
    provider: input.provider,
    model: input.model,
    tokens: input.tokens,
    cost_usd: input.cost_usd,
    duration_ms: input.duration_ms,
    status: input.status,
    error: input.error,
    output: input.output,
    gate_miss: input.gate_miss,
  };
}
