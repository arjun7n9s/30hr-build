/** Placeholder hosted Shared rates (per 1M tokens). Replace from the dashboard when billed. */
const RATES = {
  tmx_in: 0.06,
  tmx_out: 0.4,
  nano_in: 0.05,
  nano_out: 0.4,
  embed: 0.02,
};

export function usdChat(provider: "tensormux" | "openai", prompt: number, completion: number): number {
  const inn = provider === "tensormux" ? RATES.tmx_in : RATES.nano_in;
  const out = provider === "tensormux" ? RATES.tmx_out : RATES.nano_out;
  return (prompt * inn + completion * out) / 1_000_000;
}

export function usdEmbed(tokens: number): number {
  return (tokens * RATES.embed) / 1_000_000;
}
