import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { PolicyDoc, ToolCaller, TraceStep } from "./types.js";
import { contextGate } from "./gates.js";
import { checkTool, githubToken } from "./policy.js";
import { estimateTokens } from "./score.js";

export class PolicyDeniedError extends Error {
  constructor(public reason: string) {
    super(reason);
    this.name = "PolicyDeniedError";
  }
}

export class GithubMcp implements ToolCaller {
  private client: Client | null = null;
  private connecting: Promise<Client> | null = null;

  constructor(private policy: PolicyDoc) {}

  async call(name: string, args: Record<string, unknown>): Promise<unknown> {
    const gated = contextGate(name, args);
    if (!gated.ok) throw new PolicyDeniedError(gated.reason);
    const gate = checkTool(this.policy, name, args);
    if (!gate.ok) throw new PolicyDeniedError(gate.reason);
    const client = await this.connect();
    const result = await client.callTool({ name, arguments: args });
    return result;
  }

  async close(): Promise<void> {
    if (this.client) {
      await this.client.close().catch(() => undefined);
      this.client = null;
    }
    this.connecting = null;
  }

  private async connect(): Promise<Client> {
    if (this.client) return this.client;
    if (this.connecting) return this.connecting;
    this.connecting = this.open();
    try {
      this.client = await this.connecting;
      return this.client;
    } finally {
      this.connecting = null;
    }
  }

  private async open(): Promise<Client> {
    const token = githubToken();
    if (!token) {
      throw new Error("GITHUB_TOKEN or GH_TOKEN is required to call GitHub MCP");
    }
    const url = this.policy.mcp.url;
    const toolsets = this.policy.mcp.toolsets?.join(",") ?? "context,repos,issues,labels,pull_requests";
    const transport = new StreamableHTTPClientTransport(new URL(url), {
      requestInit: {
        headers: {
          Authorization: `Bearer ${token}`,
          "X-MCP-Toolsets": toolsets,
        },
      },
    });
    const client = new Client({ name: "journeyman", version: "1.0.0" });
    await client.connect(transport);
    return client;
  }
}

export class TracingCaller implements ToolCaller {
  readonly steps: TraceStep[] = [];
  errors = 0;
  retries = 0;

  constructor(private inner: ToolCaller) {}

  async call(name: string, args: Record<string, unknown>): Promise<unknown> {
    const started = Date.now();
    try {
      const result = await this.inner.call(name, args);
      this.steps.push({
        tool: name,
        args,
        result: clip(result),
        latency_ms: Date.now() - started,
        tokens: estimateTokens({ args, result }),
      });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const denied = err instanceof PolicyDeniedError;
      if (!denied) this.errors += 1;
      this.steps.push({
        tool: name,
        args,
        error: message,
        denied,
        latency_ms: Date.now() - started,
        tokens: estimateTokens({ args, error: message }),
      });
      throw err;
    }
  }
}

function clip(value: unknown): unknown {
  const raw = JSON.stringify(value);
  if (raw && raw.length > 8000) {
    return { clipped: true, preview: raw.slice(0, 8000) };
  }
  return value;
}

export function textFromMcp(result: unknown): string {
  if (result == null) return "";
  if (typeof result === "string") return result;
  if (typeof result === "object" && result && "content" in result) {
    const content = (result as { content?: unknown }).content;
    if (Array.isArray(content)) {
      return content
        .map((part) => {
          if (typeof part === "string") return part;
          if (part && typeof part === "object" && "text" in part) {
            return String((part as { text: unknown }).text);
          }
          return JSON.stringify(part);
        })
        .join("\n");
    }
  }
  return JSON.stringify(result);
}

export function jsonFromMcp<T = unknown>(result: unknown): T | null {
  const text = textFromMcp(result);
  try {
    return JSON.parse(text) as T;
  } catch {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(text.slice(start, end + 1)) as T;
      } catch {
        return null;
      }
    }
    const a0 = text.indexOf("[");
    const a1 = text.lastIndexOf("]");
    if (a0 >= 0 && a1 > a0) {
      try {
        return JSON.parse(text.slice(a0, a1 + 1)) as T;
      } catch {
        return null;
      }
    }
    return null;
  }
}
