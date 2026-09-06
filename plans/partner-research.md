# Partner Stack Research & Integration Specification

**Product:** Journeyman (Automated Agent Engineering)  
**Status:** Research Locked / Pre-Implementation  
**Target File:** `plans/partner-research.md`  

---

## Executive Summary & Architecture Role Mapping

| Partner / Service | Role in Journeyman | Base URL | Model / Service | Env Var | Auth Prefix |
|---|---|---|---|---|---|
| **TensorMux** | Everyday Brain (Actor, Reflect, Patch) | `https://api.tensormux.com/v1` | `glm-4-7-flash` | `TMX_API_KEY` | `tmx_` |
| **Neatlogs** | Trace System of Record (SoR) & Cockpit | `https://api.neatlogs.com` | OpenTelemetry Tracer / Collector | `NEATLOGS_API_KEY` | `nl_` |
| **AI Grants OpenAI** | Quality-Gate Escalate & Playbook RAG | `https://api.openai.com/v1` | `gpt-5-nano` (escalate)<br>`text-embedding-3-small` (RAG) | `OPENAI_API_KEY` | `sk-` / `sk-proj-` |

---

## 1. TensorMux Integration

### 1.1 Auth & Configuration
- **Environment Variable:** `TMX_API_KEY`
- **Header:** `Authorization: Bearer <TMX_API_KEY>`
- **Base URL:** `https://api.tensormux.com/v1`
- **Key Prefix:** `tmx_` (e.g. `tmx_live_...`)
- **Active Model:** `glm-4-7-flash` (confirmed via live probe on `/v1/models`).

### 1.2 Exact SDK & HTTP Usage (Node/TS)
TensorMux provides a 100% OpenAI-compatible endpoint. In TypeScript/Node, use the official `openai` SDK with a custom `baseURL`:

```typescript
import OpenAI from 'openai';

export const rawTensorMuxClient = new OpenAI({
  baseURL: 'https://api.tensormux.com/v1',
  apiKey: process.env.TMX_API_KEY,
});
```

Calling chat completions:
```typescript
const completion = await rawTensorMuxClient.chat.completions.create({
  model: 'glm-4-7-flash',
  messages: [
    { role: 'system', content: 'You are the Journeyman Actor executing repository triage.' },
    { role: 'user', content: taskPrompt },
  ],
  temperature: 0.1,
});
```

Direct HTTP call:
```http
POST /v1/chat/completions HTTP/1.1
Host: api.tensormux.com
Authorization: Bearer tmx_xxxxxxxx
Content-Type: application/json

{
  "model": "glm-4-7-flash",
  "messages": [{"role": "user", "content": "ping"}],
  "temperature": 0.1
}
```

### 1.3 Tokens, Latency & Cost Extraction
- **Tokens:** Read directly from `completion.usage`:
  - `prompt_tokens`: `completion.usage?.prompt_tokens ?? 0`
  - `completion_tokens`: `completion.usage?.completion_tokens ?? 0`
  - `total_tokens`: `completion.usage?.total_tokens ?? 0`
- **Latency:** Capture execution duration with high-resolution timers:
  ```typescript
  const start = performance.now();
  const res = await client.chat.completions.create({ ... });
  const latencyMs = Math.round(performance.now() - start);
  ```
- **Cost Calculation:** Estimate cost based on `glm-4-7-flash` rate (~$0.10 / 1M tokens):
  ```typescript
  const costEstimate = (prompt_tokens + completion_tokens) * 0.0000001;
  ```

### 1.4 Journeyman Box Mapping
- **Actor:** Primary inference driver for step-by-step tool invocation against the GitHub readonly MCP.
- **Reflect:** Processes trace logs of failing runs to synthesize diffable updates for `Playbook.md` and append insights to `Journal.md`.
- **Patch:** Generates candidate patches under the patch budget.
- **Eval DEV / HELD-OUT:** Default inference engine for executing benchmark triage runs.

### 1.5 Pitfalls & Constraints
- **NO EMBEDDINGS:** TensorMux does not provide `/v1/embeddings`. Calling embeddings on TensorMux will throw a 404/Method Not Allowed. All embedding requests must go to AI Grants OpenAI.
- **Model Constrained:** Pinned strictly to `glm-4-7-flash`. Requests specifying standard OpenAI model names (e.g. `gpt-4o`) will fail.
- **No Direct Key Ingestion:** `TMX_API_KEY` must never be hardcoded, logged, or checked into source control.

### 1.6 Minimal Integration Sketch & Citations
- **Docs:** `https://api.tensormux.com/v1`, `https://www.tensormux.com/docs`, `https://github.com/KrxGu/Tensormux`

```typescript
// Minimal TensorMux Chat Completion
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'https://api.tensormux.com/v1',
  apiKey: process.env.TMX_API_KEY,
});

async function runBrainStep(prompt: string) {
  const t0 = performance.now();
  const res = await client.chat.completions.create({
    model: 'glm-4-7-flash',
    messages: [{ role: 'user', content: prompt }],
  });
  return {
    content: res.choices[0].message.content,
    usage: res.usage,
    latencyMs: Math.round(performance.now() - t0),
  };
}
```

---

## 2. Neatlogs Integration

### 2.1 Auth & Configuration
- **Environment Variable:** `NEATLOGS_API_KEY`
- **Header:** `Authorization: Bearer <NEATLOGS_API_KEY>` (or `x-api-key: <NEATLOGS_API_KEY>`)
- **Base Ingestion URL:** `https://api.neatlogs.com`
- **Key Prefix:** `nl_` (e.g. `nl_test_...` or `nl_live_...`)
- **Package:** `neatlogs` (`npm install neatlogs`)

### 2.2 Exact SDK & Calls (Node/TS)
Neatlogs provides an OpenTelemetry-based tracing SDK with a custom wrapper for OpenAI clients (`wrapOpenAI`).

```typescript
import { initNeatlogs, wrapOpenAI, SpanKind, flush, shutdown, tracer } from 'neatlogs';

// Initialize at application entry point BEFORE instantiating wrapped clients
initNeatlogs({
  apiKey: process.env.NEATLOGS_API_KEY,
  serviceName: 'journeyman',
  environment: process.env.NODE_ENV || 'development',
});
```

Creating manual spans for workflow phases and MCP tool invocations:
```typescript
import { SpanStatusCode } from '@opentelemetry/api';

await tracer.startActiveSpan('actor_tool_hop', {
  kind: SpanKind.TOOL,
  attributes: {
    'session_id': sessionId,
    'run_id': runId,
    'challenge_id': challengeId,
    'role': 'actor',
    'tool.name': 'github_readonly_get_issue',
    'playbook.version': activeVersion,
  },
}, async (span) => {
  try {
    const result = await executeMcpCall();
    span.setAttribute('tool.success', true);
    return result;
  } catch (err: any) {
    span.recordException(err);
    span.setStatus({ code: SpanStatusCode.ERROR, message: err.message });
    throw err;
  } finally {
    span.end();
  }
});
```

### 2.3 Tokens & Latency Extraction
- When using `wrapOpenAI`, model spans are generated automatically and record:
  - `llm.model.name`: `glm-4-7-flash` or `gpt-5-nano`
  - `llm.tokens.prompt`, `llm.tokens.completion`, `llm.tokens.total`
  - Span start/end timestamps representing precise network latency.
- In custom spans, manually write latency and token metrics via `span.setAttributes({ 'llm.tokens.total': tokens, 'duration_ms': latencyMs })`.

### 2.4 Journeyman Box Mapping
- **Trace Cockpit:** Primary UI consumption layer displaying the exact hierarchy of workflow spans, tool hops, token counts, and step latencies.
- **Runs Timeline:** Visualizes run history across DEV and HELD-OUT splits, tracking cost, speed, and accuracy across versions.
- **Actor / Reflect / Patch / Eval / RedTeam:** Each pipeline phase executes inside a root `WORKFLOW` span with child `AGENT`, `TOOL`, and `EMBEDDING` spans tagged with `role: <phase>`.

### 2.5 Pitfalls & Constraints
- **TypeScript Auto-Instrumentation Does Not Exist:** In the Python SDK, auto-instrumentation passes arrays of libraries. In Node/TS, `initNeatlogs({ instrumentations: [...] })` will fail with `UNSUPPORTED_INSTRUMENTATIONS`. You MUST use `wrapOpenAI(client)` explicitly.
- **CLI Process Exit Telemetry Loss:** Node exits immediately when the event loop empties, dropping un-flushed async HTTP trace spans. You MUST call `await flush()` and `await shutdown()` in a `finally` block at CLI termination.
- **Tracer Isolation:** Neatlogs manages an isolated OpenTelemetry instance. Do not attempt to re-register global tracer providers over Neatlogs.

### 2.6 Minimal Integration Sketch & Citations
- **Docs:** `https://docs.neatlogs.com/docs`, `https://docs.neatlogs.com/sdk/typescript`, `https://docs.neatlogs.com/integrations/openai`, `https://www.npmjs.com/package/neatlogs`

```typescript
import { initNeatlogs, wrapOpenAI, flush, shutdown } from 'neatlogs';
import OpenAI from 'openai';

initNeatlogs({ apiKey: process.env.NEATLOGS_API_KEY, serviceName: 'journeyman' });

const client = wrapOpenAI(new OpenAI({
  baseURL: 'https://api.tensormux.com/v1',
  apiKey: process.env.TMX_API_KEY,
}));

async function main() {
  try {
    const res = await client.chat.completions.create({
      model: 'glm-4-7-flash',
      messages: [{ role: 'user', content: 'Triage issue #123' }],
    });
    console.log(res.choices[0].message.content);
  } finally {
    await flush();
    await shutdown();
  }
}
```

---

## 3. AI Grants OpenAI Integration

### 3.1 Auth & Configuration
- **Environment Variable:** `OPENAI_API_KEY`
- **Header:** `Authorization: Bearer <OPENAI_API_KEY>`
- **Base URL:** `https://api.openai.com/v1`
- **Key Prefix:** `sk-` or `sk-proj-`
- **Models Used:**
  - `gpt-5-nano`: Quality-gate escalation for reasoning failures on Reflect, Patch, or complex Actor steps.
  - `text-embedding-3-small`: Primary vector embedding model (1536 dimensions) for Playbook RAG.
  - `text-embedding-ada-002`: Fallback vector embedding model.

### 3.2 Exact SDK & Calls (Node/TS)
Standard OpenAI client wrapped with Neatlogs:

```typescript
import OpenAI from 'openai';
import { wrapOpenAI } from 'neatlogs';

export const openaiClient = wrapOpenAI(new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
}));
```

Escalation Chat Completion:
```typescript
const escalationResponse = await openaiClient.chat.completions.create({
  model: 'gpt-5-nano',
  messages: [
    { role: 'system', content: 'You are the Journeyman Escalation Reasoner.' },
    { role: 'user', content: hardPrompt },
  ],
  temperature: 0.1,
});
```

Playbook Vector Embedding:
```typescript
const embeddingResponse = await openaiClient.embeddings.create({
  model: 'text-embedding-3-small',
  input: textChunk,
});
const embeddingVector: number[] = embeddingResponse.data[0].embedding;
```

### 3.3 Tokens & Latency Extraction
- Chat: `escalationResponse.usage.prompt_tokens`, `escalationResponse.usage.completion_tokens`, `escalationResponse.usage.total_tokens`.
- Embeddings: `embeddingResponse.usage.prompt_tokens`, `embeddingResponse.usage.total_tokens`.
- Wrapped automatically by Neatlogs into span attributes.

### 3.4 Journeyman Box Mapping
- **Context Gates & Router:** Evaluates prompt complexity; if TensorMux fails a verification gate, routes to `gpt-5-nano`.
- **Reflect & Patch Escalation:** If `glm-4-7-flash` produces an invalid JSON patch or non-diffable playbook update, escalates to `gpt-5-nano` to synthesize a valid patch.
- **Playbook RAG:** Generates vector embeddings for repo grounding documents, issue fixtures, and playbook chunks.

### 3.5 Pitfalls & Constraints
- **Never Default to OpenAI:** The primary cost and inference engine is TensorMux (`glm-4-7-flash`). OpenAI must only be invoked upon escalation or embedding queries.
- **Mandatory Escalation Telemetry:** Any escalation from TensorMux to `gpt-5-nano` must emit a structured warning log and span attribute explaining why.
- **Local Secret Isolation:** `OPENAI_API_KEY` lives strictly in gitignored `.env`. Never commit or print keys.

### 3.6 Minimal Integration Sketch & Citations
- **Docs:** `https://platform.openai.com/docs/api-reference`, `https://platform.openai.com/docs/guides/embeddings`

```typescript
import OpenAI from 'openai';

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function embedPlaybookChunk(chunk: string): Promise<number[]> {
  const resp = await openai.embeddings.create({
    model: 'text-embedding-3-small',
    input: chunk,
  });
  return resp.data[0].embedding;
}
```

---

## 4. Cross-Cutting Architecture Answers

### 4.1 Run-Family Grouping in Neatlogs (Pre-Patch vs. Post-Patch Replay)
To ensure a judge opens a single unified view in the Neatlogs Trace Cockpit comparing the failed pre-patch run and the post-patch replay run:
1. **Shared Session ID:** Assign both runs the identical `sessionId`, computed deterministically as `family_${challengeId}` or `challenge_${challengeId}`.
2. **Distinct Run IDs & Roles:** Each run has its own `runId` (e.g. `run_${challengeId}_v0` vs `run_${challengeId}_v1`).
3. **Span Hierarchy:**
   - Pre-patch run root span:
     ```typescript
     {
       name: 'run_pre_patch',
       attributes: {
         'session_id': `family_${challengeId}`,
         'run_id': `run_${challengeId}_v0`,
         'challenge_id': challengeId,
         'run.phase': 'pre-patch',
         'playbook.version': 'v0',
         'verdict': 'FAIL'
       }
     }
     ```
   - Post-patch replay root span:
     ```typescript
     {
       name: 'run_post_patch',
       attributes: {
         'session_id': `family_${challengeId}`,
         'run_id': `run_${challengeId}_v1`,
         'challenge_id': challengeId,
         'run.phase': 'post-patch',
         'playbook.version': 'v1',
         'parent_run_id': `run_${challengeId}_v0`,
         'verdict': 'PASS'
       }
     }
     ```
4. **Judge Cockpit Experience:** In Neatlogs, opening `family_${challengeId}` presents both runs chronologically, showing the exact tool failure on v0 and the patched resolution on v1.

### 4.2 Wrapping Custom `baseURL` (TensorMux) with Neatlogs
Neatlogs' `wrapOpenAI` intercepts method calls on the SDK client regardless of the target `baseURL`. No custom HTTP proxy is required:

```typescript
import OpenAI from 'openai';
import { wrapOpenAI } from 'neatlogs';

export function createTensorMuxClient() {
  const client = new OpenAI({
    baseURL: 'https://api.tensormux.com/v1',
    apiKey: process.env.TMX_API_KEY,
  });
  // wrapOpenAI wraps chat.completions.create and generates Neatlogs spans
  return wrapOpenAI(client);
}
```
All calls made through this client will automatically dispatch spans containing `glm-4-7-flash`, prompt/completion tokens, and latency to Neatlogs.

### 4.3 Quality-Gate Escalation Logging
When Reflect, Patch, or an Actor step fails validation on TensorMux and escalates to `gpt-5-nano`:
1. **Console / Logger Warning:** Emit an explicit structured warning log:
   ```typescript
   console.warn(JSON.stringify({
     level: 'WARN',
     event: 'QUALITY_GATE_ESCALATION',
     timestamp: new Date().toISOString(),
     challenge_id: challengeId,
     component: 'PatchSynthesizer', // or Actor / Reflect
     reason: 'SchemaValidationError: TensorMux failed to produce diffable patch block',
     original_model: 'glm-4-7-flash',
     escalated_model: 'gpt-5-nano',
     attempt: 2,
   }));
   ```
2. **Neatlogs Span Attributes & Event:**
   ```typescript
   activeSpan.addEvent('quality_gate_escalate', {
     'escalation.reason': 'Invalid JSON / missing diff chunk',
     'escalation.from': 'glm-4-7-flash',
     'escalation.to': 'gpt-5-nano',
   });
   activeSpan.setAttribute('escalated', true);
   activeSpan.setAttribute('escalation.reason', 'Invalid JSON / missing diff chunk');
   ```

### 4.4 Negative Constraints ("What We Must NOT Do")
- **NO Voice:** Skip Smallest.ai voice integration completely for v1.
- **NO Dodo Infrastructure:** Skip Dodo infrastructure.
- **NO Embeddings on TensorMux:** TensorMux is an LLM gateway only (`glm-4-7-flash`). Never call embeddings on `api.tensormux.com`.
- **NO API Keys in Chat or Git:** Never request, paste, or commit API keys.
- **NO Skipping Build Order:** Follow the locked sequence: Stage 1 (Actor ↔ MCP ↔ Traces) first.
- **NO OpenAI as Default:** Never route normal Actor or Reflect queries to OpenAI.

---

## 5. 10-Line "Wire It Like This" Recipe

```typescript
// 1. Initialize Neatlogs telemetry at application startup
import { initNeatlogs, wrapOpenAI, flush, shutdown, tracer, SpanKind } from 'neatlogs';
import OpenAI from 'openai';
initNeatlogs({ apiKey: process.env.NEATLOGS_API_KEY, serviceName: 'journeyman' });

// 2. Initialize everyday brain (TensorMux) and escalation brain (OpenAI) wrapped with Neatlogs
export const tmx = wrapOpenAI(new OpenAI({ baseURL: 'https://api.tensormux.com/v1', apiKey: process.env.TMX_API_KEY }));
export const oai = wrapOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY }));

// 3. Inference helper with quality-gate escalation and run-family span telemetry
export async function executeStep(task: string, famId: string, role: string, escalate = false) {
  const [client, model] = escalate ? [oai, 'gpt-5-nano'] : [tmx, 'glm-4-7-flash'];
  if (escalate) console.warn(`[ESCALATE] ${role} on ${famId}: falling back to gpt-5-nano`);
  return client.chat.completions.create({ model, messages: [{ role: 'user', content: task }] });
}

// 4. Teardown hook to guarantee telemetry dispatch before Node process termination
export async function cleanupTelemetry() { await flush(); await shutdown(); }
```
