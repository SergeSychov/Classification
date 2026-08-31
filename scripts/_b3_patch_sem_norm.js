#!/usr/bin/env node
/**
 * Inject / refresh Norm — Normalize Sem attrs between Sem Post-process and Sem Route.
 * hierarchy-dev only. Idempotent.
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = path.resolve(__dirname, "..");
const WF_PATH = path.join(ROOT, "workflows", "classification-stage2-hierarchy-dev.json");
const NODES_DIR = path.join(ROOT, "scripts", "hierarchy_nodes");

const NORM = "Norm — Normalize Sem attrs";
const POST = "Sem — Post-process";
const ROUTE = "Sem — Route";

function loadJs(name) {
  return fs.readFileSync(path.join(NODES_DIR, name), "utf8");
}

function uuid() {
  return crypto.randomUUID();
}

function main() {
  const wf = JSON.parse(fs.readFileSync(WF_PATH, "utf8"));
  const jsCode = loadJs("sem_normalize_attrs.js");

  // Drop existing Norm node if present (refresh).
  wf.nodes = wf.nodes.filter((n) => n.name !== NORM);

  const post = wf.nodes.find((n) => n.name === POST);
  const route = wf.nodes.find((n) => n.name === ROUTE);
  if (!post || !route) {
    throw new Error("Sem — Post-process / Sem — Route missing; run Sem patchers first");
  }

  const postPos = post.position || [2280, -1296];
  const routePos = route.position || [2500, -1296];
  const normPos = [
    Math.round((postPos[0] + routePos[0]) / 2),
    postPos[1],
  ];

  const normNode = {
    parameters: { jsCode },
    type: "n8n-nodes-base.code",
    typeVersion: 2,
    position: normPos,
    id: uuid(),
    name: NORM,
    notes:
      "Normalize administration_route / dosage_form / age_segment to fixed dictionaries. See sem_attr_dictionaries.md",
  };
  wf.nodes.push(normNode);

  // Wire: Post → Norm → Route
  wf.connections[POST] = {
    main: [[{ node: NORM, type: "main", index: 0 }]],
  };
  wf.connections[NORM] = {
    main: [[{ node: ROUTE, type: "main", index: 0 }]],
  };

  // Refresh sticky Sem note if present.
  const sticky = wf.nodes.find((n) => n.name === "🔗 Sem — B3 (log-only; Dir later)");
  if (sticky && sticky.parameters) {
    sticky.parameters.content =
      "## Sem (B3)\n\n**Live:** Limit → Sem0 → Sem1 Build → … → Post → **Norm Sem attrs** → Route → Prepare Log → Insert Log → Fin Barrier\n\n**No** Upsert Snapshot (terminal-only).\n**No** Dict Norm on this path.\n**No** category_id in Sem JSON.\nDefault `next_action=direction_select` (Dir not wired).\nLoad stays `WHERE false`.";
  }

  fs.writeFileSync(WF_PATH, JSON.stringify(wf, null, 2) + "\n", "utf8");
  console.log(`Patched ${WF_PATH}: ${POST} → ${NORM} → ${ROUTE}`);
}

main();
