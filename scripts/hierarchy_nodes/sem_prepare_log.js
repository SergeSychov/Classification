// Sem — Prepare Log (hierarchy-specific, B3 Sem).
// stage=semantic_primary; selected_category_id=null;
// decision_status=pending_fallback; next_action=direction_select.
// Does NOT prepare snapshot upsert.

function sqlText(value) {
  if (value === undefined || value === null) return null;
  const s = String(value).trim();
  return s === '' ? null : s;
}

function sqlNumber(value) {
  if (value === undefined || value === null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function sqlBoolean(value) {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const v = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y'].includes(v)) return true;
    if (['false', '0', 'no', 'n'].includes(v)) return false;
  }
  return null;
}

function sqlJson(value) {
  if (value === undefined || value === null || value === '') return null;
  return value;
}

return items.map((item, index) => {
  const j = item.json || {};
  const C = j.constants || {};

  const stage =
    sqlText(j.stage) ||
    (C.stage && C.stage.semantic_primary) ||
    'semantic_primary';
  const decisionStatus =
    sqlText(j.decision_status) ||
    (C.decision_status && C.decision_status.pending_fallback) ||
    'pending_fallback';
  const nextAction =
    sqlText(j.next_action) ||
    (C.next_action && C.next_action.direction_select) ||
    'direction_select';
  const actorType = sqlText(j.actor_type) || 'llm';
  const actorName = sqlText(j.actor_name) || 'deepseek-chat';
  const workflowVersion = sqlText(j.workflow_version) || 'stage2_hierarchy_v1';
  const promptVersion = sqlText(j.prompt_version) || 'prompt_semantic_v1';

  const inputPayload = {
    product_id: sqlNumber(j.product_id),
    product_raw_id: sqlNumber(j.product_raw_id),
    run_id: sqlNumber(j.run_id),
    stage,
    workflow_version: workflowVersion,
    prompt_version: promptVersion,
    normalized_text: sqlText(j.normalized_text),
    combined_text: sqlText(j.combined_text),
    normalize_meta: sqlJson(j.normalize_meta),
    norm_warnings: sqlJson(j.norm_warnings),
    norm_mnn_product: sqlText(j.norm_mnn_product),
    product_type_guess: sqlText(j.product_type_guess),
    rule_top_category_id: sqlNumber(j.rule_top_category_id),
    rule_top_score: sqlNumber(j.rule_top_score),
    shortlist_json: sqlJson(j.shortlist_json),
  };

  const outputPayload = {
    semantic_attrs: sqlJson(j.semantic_attrs),
    semantic_confidence: sqlNumber(j.semantic_confidence),
    semantic_explanation: sqlText(j.semantic_explanation),
    semantic_raw_json: sqlJson(j.semantic_raw_json),
    semantic_validation_passed: sqlBoolean(j.semantic_validation_passed),
    semantic_reject_reason: sqlText(j.semantic_reject_reason),
    selected_category_id: null,
    decision_status: decisionStatus,
    next_action: nextAction,
    routing_hint: sqlJson(j.routing_hint),
    cascade_trace: sqlJson(j.cascade_trace),
  };

  const status =
    sqlText(j.log_status) ||
    (j.semantic_validation_passed === true
      ? 'success'
      : j.semantic_reject_reason
        ? 'rejected'
        : 'needs_review');

  const productClassificationLogInsert = {
    run_id: sqlNumber(j.run_id),
    product_id: sqlNumber(j.product_id),
    product_raw_id: sqlNumber(j.product_raw_id),
    stage,
    actor_type: actorType,
    actor_name: actorName,
    status,
    input_payload: sqlJson(inputPayload),
    output_payload: sqlJson(outputPayload),
    selected_category_id: null,
    confidence: sqlNumber(j.semantic_confidence),
    explanation: sqlText(j.semantic_explanation),
    validation_passed: sqlBoolean(j.semantic_validation_passed),
    error_message: sqlText(j.semantic_reject_reason),
    workflow_version: workflowVersion,
    prompt_version: promptVersion,
    decision_status: decisionStatus,
    next_action: nextAction,
    routing_hint: sqlJson(j.routing_hint),
  };

  return {
    json: {
      ...j,
      stage,
      decision_status: decisionStatus,
      next_action: nextAction,
      selected_category_id: null,
      product_classification_log_insert: productClassificationLogInsert,
    },
    pairedItem: { item: index },
  };
});
