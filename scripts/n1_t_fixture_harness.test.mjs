/**
 * B4.3B-T N1-T Gate/Stub + static workflow graph tests.
 * Run: node --test scripts/n1_t_fixture_harness.test.mjs
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const harness = require("./hierarchy_nodes/n1_t_fixture_harness_v1.js");
const casesDoc = JSON.parse(
  readFileSync(join(__dirname, "hierarchy_nodes", "n1_t_fixture_cases_v1.json"), "utf8")
);

const {
  deepClone,
  evaluateN1TGate,
  emitN1TStub,
  defaultUnarmedN1TStamp,
  mergeRoutingHintWithN1T,
  buildArmedItem,
  simulateUnarmedAttachStamp,
  simulateCap,
  simulateAttachFromCap,
} = harness;

function armed(overrides = {}, n1Overrides = null) {
  const base = deepClone(casesDoc.base_armed_item);
  const merged = {
    ...base,
    ...overrides,
    run_meta: {
      ...base.run_meta,
      ...(overrides.run_meta || {}),
    },
    routing_hint: mergeRoutingHintWithN1T(base.routing_hint, {
      ...(n1Overrides || {}),
    }),
  };
  if (overrides.routing_hint) {
    merged.routing_hint = mergeRoutingHintWithN1T(
      mergeRoutingHintWithN1T(base.routing_hint, n1Overrides),
      overrides.routing_hint.n1_t || overrides.routing_hint
    );
    if (overrides.routing_hint.prior_key) {
      merged.routing_hint.prior_key = overrides.routing_hint.prior_key;
    }
  }
  return merged;
}

test("1 missing routing_hint.n1_t → Gate false", () => {
  const j = armed();
  delete j.routing_hint.n1_t;
  assert.equal(evaluateN1TGate(j), false);
});

test("2 default unarmed stamp → Gate false", () => {
  const j = simulateUnarmedAttachStamp(
    {
      product_id: 55,
      product_raw_id: 55,
      product_count: 1,
      run_id: 1,
      run_meta: { requested_batch_size: 1, effective_batch_size: 1 },
    },
    { prior_key: "x" }
  );
  assert.equal(j.routing_hint.n1_t.enabled, false);
  assert.equal(j.routing_hint.n1_t.operator_lock, false);
  assert.equal(j.routing_hint.prior_key, "x");
  assert.equal(evaluateN1TGate(j), false);
});

test("3 enabled but wrong product_id → false", () => {
  const j = armed({}, { product_id: 99 });
  assert.equal(evaluateN1TGate(j), false);
});

test("4 correct product id but wrong product_raw_id → false", () => {
  const j = armed({ product_raw_id: 56 });
  assert.equal(evaluateN1TGate(j), false);
});

test("5 batch sizes not exactly 1 → false", () => {
  const j = armed(
    {
      requested_batch_size: 5,
      effective_batch_size: 5,
      run_meta: { requested_batch_size: 5, effective_batch_size: 5 },
    },
    { requested_batch_size: 5, effective_batch_size: 5 }
  );
  assert.equal(evaluateN1TGate(j), false);
});

test("6 workflow id mismatch → false", () => {
  const j = armed({}, { workflow_id: "wrong" });
  assert.equal(evaluateN1TGate(j), false);
});

test("7 fixture mismatch → false", () => {
  const j = armed({}, { fixture_version: "other" });
  assert.equal(evaluateN1TGate(j), false);
});

test("8 invalid/missing run_id → false", () => {
  const j = armed({ run_id: null });
  assert.equal(evaluateN1TGate(j), false);
  const j2 = armed({ run_id: "x" });
  assert.equal(evaluateN1TGate(j2), false);
});

test("9 missing/unproven product_count=1 → false", () => {
  const j = armed();
  delete j.product_count;
  assert.equal(evaluateN1TGate(j), false);
  const j2 = armed({ product_count: 2 });
  assert.equal(evaluateN1TGate(j2), false);
});

test("10 real Sem marker → false", () => {
  assert.equal(evaluateN1TGate(armed({ prompt_version: "prompt_semantic_v3" })), false);
  assert.equal(evaluateN1TGate(armed({ llm_raw_output_text: "{}" })), false);
  assert.equal(evaluateN1TGate(armed({ output: { a: 1 } })), false);
  assert.equal(evaluateN1TGate(armed({ stage: "semantic_primary" })), false);
});

test("11 fully armed valid fixture → Gate true", () => {
  assert.equal(evaluateN1TGate(armed()), true);
});

test("12 Stub preserves context and prior routing_hint keys", () => {
  const input = armed();
  const out = emitN1TStub(input);
  assert.equal(out.run_id, 9001);
  assert.equal(out.product_id, 55);
  assert.equal(out.product_raw_id, 55);
  assert.equal(out.combined_text, input.combined_text);
  assert.deepEqual(out.run_meta, input.run_meta);
  assert.equal(out.routing_hint.prior_key, "keep-me");
  assert.equal(out.requested_batch_size, 1);
  assert.equal(out.effective_batch_size, 1);
});

test("13 Stub emits no final fields / no invented real semantic fields", () => {
  const out = emitN1TStub(armed());
  assert.equal(out.selected_category_id, null);
  assert.equal(out.attr_mnn, null);
  assert.equal(out.attr_dosage_form, null);
  assert.equal(out.attr_administration_route, null);
  assert.deepEqual(out.semantic_attrs, {});
  assert.equal(out.decision_status, "pending_fallback");
  assert.equal(out.next_action, "direction_select");
  assert.equal(out.final_category_id, undefined);
  assert.equal(out.final_source, undefined);
  assert.equal(out.final_confidence, undefined);
  assert.equal(out.final_explanation, undefined);
  assert.equal(out.llm_called, false);
  assert.equal(out.test_synthetic_sem, true);
  assert.equal(out.prompt_version, "test_stub_no_llm_v1");
});

test("14 product 26346 never passes Gate", () => {
  const j = armed(
    { product_id: 26346, product_raw_id: 26346 },
    { product_id: 26346, product_raw_id: 26346 }
  );
  assert.equal(evaluateN1TGate(j), false);
});

test("15 Stub with invalid item throws and returns no object", () => {
  assert.throws(() => emitN1TStub(armed({ product_id: 1 })), /refused/);
  assert.throws(() => emitN1TStub(simulateUnarmedAttachStamp({ product_id: 55 }, null)), /refused/);
});

test("16 static graph: Limit→Gate Eval→Gate IF→false→Sem0; true→Stub→Sem Route", () => {
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  const limitOut = wf.connections["Load — Limit Batch"].main[0];
  assert.equal(limitOut.length, 1);
  assert.equal(limitOut[0].node, "N1-T — Gate Eval");

  const evalOut = wf.connections["N1-T — Gate Eval"].main[0];
  assert.equal(evalOut.length, 1);
  assert.equal(evalOut[0].node, "N1-T — Gate IF");

  const gate = wf.connections["N1-T — Gate IF"].main;
  // [0]=true, [1]=false for n8n IF 2.2
  assert.equal(gate[0][0].node, "N1-T — Stub Emit");
  assert.equal(gate[1][0].node, "Sem0 — Build Prompt");

  const stubOut = wf.connections["N1-T — Stub Emit"].main[0];
  assert.equal(stubOut.length, 1);
  assert.equal(stubOut[0].node, "Sem — Route");

  // no direct Limit→Sem0
  assert.ok(!limitOut.some((c) => c.node === "Sem0 — Build Prompt"));
});

test("17 static graph: true branch cannot reach Snapshot/Upsert or Sem AI Agents", () => {
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  const nodesByName = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
  assert.ok(nodesByName["N1-T — Stub Emit"]);
  assert.ok(nodesByName["N1-T — Gate IF"]);

  // BFS from Stub
  const blocked = new Set([
    "Sem0 — AI Agent",
    "Sem — AI Agent",
    "Sem0 — DeepSeek",
    "Sem — DeepSeek",
    "DB — Prepare Snapshot",
    "DB — Upsert Snapshot",
  ]);
  const seen = new Set();
  const q = ["N1-T — Stub Emit"];
  while (q.length) {
    const cur = q.shift();
    if (seen.has(cur)) continue;
    seen.add(cur);
    assert.ok(!blocked.has(cur), `true branch reached ${cur}`);
    const conn = wf.connections[cur];
    if (!conn || !conn.main) continue;
    for (const outs of conn.main) {
      for (const edge of outs || []) {
        q.push(edge.node);
      }
    }
  }
  assert.ok(seen.has("Sem — Route"));
  assert.ok(seen.has("Dir — Candidate Builder"));
  assert.ok(seen.has("Sem — Prepare Log"));
  assert.ok(seen.has("DB — Insert Log"));
  assert.ok(seen.has("Fin — Close Run"));
});

test("18 live Load restored to B2 WHERE false stub (Action 2 containment)", () => {
  const rollback =
    "-- B2 skeleton stub: never drain pending pool\nSELECT\n  NULL::bigint AS product_id,\n  NULL::bigint AS product_raw_id\nWHERE false;";
  assert.equal(casesDoc.safe_load_sql, rollback);
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  const load = wf.nodes.find((n) => n.name === "Load — Select Batch");
  assert.equal(load.parameters.query, casesDoc.safe_load_sql);
  assert.match(load.parameters.query, /WHERE false;/);
});

test("19 Sem0/Sem1 prompt authority unchanged", () => {
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  const by = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
  assert.match(by["Sem0 — LLM Prepare"].parameters.jsCode, /prompt_sem0_v2/);
  assert.match(by["Sem — LLM Prepare"].parameters.jsCode, /prompt_semantic_v3/);
  assert.match(by["Sem0 — Post-process"].parameters.jsCode, /prompt_sem0_v2/);
  assert.match(by["Sem — Post-process"].parameters.jsCode, /prompt_semantic_v3/);
});

test("20 single-close: no Gate/Stub direct to Close; Insert Log → Barrier[1]", () => {
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  for (const name of ["N1-T — Gate IF", "N1-T — Stub Emit"]) {
    const conn = wf.connections[name];
    if (!conn) continue;
    for (const outs of conn.main || []) {
      for (const edge of outs || []) {
        assert.notEqual(edge.node, "Fin — Close Run");
        assert.notEqual(edge.node, "Fin — Pick Run");
        assert.notEqual(edge.node, "DB — Upsert Snapshot");
        assert.notEqual(edge.node, "Shell — Ensure Empty Fin");
      }
    }
  }
  const insert = wf.connections["DB — Insert Log"].main[0][0];
  assert.equal(insert.node, "Fin — Merge Barrier");
  assert.equal(insert.index, 1);
});

test("sidecar workflow id unchanged", () => {
  const id = readFileSync(
    join(ROOT, "workflows/classification-stage2-hierarchy-dev.id"),
    "utf8"
  ).trim();
  assert.equal(id, "o8sugljHYuUs7IEC");
});

test("Cap still max 10 / default 5; one-shot arm constant disarmed", () => {
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  const cap = wf.nodes.find((n) => n.name === "Run — Apply Batch Cap").parameters.jsCode;
  assert.match(cap, /MAX_LIVE_LLM_BATCH = 10/);
  assert.match(cap, /DEFAULT_LIVE_LLM_BATCH = 5/);
  assert.match(cap, /const N1_T_ONE_SHOT_ARMED = false/);
  assert.doesNotMatch(cap, /const N1_T_ONE_SHOT_ARMED = true/);
  assert.match(cap, /MUST be restored to false/);
});

test("defaultUnarmed stamp shape", () => {
  const s = defaultUnarmedN1TStamp();
  assert.equal(s.enabled, false);
  assert.equal(s.operator_lock, false);
  assert.equal(s.product_id, 55);
  assert.equal(s.workflow_id, "o8sugljHYuUs7IEC");
  assert.equal(s.load_mode, "mode_c_exact_id");
});

test("buildArmedItem helper", () => {
  const j = buildArmedItem(
    { product_id: 55, product_raw_id: 55, product_count: 1, run_id: 1, run_meta: { requested_batch_size: 1, effective_batch_size: 1 }, requested_batch_size: 1, effective_batch_size: 1 },
    null
  );
  assert.equal(evaluateN1TGate(j), true);
});

test("one-shot Cap armed: batch=1 and full G3 stamp", () => {
  const cap = simulateCap({}, true);
  assert.equal(cap.requested_batch_size, 1);
  assert.equal(cap.effective_batch_size, 1);
  assert.equal(cap.batch_size, 1);
  assert.equal(cap.routing_hint.n1_t.enabled, true);
  assert.equal(cap.routing_hint.n1_t.operator_lock, true);
  assert.equal(cap.routing_hint.n1_t.requested_batch_size, 1);
  assert.equal(cap.routing_hint.n1_t.effective_batch_size, 1);
});

test("one-shot Cap unarmed: default effective 5 and G3 false", () => {
  const cap = simulateCap({}, false);
  assert.equal(cap.requested_batch_size, null);
  assert.equal(cap.effective_batch_size, 5);
  assert.equal(cap.batch_size, 5);
  assert.equal(cap.routing_hint.n1_t.enabled, false);
  assert.equal(cap.routing_hint.n1_t.operator_lock, false);
});

test("Attach+Gate+Stub: armed Mode C item passes Gate and Stub", () => {
  const cap = simulateCap({}, true);
  const item = simulateAttachFromCap(
    {
      product_id: 55,
      product_raw_id: 55,
      product_count: 1,
      combined_text: "БИСОМОР",
    },
    cap,
    9001,
    true
  );
  assert.equal(item.run_id, 9001);
  assert.equal(item.run_meta.requested_batch_size, 1);
  assert.equal(item.run_meta.effective_batch_size, 1);
  assert.equal(item.routing_hint.n1_t.enabled, true);
  assert.equal(evaluateN1TGate(item), true);
  const out = emitN1TStub(item);
  assert.equal(out.next_action, "direction_select");
  assert.equal(out.test_synthetic_sem, true);
  assert.equal(out.selected_category_id, null);
  assert.equal(out.final_category_id, undefined);
  assert.deepEqual(out.semantic_attrs, {});
});

test("operator_lock false with enabled true → Gate false", () => {
  const j = armed({}, { operator_lock: false });
  assert.equal(evaluateN1TGate(j), false);
});

test("workflow Cap/Init/Attach all declare N1_T_ONE_SHOT_ARMED = false", () => {
  const wf = JSON.parse(
    readFileSync(join(ROOT, "workflows/classification-stage2-hierarchy-dev.json"), "utf8")
  );
  for (const name of [
    "Run — Apply Batch Cap",
    "Run — Init Constants",
    "Load — Attach Run ID",
  ]) {
    const code = wf.nodes.find((n) => n.name === name).parameters.jsCode;
    assert.match(code, /const N1_T_ONE_SHOT_ARMED = false/);
    assert.doesNotMatch(code, /const N1_T_ONE_SHOT_ARMED = true/);
  }
});
