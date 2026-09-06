export type TaskType = "label" | "duplicate" | "owner" | "summarize" | "fix_pr";
export type Split = "dev" | "holdout" | "challenge";

export type GithubRef = {
  issue_key?: string;
  issue_number?: number;
  issue_title?: string;
  pr_key?: string;
  pr_number?: number;
  path?: string;
  labels?: string[];
  state?: string;
};

export type Expected = {
  labels?: string[];
  duplicate_of?: string | number;
  owner?: string;
  keys?: string[];
  pr?: string | number;
};

export type EvalTask = {
  id: string;
  type: TaskType;
  prompt: string;
  github: GithubRef;
  expected?: Expected;
  score?: { accuracy?: string };
};

export type EvalFile = {
  split: Split;
  repo: string;
  sealed?: boolean;
  tasks: EvalTask[];
};

export type ActorAnswer = {
  labels?: string[];
  duplicate_of?: string | number;
  owner?: string;
  keys?: string[];
  pr?: string | number;
  text?: string;
};

export type TraceStep = {
  tool: string;
  args: Record<string, unknown>;
  result?: unknown;
  error?: string;
  denied?: boolean;
  latency_ms: number;
  tokens: number;
};

export type PartnerRole = "actor" | "reflect" | "patch" | "eval" | "redteam";

export type PartnerCall = {
  provider: "tensormux" | "openai";
  model: string;
  role: PartnerRole;
  tokens: number;
  latency_ms: number;
  cost_usd: number;
  gate_miss?: boolean;
  escalated?: boolean;
  escalate_reason?: string;
};

export type TraceSpan = {
  name: string;
  kind: "WORKFLOW" | "LLM" | "TOOL" | "MCP_TOOL" | "RETRIEVER" | "EMBEDDING" | "GUARDRAIL" | "EVALUATOR" | "AGENT";
  role: PartnerRole;
  run_id: string;
  family_id: string;
  task_id?: string;
  version?: number;
  tool_name?: string;
  model?: string;
  provider?: string;
  input?: unknown;
  output?: unknown;
  tokens?: { prompt?: number; completion?: number; total?: number };
  cost_usd?: number;
  duration_ms: number;
  status: "OK" | "ERROR";
  error?: string;
  playbook_hits?: string[];
  gate_miss?: boolean;
};

export type Trace = {
  id: string;
  run_id: string;
  family_id: string;
  task_id: string;
  playbook_version: number;
  split: Split;
  role?: PartnerRole;
  steps: TraceStep[];
  spans?: TraceSpan[];
  answer: ActorAnswer;
  cost: { tool_calls: number; tokens: number; dollars?: number };
  speed_ms: number;
  accuracy?: number;
  playbook_hits?: string[];
  partners?: PartnerCall[];
};

export type TaskResult = {
  task_id: string;
  type: TaskType;
  accuracy: number;
  cost: { tool_calls: number; tokens: number; dollars?: number };
  speed_ms: number;
  answer: ActorAnswer;
  expected?: Expected;
  trace_id: string;
};

export type RunRecord = {
  id: string;
  split: Split;
  playbook_version: number;
  created_at: string;
  accuracy: number;
  cost: { tool_calls: number; tokens: number; dollars?: number };
  speed_ms: number;
  reliability?: { errors: number; retries: number };
  tasks: TaskResult[];
  reflected_version?: number;
  holdout_allowed?: boolean;
  family_id?: string;
};

export type PlaybookFacts = {
  version: number;
  empty: boolean;
  repo?: string;
  labels: string[];
  owners: Record<string, string>;
  search_before_list: boolean;
  rules: {
    stack_trace_bug: boolean;
    crash_nil_oom_p0: boolean;
    path_area: boolean;
    docs_typo_readme: boolean;
    feat_from_ask: boolean;
  };
  markdown: string;
};

export type Budget = {
  max_cycles: number;
  used: number;
  last_dev_accuracy: number;
  exhausted: boolean;
};

export type AppState = {
  active_version: number;
  candidate_version: number | null;
  prior_version: number | null;
  budget: Budget;
  last_dev_run_id: string | null;
  last_holdout_run_id: string | null;
  last_family_id: string | null;
  last_rag_hits?: string[];
  last_patch?: { version: number; reason: string; improved: boolean } | null;
};

export type ScriptEntry = {
  id: string;
  name: string;
  when: string;
  body: string;
};

export type PolicyDoc = {
  mcp: { url: string; write_url?: string; toolsets?: string[] };
  allow: { tools: string[]; file_paths: string[] };
  deny: { tools: string[]; name_patterns: string[] };
};

export type KeyCatalog = {
  repo: string;
  owner: string;
  name: string;
  issues: Record<string, { number: number; title: string }>;
  prs: Record<string, { number: number; title: string; closes?: string }>;
};

export type ToolCaller = {
  call(name: string, args: Record<string, unknown>): Promise<unknown>;
};
