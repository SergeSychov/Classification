/**
 * B4.3B-T N1-T fixture harness (local, pure, non-n8n).
 */

"use strict";

const {
  evaluateN1TGate,
  defaultUnarmedN1TStamp,
  mergeRoutingHintWithN1T,
  isPlainObject,
} = require("./n1_t_gate_v1.js");
const { emitN1TStub } = require("./n1_t_stub_emit_v1.js");

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function buildArmedItem(base, n1Overrides) {
  const j = deepClone(base);
  j.routing_hint = mergeRoutingHintWithN1T(j.routing_hint, {
    ...defaultUnarmedN1TStamp(),
    enabled: true,
    operator_lock: true,
    requested_batch_size: 1,
    effective_batch_size: 1,
    ...(n1Overrides || {}),
  });
  return j;
}

/**
 * Simulate Cap default stamp + Attach re-merge for an unarmed product item.
 */
function simulateUnarmedAttachStamp(productItem, priorHint) {
  const j = deepClone(productItem);
  const capStamp = defaultUnarmedN1TStamp();
  j.routing_hint = mergeRoutingHintWithN1T(
    mergeRoutingHintWithN1T(priorHint, null),
    capStamp
  );
  j.routing_hint.n1_t.enabled = false;
  j.routing_hint.n1_t.operator_lock = false;
  return j;
}

/**
 * Pure simulation of Cap one-shot arming branch (mirrors workflow Cap logic).
 */
function simulateCap(inputJson, oneShotArmed) {
  const MAX_LIVE_LLM_BATCH = 10;
  const DEFAULT_LIVE_LLM_BATCH = 5;
  const j = deepClone(inputJson || {});
  function parseRequested(v) {
    if (v === undefined || v === null || v === "") return null;
    if (typeof v === "number" && Number.isFinite(v) && Number.isInteger(v) && v > 0) {
      return v;
    }
    return null;
  }
  const raw =
    j.requested_batch_size !== undefined
      ? j.requested_batch_size
      : j.batch_size !== undefined
        ? j.batch_size
        : j.body && j.body.batch_size;
  let requested = parseRequested(raw);
  let effective =
    requested == null ? DEFAULT_LIVE_LLM_BATCH : Math.min(requested, MAX_LIVE_LLM_BATCH);
  const prevHint = isPlainObject(j.routing_hint) ? j.routing_hint : {};
  const prevN1 = isPlainObject(prevHint.n1_t) ? prevHint.n1_t : {};
  let n1_t;
  if (oneShotArmed === true) {
    requested = 1;
    effective = 1;
    n1_t = {
      ...prevN1,
      enabled: true,
      operator_lock: true,
      product_id: 55,
      product_raw_id: 55,
      requested_batch_size: 1,
      effective_batch_size: 1,
      fixture_version: "n1_presem_stub_v1",
      workflow_id: "o8sugljHYuUs7IEC",
      load_mode: "mode_c_exact_id",
      test_mode: "n1_presem_smoke",
      test_synthetic_sem: false,
      llm_called: null,
    };
  } else {
    n1_t = {
      ...defaultUnarmedN1TStamp(),
      ...prevN1,
      enabled: false,
      operator_lock: false,
    };
  }
  return {
    ...j,
    requested_batch_size: requested,
    effective_batch_size: effective,
    batch_size: effective,
    batch_cap_version: "live_llm_batch_cap_v1",
    routing_hint: { ...prevHint, n1_t },
  };
}

/**
 * Simulate Attach re-attach from Cap onto a Mode C product row.
 */
function simulateAttachFromCap(productItem, capJson, runId, oneShotArmed) {
  const j = deepClone(productItem || {});
  const cap = deepClone(capJson || {});
  const prevHint = isPlainObject(j.routing_hint) ? j.routing_hint : {};
  const capHint = isPlainObject(cap.routing_hint) ? cap.routing_hint : {};
  const merged = { ...capHint, ...prevHint };
  const prevN1 = isPlainObject(merged.n1_t) ? merged.n1_t : {};
  let n1_t;
  let requestedMeta = cap.requested_batch_size ?? null;
  let effectiveMeta = cap.effective_batch_size ?? 5;
  if (oneShotArmed === true) {
    requestedMeta = 1;
    effectiveMeta = 1;
    n1_t = {
      ...prevN1,
      enabled: true,
      operator_lock: true,
      product_id: 55,
      product_raw_id: 55,
      requested_batch_size: 1,
      effective_batch_size: 1,
      fixture_version: "n1_presem_stub_v1",
      workflow_id: "o8sugljHYuUs7IEC",
      load_mode: "mode_c_exact_id",
      test_mode: "n1_presem_smoke",
      test_synthetic_sem: false,
      llm_called: null,
    };
  } else {
    n1_t = {
      ...defaultUnarmedN1TStamp(),
      ...prevN1,
      enabled: false,
      operator_lock: false,
    };
  }
  return {
    ...j,
    run_id: runId,
    run_meta: {
      requested_batch_size: requestedMeta,
      effective_batch_size: effectiveMeta,
      batch_cap_version: cap.batch_cap_version || "live_llm_batch_cap_v1",
    },
    routing_hint: { ...merged, n1_t },
  };
}

module.exports = {
  deepClone,
  isPlainObject,
  evaluateN1TGate,
  emitN1TStub,
  defaultUnarmedN1TStamp,
  mergeRoutingHintWithN1T,
  buildArmedItem,
  simulateUnarmedAttachStamp,
  simulateCap,
  simulateAttachFromCap,
};
