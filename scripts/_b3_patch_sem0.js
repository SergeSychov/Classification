#!/usr/bin/env node
/**
 * Inject Sem0 (product_kind / attr_profile) zone before Sem1 in
 * classification-stage2-hierarchy-dev.
 *
 * Does NOT modify classification-stage2-dev.
 * Does NOT change Load stub SQL, Norm Dict wiring, or terminal snapshot path.
 * Wires: Limit → Sem0 → Sem1 Build → … (existing Sem1 chain).
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = path.resolve(__dirname, "..");
const WF_PATH = path.join(ROOT, "workflows", "classification-stage2-hierarchy-dev.json");
const NODES_DIR = path.join(ROOT, "scripts", "hierarchy_nodes");

const S0 = {
  build: "Sem0 — Build Prompt",
  prepare: "Sem0 — LLM Prepare",
  agent: "Sem0 — AI Agent",
  deepseek: "Sem0 — DeepSeek",
  merge: "Sem0 — Merge LLM",
  post: "Sem0 — Post-process",
  sticky: "🔗 Sem0 — kind/family before Sem1",
};

const S1 = {
  build: "Sem — Build Prompt",
  prepare: "Sem — LLM Prepare",
  post: "Sem — Post-process",
};

function loadJs(name) {
  return fs.readFileSync(path.join(NODES_DIR, name), "utf8");
}

function uuid() {
  return crypto.randomUUID();
}

function main() {
  const wf = JSON.parse(fs.readFileSync(WF_PATH, "utf8"));
  const connections = wf.connections;

  const drop = new Set(Object.values(S0));
  wf.nodes = wf.nodes.filter((n) => !drop.has(n.name));

  const sharedDs = wf.nodes.find((n) => n.name === "Shared — DeepSeek");
  if (!sharedDs || !sharedDs.credentials) {
    throw new Error("Shared — DeepSeek credential template missing");
  }

  const s1Build = wf.nodes.find((n) => n.name === S1.build);
  if (!s1Build) throw new Error("Sem — Build Prompt missing; run _b3_patch_sem.js first");

  // Refresh Sem1 sources from disk (v2 prompt + enforce).
  const s1Prepare = wf.nodes.find((n) => n.name === S1.prepare);
  const s1Post = wf.nodes.find((n) => n.name === S1.post);
  if (!s1Prepare || !s1Post) throw new Error("Sem1 Prepare/Post missing");
  s1Build.parameters.jsCode = loadJs("sem_build_prompt.js");
  s1Prepare.parameters.jsCode = loadJs("sem_llm_prepare.js");
  s1Post.parameters.jsCode = loadJs("sem_post_process.js");

  const s1PrepLog = wf.nodes.find((n) => n.name === "Sem — Prepare Log");
  if (s1PrepLog && s1PrepLog.parameters) {
    s1PrepLog.parameters.jsCode = loadJs("sem_prepare_log.js");
  }

  // Refresh Sem attr Norm if already wired (idempotent with _b3_patch_sem_norm.js).
  const s1Norm = wf.nodes.find((n) => n.name === "Norm — Normalize Sem attrs");
  if (s1Norm && s1Norm.parameters) {
    s1Norm.parameters.jsCode = loadJs("sem_normalize_attrs.js");
  }

  const build = {
    parameters: { jsCode: loadJs("sem0_build_prompt.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [1180, -1296],
    id: uuid(),
    name: S0.build,
    notes: "Sem0: product_kind + attr_profile; no category_id",
  };
  const prepare = {
    parameters: { jsCode: loadJs("sem0_llm_prepare.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [1180, -1120],
    id: uuid(),
    name: S0.prepare,
  };
  const agent = {
    parameters: {
      promptType: "define",
      text: "={{ $json.prompt_user }}",
      options: { systemMessage: "={{ $json.prompt_system }}" },
    },
    type: "@n8n/n8n-nodes-langchain.agent",
    typeVersion: 1.7,
    position: [1180, -960],
    id: uuid(),
    name: S0.agent,
  };
  const deepseek = {
    parameters: {
      model: sharedDs.parameters?.model || "deepseek-v4-flash",
      options: {},
    },
    type: "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
    typeVersion: sharedDs.typeVersion || 1,
    position: [1180, -800],
    id: uuid(),
    name: S0.deepseek,
    credentials: JSON.parse(JSON.stringify(sharedDs.credentials)),
  };
  const merge = {
    parameters: {
      mode: "combine",
      combineBy: "combineByPosition",
      options: {},
    },
    type: "n8n-nodes-base.merge",
    typeVersion: 3.2,
    position: [1400, -1120],
    id: uuid(),
    name: S0.merge,
  };
  const post = {
    parameters: { jsCode: loadJs("sem0_post_process.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [1400, -960],
    id: uuid(),
    name: S0.post,
    notes: "Writes product_kind/attr_profile; soft-continue to Sem1",
  };
  const sticky = {
    parameters: {
      content:
        "## Sem0\n\n**Live:** Limit → Sem0 Build → Prepare → Agent/DeepSeek → Merge → Post → Sem1 Build\n\nSets product_kind / product_family / attr_profile for Sem1.\nSoft-fail → other + all attrs applicable.\nNo snapshot. No Dir+.",
      height: 280,
      width: 380,
      color: 4,
    },
    id: uuid(),
    name: S0.sticky,
    type: "n8n-nodes-base.stickyNote",
    typeVersion: 1,
    position: [1120, -1600],
  };

  const p1Agent = wf.nodes.find((n) => n.name === "P1 — AI Agent");
  if (p1Agent?.typeVersion) agent.typeVersion = p1Agent.typeVersion;
  const s1Agent = wf.nodes.find((n) => n.name === "Sem — AI Agent");
  if (s1Agent?.typeVersion) agent.typeVersion = s1Agent.typeVersion;

  const insertAt = wf.nodes.findIndex((n) => n.name === "Load — Limit Batch");
  const at = insertAt >= 0 ? insertAt + 1 : wf.nodes.length;
  wf.nodes.splice(at, 0, build, prepare, agent, deepseek, merge, post, sticky);

  // Rewire Limit → Sem0 → Sem1 Build
  connections["Load — Limit Batch"] = {
    main: [[{ node: S0.build, type: "main", index: 0 }]],
  };
  connections[S0.build] = {
    main: [[{ node: S0.prepare, type: "main", index: 0 }]],
  };
  connections[S0.prepare] = {
    main: [
      [
        { node: S0.agent, type: "main", index: 0 },
        { node: S0.merge, type: "main", index: 0 },
      ],
    ],
  };
  connections[S0.agent] = {
    main: [[{ node: S0.merge, type: "main", index: 1 }]],
  };
  connections[S0.deepseek] = {
    ai_languageModel: [[{ node: S0.agent, type: "ai_languageModel", index: 0 }]],
  };
  connections[S0.merge] = {
    main: [[{ node: S0.post, type: "main", index: 0 }]],
  };
  connections[S0.post] = {
    main: [[{ node: S1.build, type: "main", index: 0 }]],
  };

  // Safety asserts
  const load = wf.nodes.find((n) => n.name === "Load — Select Batch");
  if (!load?.parameters?.query?.includes("WHERE false")) {
    throw new Error("Load stub must stay WHERE false");
  }
  if (connections["Norm — Normalize Dict"]) {
    throw new Error("Norm — Normalize Dict must stay unwired");
  }
  const initOut = connections["Run — Init Constants"]?.main?.[0] || [];
  const hasEmpty = initOut.some((l) => l.node === "Shell — Ensure Empty Fin");
  if (!hasEmpty) throw new Error("Empty Fin path broken");

  const allTargets = [];
  for (const [src, ports] of Object.entries(connections)) {
    if (!src.startsWith("Sem0 —") && !src.startsWith("Sem —")) continue;
    for (const arr of Object.values(ports)) {
      for (const links of arr) {
        for (const link of links) allTargets.push(link.node);
      }
    }
  }
  if (allTargets.includes("DB — Upsert Snapshot") || allTargets.includes("DB — Prepare Snapshot")) {
    throw new Error("Sem/Sem0 must not wire to snapshot upsert");
  }
  if (allTargets.includes("P1 — Build Prompt")) {
    throw new Error("Sem/Sem0 must not reconnect P1");
  }

  fs.writeFileSync(WF_PATH, JSON.stringify(wf, null, 2) + "\n", "utf8");
  console.log(`Patched ${WF_PATH}`);
  console.log("  + Sem0 zone (Build/Prepare/Agent/DeepSeek/Merge/Post)");
  console.log("  refreshed Sem1 Build/Prepare/Post from sources (v2)");
  console.log("  wire: Limit → Sem0 → Sem1 Build → …");
  console.log("  Load WHERE false retained; Dict Norm unwired; empty Fin retained");
}

main();
