/**
 * Offline fixture tests for Sem — Post-process (primary S2 gate).
 * Run: node --test scripts/sem_post_process_fixtures.test.mjs
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const POST_PATH = join(__dirname, "hierarchy_nodes", "sem_post_process.js");

function runPostProcess(items) {
  const code = readFileSync(POST_PATH, "utf8");
  const fn = new Function("items", code);
  return fn(items);
}

function baseItem(output) {
  return {
    json: {
      product_id: 1,
      run_id: 99,
      output,
      constants: {
        stage: { semantic_primary: "semantic_primary" },
        decision_status: { pending_fallback: "pending_fallback" },
        next_action: { direction_select: "direction_select" },
        actor_type: { llm: "llm" },
        log_status: {
          success: "success",
          rejected: "rejected",
          needs_review: "needs_review",
        },
        model: { cascade_actor_name: "deepseek-chat" },
      },
      cascade_trace: { path: ["normalize"], stages: [] },
    },
  };
}

function softContinueInvariants(j) {
  assert.equal(j.decision_status, "pending_fallback");
  assert.equal(j.next_action, "direction_select");
  assert.equal(j.selected_category_id, null);
  assert.notEqual(j.decision_status, "classified");
  assert.equal(j.stage, "semantic_primary");
}

test("invalid_json → validation_passed=false, reject invalid_json, soft-continue", () => {
  const [out] = runPostProcess([baseItem("{not-json")]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "invalid_json");
  assert.equal(j.semantic_attrs, null);
  assert.equal(j.log_status, "rejected");
});

test("missing_explanation → validation_passed=false, needs_review, soft-continue", () => {
  const payload = {
    mnn: "ibuprofen",
    brand: null,
    rx_otc: "otc",
    nosology: null,
    administration_route: "oral",
    dosage_form: "tablet",
    dosage: "200 mg",
    age_segment: null,
    package_hint: null,
    combination_hint: null,
    confidence: 0.8,
  };
  const [out] = runPostProcess([baseItem(JSON.stringify(payload))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "missing_explanation");
  assert.equal(j.log_status, "needs_review");
  assert.ok(j.semantic_attrs);
  assert.equal(j.semantic_attrs.mnn, "ibuprofen");
  assert.equal(j.semantic_confidence, 0.8);
  assert.equal(j.semantic_explanation, null);
});

test("nested/partial object with empty explanation → missing_explanation", () => {
  const payload = {
    mnn: null,
    brand: null,
    rx_otc: "unknown",
    nosology: null,
    administration_route: null,
    dosage_form: null,
    dosage: null,
    age_segment: null,
    package_hint: null,
    combination_hint: null,
    confidence: 0.5,
    explanation: "   ",
  };
  const [out] = runPostProcess([baseItem(JSON.stringify(payload))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "missing_explanation");
});

test("forbidden category_id → category_id_forbidden, soft-continue", () => {
  const payload = {
    category_id: 12345,
    confidence: 0.9,
    explanation: "should not classify",
  };
  const [out] = runPostProcess([baseItem(JSON.stringify(payload))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "category_id_forbidden");
  assert.equal(j.semantic_attrs, null);
  assert.equal(j.log_status, "rejected");
});

test("forbidden direction → direction_forbidden, soft-continue", () => {
  const payload = {
    direction: "ЛОР",
    confidence: 0.9,
    explanation: "should not select direction",
  };
  const [out] = runPostProcess([baseItem(JSON.stringify(payload))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "direction_forbidden");
  assert.equal(j.semantic_attrs, null);
});

test("forbidden need → need_forbidden, soft-continue", () => {
  const payload = {
    need: "боль в горле",
    confidence: 0.9,
    explanation: "should not select need",
  };
  const [out] = runPostProcess([baseItem(JSON.stringify(payload))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "need_forbidden");
  assert.equal(j.semantic_attrs, null);
});

test("valid payload → validation_passed=true, soft-continue still", () => {
  const payload = {
    mnn: "paracetamol",
    brand: "Panadol",
    rx_otc: "otc",
    nosology: null,
    administration_route: "oral",
    dosage_form: "tablet",
    dosage: "500 mg",
    age_segment: null,
    package_hint: "12",
    combination_hint: null,
    confidence: 0.91,
    explanation: "explicit analgesic tablet",
  };
  const [out] = runPostProcess([baseItem(JSON.stringify(payload))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, true);
  assert.equal(j.semantic_reject_reason, null);
  assert.equal(j.log_status, "success");
  assert.equal(j.semantic_attrs.mnn, "paracetamol");
  assert.equal(j.semantic_explanation, "explicit analgesic tablet");
});

test("array shape → invalid_shape", () => {
  const [out] = runPostProcess([baseItem(JSON.stringify([{ confidence: 0.5 }]))]);
  const j = out.json;
  softContinueInvariants(j);
  assert.equal(j.semantic_validation_passed, false);
  assert.equal(j.semantic_reject_reason, "invalid_shape");
});
