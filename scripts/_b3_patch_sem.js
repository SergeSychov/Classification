#!/usr/bin/env node
/**
 * B3 Sem: inject Sem zone into classification-stage2-hierarchy-dev.
 *
 * Does NOT modify classification-stage2-dev.
 * Does NOT change Load stub SQL, Norm Dict wiring, or terminal snapshot path.
 * Wires: Limit → Sem → log-only Insert → Fin Merge Barrier.
 * Empty Fin path (Shell — Ensure Empty Fin → Close Run) unchanged.
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = path.resolve(__dirname, "..");
const WF_PATH = path.join(ROOT, "workflows", "classification-stage2-hierarchy-dev.json");
const NODES_DIR = path.join(ROOT, "scripts", "hierarchy_nodes");

const NAMES = {
  build: "Sem — Build Prompt",
  prepare: "Sem — LLM Prepare",
  agent: "Sem — AI Agent",
  deepseek: "Sem — DeepSeek",
  merge: "Sem — Merge LLM",
  post: "Sem — Post-process",
  route: "Sem — Route",
  prepLog: "Sem — Prepare Log",
  sticky: "🔗 Sem — B3 (log-only; Dir later)",
};

function loadJs(name) {
  return fs.readFileSync(path.join(NODES_DIR, name), "utf8");
}

function uuid() {
  return crypto.randomUUID();
}

function main() {
  const wf = JSON.parse(fs.readFileSync(WF_PATH, "utf8"));
  const nodes = wf.nodes;
  const connections = wf.connections;

  const drop = new Set(Object.values(NAMES));
  wf.nodes = nodes.filter((n) => !drop.has(n.name));

  const sharedDs = wf.nodes.find((n) => n.name === "Shared — DeepSeek");
  if (!sharedDs || !sharedDs.credentials) {
    throw new Error("Shared — DeepSeek credential template missing");
  }

  const insertLog = wf.nodes.find((n) => n.name === "DB — Insert Log");
  if (!insertLog) throw new Error("DB — Insert Log missing");

  const build = {
    parameters: { jsCode: loadJs("sem_build_prompt.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [1400, -1296],
    id: uuid(),
    name: NAMES.build,
    notes: "B3 Sem: attrs only; no category_id",
  };
  const prepare = {
    parameters: { jsCode: loadJs("sem_llm_prepare.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [1620, -1296],
    id: uuid(),
    name: NAMES.prepare,
  };
  const agent = {
    parameters: {
      promptType: "define",
      text: "={{ $json.prompt_user }}",
      options: { systemMessage: "={{ $json.prompt_system }}" },
    },
    type: "@n8n/n8n-nodes-langchain.agent",
    typeVersion: 1.7,
    position: [1840, -1296],
    id: uuid(),
    name: NAMES.agent,
  };
  const deepseek = {
    parameters: {
      model: sharedDs.parameters?.model || "deepseek-v4-flash",
      options: {},
    },
    type: "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
    typeVersion: sharedDs.typeVersion || 1,
    position: [1840, -1120],
    id: uuid(),
    name: NAMES.deepseek,
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
    position: [2060, -1296],
    id: uuid(),
    name: NAMES.merge,
  };
  const post = {
    parameters: { jsCode: loadJs("sem_post_process.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [2280, -1296],
    id: uuid(),
    name: NAMES.post,
  };
  const route = {
    parameters: {
      rules: {
        values: [
          {
            conditions: {
              options: {
                caseSensitive: true,
                leftValue: "",
                typeValidation: "strict",
                version: 2,
              },
              conditions: [
                {
                  id: uuid(),
                  leftValue: "={{ $json.next_action }}",
                  rightValue: "direction_select",
                  operator: {
                    type: "string",
                    operation: "equals",
                    name: "filter.operator.equals",
                  },
                },
              ],
              combinator: "and",
            },
            renameOutput: true,
            outputKey: "direction_select",
          },
        ],
      },
      options: { fallbackOutput: "extra" },
    },
    type: "n8n-nodes-base.switch",
    typeVersion: 3.2,
    position: [2500, -1296],
    id: uuid(),
    name: NAMES.route,
    notes: "Future-safe seam for B4 Dir; v1 both outs → Sem Prepare Log",
  };
  const prepLog = {
    parameters: { jsCode: loadJs("sem_prepare_log.js") },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: [2720, -1296],
    id: uuid(),
    name: NAMES.prepLog,
    notes: "Hierarchy Sem log-only; selected_category_id=null; no snapshot",
  };
  const sticky = {
    parameters: {
      content:
        "## Sem (B3)\n\n**Live:** Limit → Build → Prepare → Agent/DeepSeek → Merge → Post → Route → Prepare Log → Insert Log → Fin Barrier\n\n**No** Upsert Snapshot (terminal-only).\n**No** Dict Norm on this path.\n**No** category_id in Sem JSON.\nDefault `next_action=direction_select` (Dir not wired).\nLoad stays `WHERE false`.",
      height: 320,
      width: 420,
      color: 5,
    },
    id: uuid(),
    name: NAMES.sticky,
    type: "n8n-nodes-base.stickyNote",
    typeVersion: 1,
    position: [1360, -1600],
  };

  // Match agent typeVersion from P1 if present
  const p1Agent = wf.nodes.find((n) => n.name === "P1 — AI Agent");
  if (p1Agent?.typeVersion) agent.typeVersion = p1Agent.typeVersion;

  const insertAt = wf.nodes.findIndex((n) => n.name === "Load — Limit Batch");
  const at = insertAt >= 0 ? insertAt + 1 : wf.nodes.length;
  wf.nodes.splice(
    at,
    0,
    build,
    prepare,
    agent,
    deepseek,
    merge,
    post,
    route,
    prepLog,
    sticky
  );

  // Rewire Limit → Sem Build
  connections["Load — Limit Batch"] = {
    main: [[{ node: NAMES.build, type: "main", index: 0 }]],
  };
  connections[NAMES.build] = {
    main: [[{ node: NAMES.prepare, type: "main", index: 0 }]],
  };
  connections[NAMES.prepare] = {
    main: [
      [
        { node: NAMES.agent, type: "main", index: 0 },
        { node: NAMES.merge, type: "main", index: 0 },
      ],
    ],
  };
  connections[NAMES.agent] = {
    main: [[{ node: NAMES.merge, type: "main", index: 1 }]],
  };
  connections[NAMES.deepseek] = {
    ai_languageModel: [
      [{ node: NAMES.agent, type: "ai_languageModel", index: 0 }],
    ],
  };
  connections[NAMES.merge] = {
    main: [[{ node: NAMES.post, type: "main", index: 0 }]],
  };
  connections[NAMES.post] = {
    main: [[{ node: NAMES.route, type: "main", index: 0 }]],
  };
  // Both Route outputs → Prepare Log (v1); B4 will rewire direction_select → Dir
  connections[NAMES.route] = {
    main: [
      [{ node: NAMES.prepLog, type: "main", index: 0 }],
      [{ node: NAMES.prepLog, type: "main", index: 0 }],
    ],
  };
  connections[NAMES.prepLog] = {
    main: [[{ node: "DB — Insert Log", type: "main", index: 0 }]],
  };

  // Safety asserts
  const load = wf.nodes.find((n) => n.name === "Load — Select Batch");
  if (!load?.parameters?.query?.includes("WHERE false")) {
    throw new Error("Load stub must stay WHERE false");
  }
  if (connections["Norm — Normalize Dict"]) {
    throw new Error("Norm — Normalize Dict must stay unwired");
  }
  if (!connections["Shell — Ensure Empty Fin"]) {
    // ensure empty fin still connected from Init
  }
  const initOut = connections["Run — Init Constants"]?.main?.[0] || [];
  const hasEmpty = initOut.some((l) => l.node === "Shell — Ensure Empty Fin");
  if (!hasEmpty) throw new Error("Empty Fin path broken");

  // Ensure Sem does not connect to Upsert Snapshot
  const allTargets = [];
  for (const [src, ports] of Object.entries(connections)) {
    if (!src.startsWith("Sem —")) continue;
    for (const arr of Object.values(ports)) {
      for (const links of arr) {
        for (const link of links) allTargets.push(link.node);
      }
    }
  }
  if (allTargets.includes("DB — Upsert Snapshot") || allTargets.includes("DB — Prepare Snapshot")) {
    throw new Error("Sem must not wire to snapshot upsert");
  }
  if (allTargets.includes("P1 — Build Prompt")) {
    throw new Error("Sem must not reconnect P1");
  }

  fs.writeFileSync(WF_PATH, JSON.stringify(wf, null, 2) + "\n", "utf8");
  console.log(`Patched ${WF_PATH}`);
  console.log("  + Sem zone (Build/Prepare/Agent/DeepSeek/Merge/Post/Route/Prepare Log)");
  console.log("  wire: Limit → Sem → Prepare Log → Insert Log → Fin Barrier");
  console.log("  Load WHERE false retained; Dict Norm unwired; empty Fin retained");
}

main();
