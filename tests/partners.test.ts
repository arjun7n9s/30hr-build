import { describe, expect, it } from "vitest";
import { actorGate, complete, extractJson, patchGate, reflectGate } from "../src/partners/brain.js";
import { listNeatlogs } from "../src/partners/neatlogs.js";
import { writeTrace } from "../src/partners/sink.js";
import { retrievePlaybook } from "../src/partners/rag.js";
import { emptyFacts, parsePlaybook } from "../src/playbook.js";
import { getTrace } from "../src/store.js";

function chatResponse(content: string, urlHint?: string) {
  return {
    ok: true,
    json: async () => ({
      choices: [{ message: { content } }],
      usage: { prompt_tokens: 11, completion_tokens: 7, total_tokens: 18 },
      urlHint,
    }),
  } as Response;
}

describe("partner brain", () => {
  it("uses TensorMux and does not escalate when the gate passes", async () => {
    const urls: string[] = [];
    const result = await complete({
      role: "actor",
      run_id: "run-ok",
      family_id: "fam-ok",
      prompt: "label this",
      tmxKey: "tmx_test",
      openaiKey: "sk-test",
      gate: (text) => actorGate(text, "label"),
      fetchImpl: async (input) => {
        urls.push(String(input));
        return chatResponse('{"labels":["type:bug","area:api"]}');
      },
    });
    expect(result.provider).toBe("tensormux");
    expect(result.escalated).toBe(false);
    expect(result.gate_miss).toBe(false);
    expect(urls.some((u) => u.includes("tensormux.com"))).toBe(true);
    expect(urls.some((u) => u.includes("openai.com"))).toBe(false);
  });

  it("same node calls OpenAI gpt-5-nano after a logged gate miss", async () => {
    const urls: string[] = [];
    const result = await complete({
      role: "reflect",
      run_id: "run-miss",
      family_id: "fam-miss",
      prompt: "reflect",
      tmxKey: "tmx_test",
      openaiKey: "sk-test",
      gate: reflectGate,
      fetchImpl: async (input) => {
        const url = String(input);
        urls.push(url);
        if (url.includes("tensormux.com")) return chatResponse("nope");
        return chatResponse("- search before list-all\n- merge CONTRIBUTING path rules");
      },
    });
    expect(result.escalated).toBe(true);
    expect(result.gate_miss).toBe(true);
    expect(result.escalate_reason).toBe("reflect_unparseable_playbook_diff");
    expect(result.spans.some((s) => s.kind === "GUARDRAIL" && s.gate_miss)).toBe(true);
    expect(result.spans.some((s) => s.name === "openai" && s.provider === "openai")).toBe(true);
    expect(result.spans.some((s) => s.name === "openai-nano" || s.provider === "nano")).toBe(false);
    expect(urls.findIndex((u) => u.includes("tensormux.com"))).toBeLessThan(
      urls.findIndex((u) => u.includes("openai.com")),
    );
  });

  it("does not call OpenAI when TensorMux is skipped", async () => {
    const urls: string[] = [];
    const result = await complete({
      role: "patch",
      run_id: "run-skip",
      family_id: "fam-skip",
      prompt: "patch",
      openaiKey: "sk-test",
      gate: patchGate,
      fetchImpl: async (input) => {
        urls.push(String(input));
        return chatResponse("should not run");
      },
    });
    expect(result.skipped).toBe(true);
    expect(result.escalated).toBe(false);
    expect(urls).toEqual([]);
  });

  it("does not escalate on TensorMux transport failure", async () => {
    const urls: string[] = [];
    const result = await complete({
      role: "actor",
      run_id: "run-500",
      family_id: "fam-500",
      prompt: "label",
      tmxKey: "tmx_test",
      openaiKey: "sk-test",
      gate: (text) => actorGate(text, "label"),
      fetchImpl: async (input) => {
        urls.push(String(input));
        return { ok: false, status: 500, json: async () => ({}) } as Response;
      },
    });
    expect(result.transport_error).toBe(true);
    expect(result.escalated).toBe(false);
    expect(urls.some((u) => u.includes("openai.com"))).toBe(false);
  });
});

describe("playbook RAG", () => {
  const facts = parsePlaybook(
    [
      "# Playbook v1",
      "## Labels",
      "- type:bug",
      "## Label rules",
      "- stack trace → `type:bug`",
      "## Owners",
      "- src/api → api",
    ].join("\n"),
    1,
  );

  it("falls back to keywords without OpenAI", async () => {
    const rag = await retrievePlaybook({
      query: "who owns src/api stack traces",
      facts,
      run_id: "run-rag",
      family_id: "fam-rag",
    });
    expect(rag.hits.length).toBeGreaterThan(0);
    expect(rag.spans.some((s) => s.kind === "RETRIEVER")).toBe(true);
    expect(rag.spans.some((s) => s.kind === "EMBEDDING")).toBe(false);
  });

  it("ranks with embeddings when a key is injected", async () => {
    const rag = await retrievePlaybook({
      query: "owners",
      facts,
      run_id: "run-emb",
      family_id: "fam-emb",
      openaiKey: "sk-test",
      fetchImpl: async () =>
        ({
          ok: true,
          json: async () => ({
            data: [
              { embedding: [1, 0, 0] },
              { embedding: [0.1, 1, 0] },
              { embedding: [0.1, 0.2, 1] },
              { embedding: [1, 0.1, 0] },
            ],
            usage: { total_tokens: 12 },
          }),
        }) as Response,
    });
    expect(rag.spans.some((s) => s.kind === "EMBEDDING")).toBe(true);
    expect(rag.hits.length).toBeGreaterThan(0);
  });

  it("returns nothing on an empty playbook", async () => {
    const rag = await retrievePlaybook({
      query: "labels",
      facts: emptyFacts(0),
      run_id: "run-empty",
      family_id: "fam-empty",
    });
    expect(rag.excerpt).toBe("");
  });
});

describe("neatlogs family", () => {
  it("publishes Neatlogs from traces on the universal path", () => {
    const actor = writeTrace({
      id: "trace-a",
      run_id: "run-a",
      family_id: "fam-sink",
      task_id: "dev-01",
      playbook_version: 0,
      split: "dev",
      role: "actor",
      steps: [],
      answer: {},
      cost: { tool_calls: 1, tokens: 4 },
      speed_ms: 4,
      spans: [
        {
          name: "list_issues",
          kind: "MCP_TOOL",
          role: "actor",
          run_id: "run-a",
          family_id: "fam-sink",
          duration_ms: 4,
          status: "OK",
        },
      ],
    });
    writeTrace({
      id: "trace-p",
      run_id: "run-a",
      family_id: "fam-sink",
      task_id: "patch",
      playbook_version: 0,
      split: "dev",
      role: "patch",
      steps: [],
      answer: {},
      cost: { tool_calls: 0, tokens: 8 },
      speed_ms: 8,
      spans: [
        {
          name: "tensormux",
          kind: "LLM",
          role: "patch",
          run_id: "run-a",
          family_id: "fam-sink",
          duration_ms: 8,
          status: "OK",
        },
      ],
    });
    expect(getTrace(actor.id)?.family_id).toBe("fam-sink");
    const family = listNeatlogs({ familyId: "fam-sink" });
    expect(family.map((r) => r.role).sort()).toEqual(["actor", "patch"]);
    expect(family.every((r) => r.family_id === "fam-sink")).toBe(true);
  });
});

describe("gates", () => {
  it("parses actor JSON and rejects garbage", () => {
    expect(extractJson('here {"labels":["type:bug"]}')).toEqual({ labels: ["type:bug"] });
    expect(actorGate("not json", "label").ok).toBe(false);
    expect(patchGate("short").ok).toBe(false);
    expect(patchGate("label miss: search before list-all").ok).toBe(true);
  });
});
