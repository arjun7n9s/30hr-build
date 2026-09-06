import { usdChat, usdEmbed } from "./cost.js";
import { livePartnerKey } from "./offline.js";

export const OPENAI_URL = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
export const OPENAI_CHAT = process.env.OPENAI_ESCALATE_MODEL || "gpt-5-nano";
export const OPENAI_EMBED = process.env.OPENAI_EMBEDDING_MODEL || "text-embedding-3-small";
export const OPENAI_EMBED_BACKUP = process.env.OPENAI_EMBEDDING_FALLBACK || "text-embedding-ada-002";

export function openaiKey(): string | undefined {
  return process.env.OPENAI_API_KEY || undefined;
}

/** Same OpenAI partner as embeddings. Chat use is gpt-5-nano after a logged gate miss. */
export async function openaiChat(
  messages: { role: "system" | "user"; content: string }[],
  opts: { fetchImpl?: typeof fetch; apiKey?: string } = {},
): Promise<
  | { text: string; prompt: number; completion: number; total: number; latency_ms: number; cost_usd: number; model: string }
  | { skipped: true; reason: string }
> {
  const key = livePartnerKey(opts.apiKey, openaiKey);
  if (!key) return { skipped: true, reason: "OPENAI_API_KEY missing" };
  const started = Date.now();
  const res = await (opts.fetchImpl ?? fetch)(`${OPENAI_URL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model: OPENAI_CHAT, messages, max_completion_tokens: 2048 }),
  });
  if (!res.ok) throw new Error(`OpenAI chat ${res.status}`);
  const body = (await res.json()) as {
    choices?: { message?: { content?: string } }[];
    usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
  };
  const prompt = body.usage?.prompt_tokens ?? 0;
  const completion = body.usage?.completion_tokens ?? 0;
  return {
    text: body.choices?.[0]?.message?.content ?? "",
    prompt,
    completion,
    total: body.usage?.total_tokens ?? prompt + completion,
    latency_ms: Date.now() - started,
    cost_usd: usdChat("openai", prompt, completion),
    model: OPENAI_CHAT,
  };
}

export async function openaiEmbed(
  input: string[],
  opts: { fetchImpl?: typeof fetch; apiKey?: string } = {},
): Promise<{ vectors: number[][]; model: string; tokens: number; cost_usd: number } | { skipped: true; reason: string }> {
  const key = livePartnerKey(opts.apiKey, openaiKey);
  if (!key) return { skipped: true, reason: "OPENAI_API_KEY missing" };
  for (const model of [OPENAI_EMBED, OPENAI_EMBED_BACKUP]) {
    const res = await (opts.fetchImpl ?? fetch)(`${OPENAI_URL}/embeddings`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ model, input }),
    });
    if (!res.ok) continue;
    const body = (await res.json()) as {
      data?: { embedding: number[] }[];
      usage?: { prompt_tokens?: number; total_tokens?: number };
    };
    const tokens = body.usage?.total_tokens ?? body.usage?.prompt_tokens ?? 0;
    return {
      vectors: (body.data ?? []).map((d) => d.embedding),
      model,
      tokens,
      cost_usd: usdEmbed(tokens),
    };
  }
  throw new Error("OpenAI embeddings failed");
}
