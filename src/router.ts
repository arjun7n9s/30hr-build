import type { EvalTask, PlaybookFacts } from "./types.js";

/** Stage 6 stub. Always the full actor path until polish. */
export function costRouter(task: EvalTask, facts: PlaybookFacts): { path: "full" | "cheap"; reason: string } {
  void task;
  void facts;
  return { path: "full", reason: "router stub — polish is stage 6" };
}
