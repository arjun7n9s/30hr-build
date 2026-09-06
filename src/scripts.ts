import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { SCRIPTS_PATH, ensureDataDirs } from "./paths.js";
import type { ScriptEntry } from "./types.js";

export function readScripts(): ScriptEntry[] {
  ensureDataDirs();
  if (!existsSync(SCRIPTS_PATH)) {
    writeFileSync(SCRIPTS_PATH, "[]\n");
    return [];
  }
  return JSON.parse(readFileSync(SCRIPTS_PATH, "utf8")) as ScriptEntry[];
}

export function writeScripts(scripts: ScriptEntry[]): void {
  ensureDataDirs();
  writeFileSync(SCRIPTS_PATH, `${JSON.stringify(scripts, null, 2)}\n`);
}
