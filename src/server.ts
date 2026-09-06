import { existsSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import express from "express";
import { loadCatalog } from "./catalog.js";
import { evalSnapshot, pollFixtureEval } from "./eval-merge.js";
import { ChallengeHoldoutError, HoldoutSealedError, promoteVersion, rejectVersion, rollbackVersion, runChallenge, runSplit } from "./harness.js";
import { readJournal } from "./journal.js";
import { partnerFlags, loadDotenv } from "./partners/env.js";
import { hasLocalStore, listNeatlogs } from "./partners/neatlogs.js";
import { retrievePlaybook } from "./partners/rag.js";
import { redTeamStatus } from "./redteam.js";
import { readScripts } from "./scripts.js";
import { GithubMcp } from "./mcp.js";
import { WEB_DIST } from "./paths.js";
import { githubToken, loadPolicy } from "./policy.js";
import {
  bootStore,
  getRun,
  getTrace,
  listPlaybookVersions,
  listRuns,
  listTraces,
  loadFacts,
  loadState,
  readPlaybookMarkdown,
} from "./store.js";

const PORT = Number(process.env.PORT || 8787);

function tools() {
  return new GithubMcp(loadPolicy());
}

export function createApp() {
  loadDotenv();
  bootStore();
  const app = express();
  app.use(express.json({ limit: "2mb" }));

  app.get("/api/health", (_req, res) => {
    res.json({
      ok: true,
      product: "journeyman",
      token: Boolean(githubToken()),
      mcp: loadPolicy().mcp.url,
      eval: evalSnapshot(),
      partners: partnerFlags(),
      neatlogs: hasLocalStore(),
    });
  });

  app.get("/api/state", (_req, res) => {
    const state = loadState();
    res.json({
      ...state,
      playbooks: listPlaybookVersions(),
      eval: evalSnapshot(),
      token: Boolean(githubToken()),
      redteam: redTeamStatus(),
      scripts: readScripts().length,
      partners: partnerFlags(),
    });
  });

  app.get("/api/neatlogs", (req, res) => {
    const runId = typeof req.query.run === "string" ? req.query.run : undefined;
    const familyId = typeof req.query.family === "string" ? req.query.family : undefined;
    res.json({ records: listNeatlogs({ runId, familyId }) });
  });

  app.get("/api/rag", async (req, res) => {
    const q = typeof req.query.q === "string" ? req.query.q : "label rules owners search";
    const state = loadState();
    const facts = loadFacts(state.active_version);
    const rag = await retrievePlaybook({
      query: q,
      facts,
      run_id: "ui",
      family_id: state.last_family_id ?? "ui",
      version: facts.version,
    });
    res.json({ excerpt: rag.excerpt, hits: rag.hits });
  });

  app.get("/api/journal", (_req, res) => {
    res.json({ markdown: readJournal() });
  });

  app.get("/api/runs", (_req, res) => {
    res.json({ runs: listRuns() });
  });

  app.get("/api/runs/:id", (req, res) => {
    const run = getRun(req.params.id);
    if (!run) return res.status(404).json({ error: "run not found" });
    res.json({ run, traces: listTraces(run.id) });
  });

  app.get("/api/playbooks", (_req, res) => {
    res.json({
      versions: listPlaybookVersions().map((version) => ({
        version,
        markdown: readPlaybookMarkdown(version),
      })),
      active: loadState().active_version,
    });
  });

  app.get("/api/playbooks/:version", (req, res) => {
    const version = Number(req.params.version);
    res.json({ version, markdown: readPlaybookMarkdown(version) });
  });

  app.get("/api/traces", (req, res) => {
    const runId = typeof req.query.run === "string" ? req.query.run : undefined;
    res.json({ traces: listTraces(runId) });
  });

  app.get("/api/traces/:id", (req, res) => {
    const trace = getTrace(req.params.id);
    if (!trace) return res.status(404).json({ error: "trace not found" });
    res.json({ trace });
  });

  app.post("/api/eval/merge", (_req, res) => {
    res.json(pollFixtureEval());
  });

  app.post("/api/eval/dev", async (req, res) => {
    const version = Number(req.body?.playbook_version ?? loadState().active_version);
    const mcp = tools();
    try {
      pollFixtureEval();
      const run = await runSplit({
        split: "dev",
        playbookVersion: version,
        tools: mcp,
        catalog: loadCatalog(),
        reflect: req.body?.reflect !== false,
      });
      res.json({ run });
    } catch (err) {
      res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      await mcp.close();
    }
  });

  app.post("/api/eval/holdout", async (req, res) => {
    const version = Number(req.body?.playbook_version);
    if (!Number.isFinite(version)) {
      return res.status(400).json({ error: "playbook_version required" });
    }
    const mcp = tools();
    try {
      pollFixtureEval();
      const run = await runSplit({
        split: "holdout",
        playbookVersion: version,
        tools: mcp,
        catalog: loadCatalog(),
        allowHoldout: true,
      });
      res.json({ run });
    } catch (err) {
      if (err instanceof HoldoutSealedError) return res.status(403).json({ error: err.message });
      res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      await mcp.close();
    }
  });

  app.post("/api/promote", (req, res) => {
    const version = Number(req.body?.playbook_version);
    const action = String(req.body?.action ?? "approve");
    if (action === "reject") {
      return res.json(rejectVersion(version));
    }
    if (action === "rollback") {
      const rolled = rollbackVersion();
      if (!rolled.ok) return res.status(409).json(rolled);
      return res.json(rolled);
    }
    const holdoutRunId = String(req.body?.holdout_run_id ?? "");
    const holdout = holdoutRunId ? getRun(holdoutRunId) : undefined;
    const result = promoteVersion(version, holdout);
    if (!result.ok) return res.status(409).json(result);
    res.json(result);
  });

  app.post("/api/challenge", async (req, res) => {
    const prompt = String(req.body?.prompt ?? "").trim();
    if (!prompt) return res.status(400).json({ error: "prompt required" });
    if (req.body?.split === "holdout") {
      return res.status(403).json({ error: "Challenge cannot touch hold-out" });
    }
    const mcp = tools();
    try {
      const result = await runChallenge({
        prompt,
        type: req.body?.type,
        github: req.body?.github,
        tools: mcp,
        playbookVersion: req.body?.playbook_version,
      });
      res.json(result);
    } catch (err) {
      if (err instanceof ChallengeHoldoutError) return res.status(403).json({ error: err.message });
      res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      await mcp.close();
    }
  });

  if (existsSync(WEB_DIST)) {
    app.use(express.static(WEB_DIST));
    app.get(/.*/, (_req, res) => {
      res.sendFile(join(WEB_DIST, "index.html"));
    });
  }

  return app;
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const app = createApp();
  app.listen(PORT, () => {
    console.log(`Journeyman API http://127.0.0.1:${PORT}`);
    const first = pollFixtureEval();
    if (numbersHint()) {
      console.log("eval JSON numbers are still 0 — polling sibling fixture worker files");
    } else if (first.merged.length) {
      console.log(`merged GitHub numbers from ${first.merged.map((m) => m.path).join(", ")}`);
    }
    setInterval(() => {
      if (numbersHint()) pollFixtureEval();
    }, 30_000).unref();
  });
}

function numbersHint(): boolean {
  return evalSnapshot().zeros;
}
