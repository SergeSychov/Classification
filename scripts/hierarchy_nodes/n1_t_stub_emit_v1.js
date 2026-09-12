/**
 * B4.3B-T N1-T Stub Emit (local mirror; pure; non-n8n).
 * Re-validates G3; throws if not fully armed. Never silent-synthesizes.
 */

"use strict";

const {
  evaluateN1TGate,
  isPlainObject,
} = require("./n1_t_gate_v1.js");

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

/**
 * @param {object} itemJson
 * @returns {object} new json object
 */
function emitN1TStub(itemJson) {
  if (!evaluateN1TGate(itemJson)) {
    throw new Error(
      "N1-T Stub Emit refused: G3 operator lock not fully satisfied (fail-closed; no synthetic Sem)"
    );
  }

  const j = itemJson;
  const existingHint = isPlainObject(j.routing_hint) ? { ...j.routing_hint } : {};
  const existingN1T = isPlainObject(existingHint.n1_t) ? { ...existingHint.n1_t } : {};

  return {
    ...deepClone(j),
    test_mode: "n1_presem_smoke",
    test_synthetic_sem: true,
    test_fixture_version: "n1_presem_stub_v1",
    llm_called: false,
    semantic_validation_passed: true,
    semantic_reject_reason: null,
    semantic_confidence: null,
    semantic_attrs: {},
    attr_mnn: null,
    attr_dosage_form: null,
    attr_administration_route: null,
    decision_status: "pending_fallback",
    next_action: "direction_select",
    selected_category_id: null,
    direction_static: true,
    stage: "direction_select",
    workflow_version: "hierarchy_n1_presem_smoke_v1",
    prompt_version: "test_stub_no_llm_v1",
    routing_hint: {
      ...existingHint,
      n1_t: {
        ...existingN1T,
        test_synthetic_sem: true,
        llm_called: false,
      },
    },
  };
}

module.exports = {
  emitN1TStub,
};
