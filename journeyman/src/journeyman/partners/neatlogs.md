# Neatlogs ingest (verified against current HTTP docs)

Source of truth for this file: [HTTP Trace Injection](https://docs.neatlogs.com/sdk/http-injection) (read 2026-09-06). Dashboard help and the HTTP docs agree: you POST one nested JSON trace to the ingest host. You do not POST to `app.neatlogs.com`. There is no `api.neatlogs.com` receiver in the current docs.

## Hosts

| Role | URL |
|---|---|
| Ingest (write traces) | `https://ingest.neatlogs.com` |
| Dashboard / cockpit (read, keys, sessions) | `https://app.neatlogs.com` |
| Endpoint | `POST /v1/trace` |
| Full URL | `https://ingest.neatlogs.com/v1/trace` |

Self-hosting: point `NEATLOGS_BASE_URL` at your own host. The path stays `/v1/trace`.

Do not confuse this with OpenTelemetry: OTLP is `POST /v1/traces` (protobuf/gRPC). Journeyman uses the JSON receiver only.

## Auth

Write key (`nlw_…`): ingest-only, per-user. It can POST traces and cannot read data.

Header (the only auth the docs specify):

```
Authorization: Bearer <your-write-key>
```

Also send `Content-Type: application/json`.

A write key identifies **you**, not a project. Name the target project on every root object with the `project` field (project **name**, not a UUID). That is `NEATLOGS_PROJECT_ID` in `.env`.

Journeyman maps `NEATLOGS_API_KEY` to that Bearer write key. Do not send `x-api-key`.

## Exact JSON schema

One object per request. Nesting via `children` is the span tree. You never send `trace_id`, `span_id`, or `parent_span_id` — Neatlogs generates them. `project` is root-only.

Every field except `name` is optional. The same fields apply to the root and to any child:

```
{
  "name": "string (required) — root name becomes the workflow name",
  "project": "string (root only, required with a write key) — target project NAME",
  "kind": "string (optional) — span kind; inferred from fields when omitted",
  "input": "any (optional)",
  "output": "any (optional)",
  "model": "string (optional)",
  "tokens": { "prompt": 0, "completion": 0, "total": 0 },
  "query": "any (optional)",
  "documents": "any (optional)",
  "tool_name": "string (optional)",
  "passed": "boolean (optional)",
  "score": "number (optional)",
  "status": "OK | ERROR (optional, default OK)",
  "error": "string (optional)",
  "start": "string (optional) — ISO timestamp",
  "end": "string (optional) — ISO timestamp",
  "duration_ms": "number (optional)",
  "metadata": { "any": "arbitrary key/values" },
  "attributes": { "neatlogs.llm.temperature": 0.7 },
  "logs": [{ "level": "info", "message": "string", "timestamp": "ISO (optional)" }],
  "children": [{ "name": "nested span", "kind": "TOOL" }]
}
```

Canonical `kind` values: `WORKFLOW`, `LLM`, `TOOL`, `AGENT`, `CHAIN`, `TASK`, `RETRIEVER`, `EMBEDDING`, `VECTOR_STORE`, `RERANKER`, `GUARDRAIL`, `EVALUATOR`, `MCP_TOOL`, `HTTP`.

Inference if `kind` is omitted (first match wins): `tool_name` → `TOOL`; `passed`/`score` → `GUARDRAIL`; `model`/`tokens` → `LLM`; `query`/`documents` → `RETRIEVER`; else root → `WORKFLOW`, node with children → `CHAIN`, bare leaf → `TOOL`.

Session / end-user belong on the **root** only:

- `attributes["neatlogs.session.id"]`
- `attributes["neatlogs.end_user.id"]`

## Response

Success `200`:

```
{ "success": true, "trace_id": "a1b2c3d4e5f6...", "spans": 2 }
```

`trace_id` is a 32-character hex id. Correlate cockpit views with that id. Validation error `400` returns `{ "error": "Validation error", "details": { "fieldErrors": … } }`.

## Rate limits / size

Docs “Limits” section (no QPS number published):

- Max payload: **50 MB** per request (larger payloads rejected).
- Latency: traces typically appear within 1–2 seconds.
- Batch a whole run as **one nested trace** rather than posting spans one-by-one.

## Example curl

```bash
curl -X POST https://ingest.neatlogs.com/v1/trace \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $NEATLOGS_API_KEY" \
  -d '{
    "name": "journeyman-run",
    "project": "journeyman",
    "kind": "WORKFLOW",
    "attributes": { "neatlogs.session.id": "demo-run1" },
    "children": [
      {
        "name": "answer",
        "kind": "LLM",
        "model": "glm-4-7-flash",
        "input": "label issue 12",
        "output": "area:api type:bug",
        "tokens": { "prompt": 12, "completion": 8 }
      }
    ]
  }'
```

## Journeyman mapping

`NeatlogsTraceSink` buffers graph nodes (Actor, Router, Reflect, Patch, Eval DEV, Eval Hold, RedTeam) as `children`, then `flush()` POSTs one `WORKFLOW` root. Env:

- `NEATLOGS_API_KEY` — write key for the Bearer header
- `NEATLOGS_PROJECT_ID` — root `project` name
- `NEATLOGS_BASE_URL` — default `https://ingest.neatlogs.com`

If `NEATLOGS_API_KEY` is unset, the sink is a no-op (`NullTraceSink`). Keys stay in local `.env`. Never paste them into chat.
