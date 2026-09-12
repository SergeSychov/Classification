/**
 * B4.3B-T Mode C Load SQL static checks (hermetic; no DB/n8n).
 * Run: node --test scripts/mode_c_load_static.test.mjs
 */

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const ROLLBACK_SQL =
  "-- B2 skeleton stub: never drain pending pool\nSELECT\n  NULL::bigint AS product_id,\n  NULL::bigint AS product_raw_id\nWHERE false;";

const MODE_C_SQL =
  "-- B4.3B-T Mode C temporary exact-ID Load — product 55 only\n-- TEST-ONLY local patch; no settings/allowlist; separate rollback required\nSELECT\n  p.product_id,\n  p.product_raw_id,\n  p.rule_top_category_id,\n  p.rule_top_score,\n  p.rule_shortlist_id,\n  p.rule_decision_status,\n  p.decision_status,\n  s.product_type_guess,\n  s.shortlist_count,\n  s.shortlist_json,\n  s.combined_text\nFROM product_classification AS p\nJOIN classification_shortlist AS s\n  ON s.product_id = p.product_id\nWHERE p.product_id = 55\n  AND p.product_raw_id = 55\n  AND p.decision_status IN ('pending', 'needs_human_review')\n  AND p.rule_decision_status IN ('needs_llm', 'no_match')\n  AND (s.stage IS NULL OR s.stage = 'primary_rules')\n  AND COALESCE(s.combined_text, '') <> ''\nORDER BY p.product_id, s.id\nLIMIT 1;";

const T1_NODE_IDS = {
  "N1-T — Gate Eval": "450f46d1-b7aa-46b3-9f7a-8fac9cd037cd",
  "N1-T — Gate IF": "87144f6f-f53d-4edb-b7ab-8a89d3156ddc",
  "N1-T — Stub Emit": "5dfd6765-2530-40d8-b8f7-07c5597130a3",
};

function loadWf() {
  return JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
}

function sha(s) {
  return createHash("sha256").update(s).digest("hex");
}

test("1 Load node id/name unchanged; query equals B2 WHERE false stub", () => {
  const wf = loadWf();
  const load = wf.nodes.find((n) => n.name === "Load — Select Batch");
  assert.equal(load.id, "fd82e788-b629-4698-b558-1c47e1aac90a");
  assert.equal(load.type, "n8n-nodes-base.postgres");
  assert.equal(load.alwaysOutputData, true);
  assert.equal(load.parameters.operation, "executeQuery");
  assert.equal(load.parameters.query, ROLLBACK_SQL);
  assert.notEqual(load.parameters.query, MODE_C_SQL);
});

test("2 T1 graph retained; Cap/Init/Attach one-shot disarmed; Load stubbed", () => {
  const wf = loadWf();
  assert.ok(wf.nodes.length === 94 || wf.nodes.length === 95); // + optional armed sticky
  assert.equal("active" in wf, false);
  const by = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
  for (const [name, id] of Object.entries(T1_NODE_IDS)) {
    assert.equal(by[name].id, id);
  }
  for (const name of [
    "Run — Apply Batch Cap",
    "Run — Init Constants",
    "Load — Attach Run ID",
  ]) {
    const code = by[name].parameters.jsCode;
    // Emergency containment: G3 disarmed (ONE_SHOT false); armed branch text may remain.
    assert.match(code, /const N1_T_ONE_SHOT_ARMED = false/);
    assert.doesNotMatch(code, /const N1_T_ONE_SHOT_ARMED = true/);
    assert.match(code, /enabled:\s*false/);
    assert.match(code, /operator_lock:\s*false/);
  }
  assert.equal(by["Load — Select Batch"].parameters.query, ROLLBACK_SQL);
  assert.equal(
    wf.connections["Load — Limit Batch"].main[0][0].node,
    "N1-T — Gate Eval"
  );
  assert.equal(
    wf.connections["N1-T — Gate IF"].main[0][0].node,
    "N1-T — Stub Emit"
  );
  assert.equal(
    wf.connections["N1-T — Gate IF"].main[1][0].node,
    "Sem0 — Build Prompt"
  );
});

test("3 single SELECT; no write keywords / multi-statement", () => {
  const q = MODE_C_SQL;
  assert.equal((q.match(/\bSELECT\b/gi) || []).length, 1);
  const forbidden =
    /\b(INSERT|UPDATE|DELETE|MERGE|ALTER|CREATE|DROP|TRUNCATE|COPY|CALL|DO|SELECT\s+INTO|FOR\s+UPDATE|UNION)\b/i;
  assert.doesNotMatch(q, forbidden);
  assert.equal(q.trim().endsWith(";"), true);
  // Strip SQL line comments before checking for extra statement terminators
  const noComments = q
    .split("\n")
    .map((line) => line.replace(/--.*$/, ""))
    .join("\n");
  const body = noComments.trim().replace(/;$/, "");
  assert.equal(body.includes(";"), false);
});

test("4 exact id guards", () => {
  assert.match(MODE_C_SQL, /p\.product_id = 55/);
  assert.match(MODE_C_SQL, /p\.product_raw_id = 55/);
});

test("5 hard LIMIT 1", () => {
  assert.match(MODE_C_SQL, /\nLIMIT 1;/);
  assert.doesNotMatch(MODE_C_SQL, /\{\{/);
  assert.doesNotMatch(MODE_C_SQL, /\$json/);
  assert.doesNotMatch(MODE_C_SQL, /\$\(/);
});

test("6 required shortlist join", () => {
  assert.match(
    MODE_C_SQL,
    /JOIN classification_shortlist AS s\n  ON s\.product_id = p\.product_id/
  );
});

test("7 required row fields present", () => {
  for (const col of [
    "p.product_id",
    "p.product_raw_id",
    "p.rule_top_category_id",
    "p.rule_top_score",
    "p.rule_shortlist_id",
    "p.rule_decision_status",
    "p.decision_status",
    "s.product_type_guess",
    "s.shortlist_count",
    "s.shortlist_json",
    "s.combined_text",
  ]) {
    assert.ok(MODE_C_SQL.includes(col), col);
  }
});

test("8 no settings/allowlist/dynamic/non-55 predicates", () => {
  const q = MODE_C_SQL;
  for (const bad of [
    "pipeline_settings",
    "hierarchy_experiment_enabled",
    "hierarchy_product_allowlist",
    "{{",
    "$json",
    "$(",
  ]) {
    assert.equal(q.includes(bad), false, bad);
  }
  assert.doesNotMatch(q, /\brandom\b/i);
  assert.doesNotMatch(q, /\boffset\b/i);
  assert.doesNotMatch(q, /LIMIT\s+\{\{/);
  // No non-55 product_id equality predicates
  const idEq = [...q.matchAll(/product_id\s*=\s*(\d+)/g)].map((m) => m[1]);
  assert.ok(idEq.length >= 1);
  assert.ok(idEq.every((v) => v === "55"));
  const rawEq = [...q.matchAll(/product_raw_id\s*=\s*(\d+)/g)].map((m) => m[1]);
  assert.ok(rawEq.every((v) => v === "55"));
});

test("9 live Load equals rollback stub after Action 2 containment", () => {
  assert.equal(
    ROLLBACK_SQL,
    "-- B2 skeleton stub: never drain pending pool\nSELECT\n  NULL::bigint AS product_id,\n  NULL::bigint AS product_raw_id\nWHERE false;"
  );
  const live = loadWf().nodes.find((n) => n.name === "Load — Select Batch")
    .parameters.query;
  assert.equal(live, ROLLBACK_SQL);
  assert.notEqual(live, MODE_C_SQL);
});

test("10 prompt authority unchanged", () => {
  const wf = loadWf();
  const by = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
  assert.match(by["Sem0 — LLM Prepare"].parameters.jsCode, /prompt_sem0_v2/);
  assert.match(by["Sem — LLM Prepare"].parameters.jsCode, /prompt_semantic_v3/);
});

test("11 sidecar id unchanged", () => {
  const id = readFileSync(
    join(ROOT, "workflows/classification-stage2-hierarchy-dev.id"),
    "utf8"
  ).trim();
  assert.equal(id, "o8sugljHYuUs7IEC");
});

test("12 live Load query SHA equals rollback stub SHA", () => {
  const live = loadWf().nodes.find((n) => n.name === "Load — Select Batch")
    .parameters.query;
  assert.equal(sha(live), sha(ROLLBACK_SQL));
  assert.notEqual(sha(live), sha(MODE_C_SQL));
});
