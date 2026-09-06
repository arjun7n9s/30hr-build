import type { PartnerRole, Trace, TraceSpan } from "../types.js";
import { recordSpans } from "./neatlogs.js";
import { saveTrace } from "../store.js";

/** Universal path: node → Traces → Neatlogs. Never publish partners around the trace. */
export function writeTrace(trace: Trace, spans: TraceSpan[] = trace.spans ?? []): Trace {
  const role: PartnerRole = trace.role ?? "actor";
  const next = { ...trace, role, spans };
  saveTrace(next);
  recordSpans({
    name: `${role} ${next.task_id}`,
    run_id: next.run_id,
    family_id: next.family_id,
    role,
    version: next.playbook_version,
    task_id: next.task_id,
    spans,
  });
  return next;
}
