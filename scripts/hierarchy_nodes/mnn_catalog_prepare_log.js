// Prepare log payload for stage=mnn_catalog_resolve.
// Requires non-null run_id (never insert with run_id=null).

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
  return null;
}

function sqlJson(value) {
  if (value === undefined || value === null || value === '') return null;
  return value;
}

return items.map((item, index) => {
  const j = item.json || {};
  const runId = sqlNumber(j.run_id);
  const stage = 'mnn_catalog_resolve';

  if (runId == null) {
    return {
      json: {
        ...j,
        product_classification_log_insert_mnn_catalog: null,
        mnn_catalog_log_skipped_reason: 'run_id_null_forbidden',
      },
      pairedItem: item.pairedItem ?? { item: index },
    };
  }

  const inputPayload = {
    product_id: sqlNumber(j.product_id),
    run_id: runId,
    normalized_text: sqlText(j.normalized_text),
    catalog_sources: sqlJson(j.source_raw_mnn || j.catalog_mnn_sources),
  };

  const outputPayload = {
    resolved_mnn: sqlText(j.resolved_mnn),
    resolved_mnn_components: sqlJson(j.resolved_mnn_components),
    resolved_mnn_component_stats: sqlJson(j.resolved_mnn_component_stats),
    resolved_mnn_sources: sqlJson(j.resolved_mnn_sources),
    resolved_rx_otc: sqlText(j.resolved_rx_otc),
    resolved_age_segment: sqlText(j.resolved_age_segment),
    mnn_resolution_status: sqlText(j.mnn_resolution_status),
    resolution_reason: sqlText(j.resolution_reason),
    needs_mnn_enrichment: sqlBoolean(j.needs_mnn_enrichment),
    source_raw_mnn: sqlJson(j.source_raw_mnn),
  };

  const validationPassed = j.mnn_resolution_status === 'resolved_catalog';

  const productClassificationLogInsert = {
    run_id: runId,
    product_id: sqlNumber(j.product_id),
    product_raw_id: sqlNumber(j.product_raw_id),
    stage,
    actor_type: 'system',
    actor_name: 'mnn_catalog_consensus_v1',
    status: validationPassed ? 'success' : 'needs_review',
    input_payload: inputPayload,
    output_payload: outputPayload,
    selected_category_id: null,
    validation_passed: validationPassed,
    workflow_version: sqlText(j.workflow_version) || 'mnn_catalog_enrichment_v1',
    prompt_version: sqlText(j.prompt_version) || 'mnn_catalog_consensus_v1',
    decision_status: sqlText(j.decision_status),
    next_action: sqlText(j.next_action),
    routing_hint: sqlJson(j.routing_hint),
  };

  return {
    json: {
      ...j,
      stage,
      product_classification_log_insert_mnn_catalog: productClassificationLogInsert,
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
