import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT } from "../paths.js";

/** Load gitignored `.env` into process.env without printing values. */
export function loadDotenv(path = join(ROOT, ".env")): void {
  if (!existsSync(path)) return;
  for (const raw of readFileSync(path, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
    if (process.env[key]) continue;
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

export function partnerFlags(): { tensormux: boolean; neatlogs: boolean; openai: boolean } {
  return {
    tensormux: Boolean(process.env.TMX_API_KEY),
    neatlogs: Boolean(process.env.NEATLOGS_API_KEY || process.env.NEATLOGS_WRITE_KEY),
    openai: Boolean(process.env.OPENAI_API_KEY),
  };
}
