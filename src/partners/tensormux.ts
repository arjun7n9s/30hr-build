import { usdChat } from "./cost.js";
import { livePartnerKey } from "./offline.js";

export const TMX_URL = process.env.TENSOR_MUX_BASE_URL || "https://api.tensormux.com/v1";
export const TMX_MODEL = process.env.TENSOR_MUX_MODEL || "glm-4-7-flash";

export function tmxKey(): string | undefined {
  return process.env.TMX_API_KEY || undefined;
}

export type ChatUsage = { prompt: number; completion: number; total: number; latency_ms: number; cost_usd: number };

export async function tensormuxChat(
  messages: { role: "system" | "user"; content: string }[],
  opts: { fetchImpl?: typeof fetch; apiKey?: string } = {},
): Promise<{ text: string; usage: ChatUsage; model: string } | { skipped: true; reason: string }> {
  const key = livePartnerKey(opts.apiKey, tmxKey);
  if (!key) return { skipped: true, reason: "TMX_API_KEY missing" };
  const started = Date.now();
  const res = await (opts.fetchImpl ?? fetch)(`${TMX_URL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model: TMX_MODEL, messages, temperature: 0 }),
  });
  if (!res.ok) {
    throw new Error(`TensorMux ${res.status}`);
  }
  const body = (await res.json()) as {
    choices?: { message?: { content?: string } }[];
    usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
  };
  const prompt = body.usage?.prompt_tokens ?? 0;
  const completion = body.usage?.completion_tokens ?? 0;
  const total = body.usage?.total_tokens ?? prompt + completion;
  return {
    text: body.choices?.[0]?.message?.content ?? "",
    model: TMX_MODEL,
    usage: {
      prompt,
      completion,
      total,
      latency_ms: Date.now() - started,
      cost_usd: usdChat("tensormux", prompt, completion),
    },
  };
}
