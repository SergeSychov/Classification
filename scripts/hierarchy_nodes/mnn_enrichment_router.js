// MNN — Enrichment Router (hierarchy mirror).
// Calls are performed by HTTP node; this Code node maps response + gates.
// Body for webhook: { product: normalized_text }
// Preserve pairedItem; do not rewrite attr_*.

function normalizeRx(raw) {
  const t = String(raw || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .trim();
  if (!t) return 'unknown';
  if (/без\s*рецепт|безрецептур|\botc\b/.test(t) || t === 'otc') return 'otc';
  if (/по\s+рецепту|рецептурн|\brx\b/.test(t) || t === 'rx') return 'rx';
  if (/not\s*applicable|не\s*применимо/.test(t)) return 'unknown';
  return 'unknown';
}

function normalizeAge(raw) {
  const t = String(raw || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .trim();
  if (!t) return 'unknown';
  if (/универсал/.test(t)) return 'универсальный';
  if (/детск|ребен|дети|child/.test(t)) return 'дети';
  if (/взросл|adult/.test(t)) return 'взрослые';
  return 'unknown';
}

function normalizeMnn(mnn) {
  if (mnn == null) return null;
  if (Array.isArray(mnn)) {
    const parts = mnn.map((x) => String(x || '').trim()).filter(Boolean);
    return parts.length ? parts.join(', ') : null;
  }
  const s = String(mnn).trim();
  return s || null;
}

function isHomeopathy(text) {
  return /гомеоп|homeop/i.test(String(text || ''));
}

return items.map((item, index) => {
  const j = item.json || {};
  const kind = j.product_kind || null;
  const text = j.normalized_text || '';
  const needs = j.needs_mnn_enrichment === true;
  const alreadyResolved = j.mnn_resolution_status === 'resolved_catalog' && j.resolved_mnn;

  const shouldCall =
    needs &&
    kind === 'drug' &&
    !isHomeopathy(text) &&
    String(text).trim().length >= 3 &&
    !alreadyResolved;

  // Response may already be on item (after HTTP) under enrichment_raw / body
  const resp = j.mnn_enrichment_raw || j.enrichment_response || j.body || null;

  let mapped = {
    mnn_enriched: null,
    rx_otc_enriched: 'unknown',
    age_enriched: 'unknown',
    mnn_enrichment_status: null,
    mnn_evidence: [],
    needs_human_review: j.needs_human_review === true,
    enrichment_should_call: shouldCall,
  };

  if (resp && typeof resp === 'object') {
    const status = String(resp.status || '').toLowerCase() || 'error';
    const category = String(resp.Category || resp.category || '');
    const evidence = Array.isArray(resp.evidence) ? resp.evidence : [];
    mapped.mnn_enrichment_status = status;
    mapped.mnn_evidence = evidence;
    mapped.rx_otc_enriched = normalizeRx(resp.RX_OTC ?? resp.rx_otc);
    mapped.age_enriched = normalizeAge(resp.Age ?? resp.age);

    if (status === 'ok' && category === 'Drug' && evidence.length && resp.mnn != null) {
      mapped.mnn_enriched = normalizeMnn(resp.mnn);
    } else {
      mapped.mnn_enriched = null;
      mapped.needs_human_review = true;
    }
  }

  const productClassificationLogInsertEnrichment =
    j.run_id == null
      ? null
      : {
          run_id: Number(j.run_id),
          product_id: Number(j.product_id),
          product_raw_id: j.product_raw_id != null ? Number(j.product_raw_id) : null,
          stage: 'mnn_enrichment',
          actor_type: 'llm',
          actor_name: 'mnn-drug-enrichment',
          status: mapped.mnn_enriched ? 'success' : 'needs_review',
          input_payload: {
            product: text,
            needs_mnn_enrichment: needs,
            enrichment_should_call: shouldCall,
          },
          output_payload: {
            enrichment_response: resp,
            mnn_enriched: mapped.mnn_enriched,
            rx_otc_enriched: mapped.rx_otc_enriched,
            age_enriched: mapped.age_enriched,
            mnn_enrichment_status: mapped.mnn_enrichment_status,
            mnn_evidence: mapped.mnn_evidence,
          },
          selected_category_id: null,
          validation_passed: Boolean(mapped.mnn_enriched),
          workflow_version: j.workflow_version || 'mnn_catalog_enrichment_v1',
          prompt_version: j.prompt_version || 'mnn_drug_enrichment',
        };

  return {
    json: {
      ...j,
      ...mapped,
      enrichment_webhook_body: shouldCall ? { product: text } : null,
      product_classification_log_insert_mnn_enrichment: productClassificationLogInsertEnrichment,
      attr_mnn: j.attr_mnn,
      attr_rx_otc: j.attr_rx_otc,
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
