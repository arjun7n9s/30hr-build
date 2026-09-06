import type { PlaybookFacts } from "../types.js";
import type { NeatSpan } from "./neatlogs.js";
import { openaiEmbed } from "./openai.js";

export type RagHit = {
  excerpt: string;
  hits: string[];
  spans: NeatSpan[];
  dollars: number;
  tokens: number;
};

const STOP = new Set(["the", "and", "for", "this", "that", "with", "from", "into", "your", "repo"]);

export async function retrievePlaybook(opts: {
  query: string;
  facts: PlaybookFacts;
  run_id: string;
  family_id: string;
  version?: number;
  fetchImpl?: typeof fetch;
  openaiKey?: string;
}): Promise<RagHit> {
  const chunks = chunkPlaybook(opts.facts.markdown || "");
  const started = Date.now();
  if (!chunks.length) {
    return { excerpt: "", hits: [], spans: [], dollars: 0, tokens: 0 };
  }

  const embedded = await openaiEmbed([opts.query, ...chunks.map((c) => c.text)], {
    fetchImpl: opts.fetchImpl,
    apiKey: opts.openaiKey,
  }).catch(() => ({ skipped: true as const, reason: "embed failed" }));

  let ranked = keywordRank(opts.query, chunks);
  let dollars = 0;
  let tokens = 0;
  const spans: NeatSpan[] = [];

  if (!("skipped" in embedded)) {
    const [qVec, ...cVecs] = embedded.vectors;
    if (qVec && cVecs.length === chunks.length) {
      ranked = chunks
        .map((chunk, i) => ({ chunk, score: cosine(qVec, cVecs[i] ?? []) }))
        .sort((a, b) => b.score - a.score)
        .map((row) => row.chunk);
    }
    dollars = embedded.cost_usd;
    tokens = embedded.tokens;
    spans.push({
      name: "playbook-embed",
      kind: "EMBEDDING",
      role: "actor",
      run_id: opts.run_id,
      family_id: opts.family_id,
      version: opts.version,
      provider: "openai",
      model: embedded.model,
      tokens: { prompt: embedded.tokens, total: embedded.tokens },
      cost_usd: embedded.cost_usd,
      duration_ms: Date.now() - started,
      status: "OK",
    });
  }

  const top = ranked.slice(0, 3);
  const hits = top.map((c) => c.heading);
  const excerpt = top.map((c) => c.text).join("\n\n").slice(0, 2400);
  spans.push({
    name: "playbook-rag",
    kind: "RETRIEVER",
    role: "actor",
    run_id: opts.run_id,
    family_id: opts.family_id,
    version: opts.version,
    duration_ms: Date.now() - started,
    status: "OK",
    playbook_hits: hits,
    output: excerpt.slice(0, 800),
  });
  return { excerpt, hits, spans, dollars, tokens };
}

export function chunkPlaybook(markdown: string): { heading: string; text: string }[] {
  const parts = markdown.split(/^## /m).map((block, i) => {
    const lines = block.trim();
    if (!lines) return null;
    const [first, ...rest] = lines.split(/\r?\n/);
    const heading = i === 0 ? "playbook" : (first ?? "section").trim();
    const text = i === 0 ? lines : `${heading}\n${rest.join("\n")}`;
    return { heading: heading.slice(0, 80), text: text.slice(0, 1200) };
  });
  return parts.filter((p): p is { heading: string; text: string } => Boolean(p));
}

function keywordRank(query: string, chunks: { heading: string; text: string }[]): { heading: string; text: string }[] {
  const q = tokens(query);
  return [...chunks].sort((a, b) => score(q, b.text) - score(q, a.text));
}

function score(query: Set<string>, text: string): number {
  const hay = tokens(text);
  let n = 0;
  for (const t of query) if (hay.has(t)) n += 1;
  return n;
}

function tokens(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9:]+/)
      .filter((t) => t.length > 2 && !STOP.has(t)),
  );
}

function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (!na || !nb) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}
