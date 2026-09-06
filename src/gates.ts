/** Stage 6 stub. Pass through; Policy YAML remains the real gate. */
export function contextGate(
  tool: string,
  args: Record<string, unknown>,
): { ok: true; reason: string } | { ok: false; reason: string } {
  void args;
  return { ok: true, reason: `gates stub pass for ${tool}` };
}
