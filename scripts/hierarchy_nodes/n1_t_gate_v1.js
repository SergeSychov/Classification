/**
 * B4.3B-T N1-T Gate predicate (local mirror; pure; non-n8n).
 * Fail-closed: any missing/malformed/inconsistent proof → false.
 */

"use strict";

const EXPECTED_PRODUCT_ID = 55;
const EXPECTED_PRODUCT_RAW_ID = 55;
const EXPECTED_WORKFLOW_ID = "o8sugljHYuUs7IEC";
const EXPECTED_FIXTURE_VERSION = "n1_presem_stub_v1";
const EXPECTED_LOAD_MODE = "mode_c_exact_id";

const REAL_SEM_PROMPT_VERSIONS = new Set([
  "prompt_sem0_v2",
  "prompt_semantic_v3",
  "prompt_semantic_v2",
]);

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function strictTrue(value) {
  return value === true;
}

function strictNumEq(value, expected) {
  return typeof value === "number" && Number.isFinite(value) && value === expected;
}

function coerceFiniteNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function hasOwn(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

/**
 * Conservative evidence of a prior real Sem/LLM pass on this item.
 * Uncertain / unexpected markers fail closed (return true = blocked).
 */
function hasRealSemOrLlmEvidence(j) {
  if (!isPlainObject(j)) return true;

  if (j.llm_called === true) return true;
  if (typeof j.llm_raw_output_text === "string" && j.llm_raw_output_text.trim() !== "") {
    return true;
  }
  if (j.output !== undefined && j.output !== null && j.output !== "") return true;
  if (j.text !== undefined && j.text !== null && j.text !== "") {
    // Agent text channel; only block when not clearly our stub path
    if (j.test_synthetic_sem !== true) return true;
  }
  if (j.response !== undefined && j.response !== null && j.response !== "") return true;

  if (typeof j.prompt_version === "string" && REAL_SEM_PROMPT_VERSIONS.has(j.prompt_version)) {
    return true;
  }

  if (j.stage === "semantic_primary" || j.stage === "product_kind_select") {
    return true;
  }

  if (j.semantic_raw_json !== undefined && j.semantic_raw_json !== null) return true;

  const n1 = isPlainObject(j.routing_hint) && isPlainObject(j.routing_hint.n1_t)
    ? j.routing_hint.n1_t
    : null;
  if (n1 && n1.llm_called === true) return true;
  if (n1 && n1.test_synthetic_sem === true && j.test_synthetic_sem !== true) {
    // inconsistent synthetic markers
    return true;
  }

  return false;
}

function readBatchPair(j, n1) {
  const requestedFromStamp = n1.requested_batch_size;
  const effectiveFromStamp = n1.effective_batch_size;

  const meta = isPlainObject(j.run_meta) ? j.run_meta : {};
  const requestedFromItem =
    hasOwn(j, "requested_batch_size") && j.requested_batch_size !== undefined
      ? j.requested_batch_size
      : meta.requested_batch_size;
  const effectiveFromItem =
    hasOwn(j, "effective_batch_size") && j.effective_batch_size !== undefined
      ? j.effective_batch_size
      : meta.effective_batch_size !== undefined
        ? meta.effective_batch_size
        : j.batch_size;

  return {
    stampRequested: requestedFromStamp,
    stampEffective: effectiveFromStamp,
    itemRequested: requestedFromItem,
    itemEffective: effectiveFromItem,
  };
}

/**
 * @param {object} itemJson
 * @returns {boolean}
 */
function evaluateN1TGate(itemJson) {
  const j = itemJson;
  if (!isPlainObject(j)) return false;

  const hint = j.routing_hint;
  if (!isPlainObject(hint)) return false;
  const n1 = hint.n1_t;
  if (!isPlainObject(n1)) return false;

  if (!strictTrue(n1.enabled)) return false;
  if (!strictTrue(n1.operator_lock)) return false;

  if (!strictNumEq(n1.product_id, EXPECTED_PRODUCT_ID)) return false;
  if (!strictNumEq(n1.product_raw_id, EXPECTED_PRODUCT_RAW_ID)) return false;

  if (!strictNumEq(coerceFiniteNumber(j.product_id), EXPECTED_PRODUCT_ID)) return false;
  if (!strictNumEq(coerceFiniteNumber(j.product_raw_id), EXPECTED_PRODUCT_RAW_ID)) {
    return false;
  }

  if (!strictNumEq(n1.requested_batch_size, 1)) return false;
  if (!strictNumEq(n1.effective_batch_size, 1)) return false;

  const batches = readBatchPair(j, n1);
  if (!strictNumEq(coerceFiniteNumber(batches.itemRequested), 1)) return false;
  if (!strictNumEq(coerceFiniteNumber(batches.itemEffective), 1)) return false;

  if (n1.workflow_id !== EXPECTED_WORKFLOW_ID) return false;
  if (n1.fixture_version !== EXPECTED_FIXTURE_VERSION) return false;
  if (n1.load_mode !== EXPECTED_LOAD_MODE) return false;

  const runId = coerceFiniteNumber(j.run_id);
  if (runId === null) return false;

  // product_count must be proven === 1; missing → fail closed
  if (!strictNumEq(coerceFiniteNumber(j.product_count), 1)) return false;

  if (hasRealSemOrLlmEvidence(j)) return false;

  return true;
}

function defaultUnarmedN1TStamp(overrides) {
  return {
    enabled: false,
    operator_lock: false,
    product_id: EXPECTED_PRODUCT_ID,
    product_raw_id: EXPECTED_PRODUCT_RAW_ID,
    requested_batch_size: null,
    effective_batch_size: null,
    fixture_version: EXPECTED_FIXTURE_VERSION,
    workflow_id: EXPECTED_WORKFLOW_ID,
    load_mode: EXPECTED_LOAD_MODE,
    test_mode: "n1_presem_smoke",
    test_synthetic_sem: false,
    llm_called: null,
    ...(isPlainObject(overrides) ? overrides : {}),
  };
}

function mergeRoutingHintWithN1T(existingHint, n1t) {
  const base = isPlainObject(existingHint) ? { ...existingHint } : {};
  const prevN1 = isPlainObject(base.n1_t) ? base.n1_t : {};
  base.n1_t = {
    ...defaultUnarmedN1TStamp(),
    ...prevN1,
    ...(isPlainObject(n1t) ? n1t : {}),
  };
  return base;
}

module.exports = {
  EXPECTED_PRODUCT_ID,
  EXPECTED_PRODUCT_RAW_ID,
  EXPECTED_WORKFLOW_ID,
  EXPECTED_FIXTURE_VERSION,
  EXPECTED_LOAD_MODE,
  evaluateN1TGate,
  hasRealSemOrLlmEvidence,
  defaultUnarmedN1TStamp,
  mergeRoutingHintWithN1T,
  isPlainObject,
};
