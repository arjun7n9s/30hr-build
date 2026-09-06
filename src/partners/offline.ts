/** Tests never hit partner HTTP, even if a key is in the shell. */
export function partnersOffline(): boolean {
  return process.env.VITEST === "true" || process.env.JOURNEYMAN_OFFLINE === "1";
}

export function livePartnerKey(explicit: string | undefined, fromEnv: () => string | undefined): string | undefined {
  if (explicit !== undefined) return explicit || undefined;
  if (partnersOffline()) return undefined;
  return fromEnv();
}
