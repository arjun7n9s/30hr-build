import type { Report } from "./reportView";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");

function url(path: string): string {
  return `${API_BASE}${path}`;
}

export type ChallengeIn = {
  prompt: string;
  task_type?: string;
  target?: string;
  body?: string;
};

export type ChallengeResult = {
  session_id: string;
  playbook_version: string;
  mode: string;
  result: {
    prompt: string;
    task_type: string | null;
    answer: unknown;
    text: string;
    tokens: number;
    cost: number;
    speed_ms: number;
    tool_calls: number;
    playbook_hits: string[];
    rule_hits: { rule_id: string; why: string }[];
    escalated: boolean;
    model: string;
    spans: {
      name: string;
      kind: string;
      duration_ms: number;
      tokens: number;
      cost: number;
      model: string;
      route: string;
      input?: unknown;
      output?: unknown;
    }[];
  };
};

async function safeJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) msg = `${msg} — ${body.detail}`;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export async function loadReport(): Promise<{ report: Report; source: "api" | "local" | "snapshot" }> {
  try {
    const res = await fetch(url("/api/report"), { cache: "no-store" });
    if (res.ok) return { report: (await res.json()) as Report, source: "api" };
  } catch {
    /* fall through */
  }
  try {
    const res = await fetch("/last-report.json", { cache: "no-store" });
    if (res.ok) return { report: (await res.json()) as Report, source: "local" };
  } catch {
    /* fall through */
  }
  const res = await fetch("/demo-snapshot.json", { cache: "no-store" });
  if (!res.ok) throw new Error("no report available");
  return { report: (await res.json()) as Report, source: "snapshot" };
}

export async function postChallenge(body: ChallengeIn): Promise<ChallengeResult> {
  return safeJson(
    await fetch(url("/api/challenge"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function postRun(mode: "offline" | "live" = "offline"): Promise<Report> {
  return safeJson(
    await fetch(url("/api/run"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ challenge_id: "frozen", mode }),
    }),
  );
}

export async function postRollback(): Promise<{
  ok: boolean;
  pointer: { active: string; prior: string | null; candidate: string | null };
}> {
  return safeJson(await fetch(url("/api/rollback"), { method: "POST" }));
}

export async function health(): Promise<{ ok: boolean; service: string } | null> {
  try {
    const res = await fetch(url("/api/health"));
    if (!res.ok) return null;
    return (await res.json()) as { ok: boolean; service: string };
  } catch {
    return null;
  }
}
