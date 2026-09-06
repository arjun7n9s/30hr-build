# Partner stack research brief

You are a **research worker only**. Do not implement Journeyman. Do not edit architecture.md. Do not ask anyone to paste API keys into chat. Do not commit secrets.

Product: Journeyman. We will later wire these partners into the locked loop. Your job is to figure out **how to use them for real**, then write `plans/partner-research.md` in this workspace.

## What we already decided (do not reopen)

- **TensorMux** is the everyday brain. Actor, Reflect, and Patch call its OpenAI-compatible endpoint `https://api.tensormux.com/v1` with model `glm-4-7-flash` and a `tmx_` key from env (`TMX_API_KEY`). Every model call must record tokens, latency, and a rough cost into the run trace. **No embeddings on TensorMux.**
- **Neatlogs** is the system of record for traces and the Trace cockpit. Every Actor tool hop and every model call is a span: run id, challenge, version, role (`actor` / `reflect` / `patch` / `eval` / `redteam`), tool name, success/error, timing, tokens, playbook bits hit. Fail → patch → replay must be the same run family, before/after.
- **AI Grants OpenAI** lives only in local `.env`. Use `gpt-5-nano` when TensorMux fails a quality gate on Reflect, Patch, or a hard Actor step — log that you escalated and why. Use `text-embedding-3-small` (`text-embedding-ada-002` backup) for playbook RAG. Default path stays TensorMux. Never ask for keys in chat.
- **Skip** Smallest.ai voice for v1. **Skip** Dodo as infrastructure.

Env template is `.env.example`. Keys go in gitignored `.env`.

## Research these docs (live web, required)

Start here, then follow their own links:

1. Neatlogs: https://docs.neatlogs.com/docs and the rest of that site (SDK, TypeScript, span kinds, HTTP inject, OpenAI wrap, MCP guides). Also https://www.npmjs.com/package/neatlogs and https://docs.neatlogs.com/sdk/typescript if it exists.
2. TensorMux: https://api.tensormux.com/v1 (hosted, `tmx_` keys, `glm-4-7-flash`). Also https://www.tensormux.com/docs and https://github.com/KrxGu/Tensormux so you know hosted vs OSS gateway. We are using the **hosted** OpenAI-compatible endpoint, not self-hosting the gateway unless docs say the hosted API is the same.
3. AI Grants OpenAI: find the official aigrants docs for GPT + embeddings (base URL, model names, auth header). Also OpenAI-compatible chat + embeddings (`text-embedding-3-small`, ada-002).

## Answer in `plans/partner-research.md`

For **each** partner (TensorMux, Neatlogs, AI Grants OpenAI):

1. Auth: env var name, header, base URL, what a key looks like (prefix only, e.g. `tmx_`).
2. Exact SDK or HTTP calls we should use from a Node/TS app (Journeyman is TS).
3. How to get tokens + latency out of a response so we can write cost into traces.
4. How this maps onto Journeyman boxes (Actor, Reflect, Patch, Eval, RedTeam, playbook RAG, Trace cockpit).
5. Pitfalls (init-before-import, no embeddings on TensorMux, escalate logging, run-family grouping in Neatlogs).
6. A **minimal** integration sketch (no full product). Cite URLs.

Also answer:

- How to group Neatlogs spans so a judge opens the same run family before and after a patch.
- How to wrap a custom OpenAI-compatible client (TensorMux `baseURL`) so Neatlogs still sees model spans.
- Quality-gate escalate: what we should log when we flip Actor/Reflect/Patch from TensorMux → `gpt-5-nano`.
- What we should **not** do (voice, Dodo, embedding via TensorMux, keys in chat).

End with a 10-line “wire it like this” recipe the implementation worker can follow.

Commit locally only if you must; **do not push** until 30hr-build-4 reviews. No Co-authored-by trailers. Prefer just writing the research file and waiting.
