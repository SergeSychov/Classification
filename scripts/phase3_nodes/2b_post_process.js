function extractJsonString(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') return JSON.stringify(value);
  let text = String(value).trim();
  const codeFenceMatch = text.match(/^```(?:json)?\s*\n?([\s\S]+?)\n?```\s*$/i);
  if (codeFenceMatch) text = codeFenceMatch[1].trim();
  return text;
}

function safeParseJson(value) {
  const text = extractJsonString(value);
  if (!text) return { ok: false, error: 'empty_output', parsed: null, raw_text: null };
  try {
    return { ok: true, error: null, parsed: JSON.parse(text), raw_text: text };
  } catch (e) {
    return { ok: false, error: 'invalid_json', parsed: null, raw_text: text };
  }
}

function normalizeInt(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function normalizeConfidence(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  if (n < 0 || n > 1) return null;
  return n;
}

function safeText(v) {
  if (v === undefined || v === null || v === '') return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}

function safeNumber(v) {
  if (v === undefined || v === null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function safeJson(v) {
  if (v === undefined || v === null) return null;
  return v;
}

return items.map((item, index) => {
  const root = item.json || {};
  const ctx = root.context || {};
  const C = root.constants || {};

  const STAGE = C.stage || { fallback_2b: 'fallback_2b' };
  const DECISION = C.decision_status || {
    classified: 'classified',
    needs_human_review: 'needs_human_review',
    error: 'error',
  };
  const FINAL = C.final_source || { fallback_2b: 'fallback_2b', system: 'system' };
  const NEXT = C.next_action || { none: 'none', judge: 'judge', human_review: 'human_review' };
  const ACTOR = C.actor_type || { llm: 'llm' };
  const LOG = C.log_status || { success: 'success', needs_review: 'needs_review', rejected: 'rejected' };
  const THRESHOLDS = C.thresholds || { min_confidence_2b_ok: 0.60 };
  const MODEL = C.model || { fallback_actor_name: 'deepseek-chat' };

  const WORKFLOW_VERSION = root.workflow_version || 'stage2_fallback_2b_v1';
  const PROMPT_VERSION = root.prompt_version || 'prompt_fallback_2b_v1';

  const runId = normalizeInt(ctx.run_id ?? root.run_id);
  const productId = normalizeInt(ctx.product_id ?? root.product_id);
  const productRawId = normalizeInt(ctx.product_raw_id ?? root.product_raw_id);
  const llmCategoryId = normalizeInt(root.llm_category_id);

  const shortlist = Array.isArray(ctx.branch_shortlist_json)
    ? ctx.branch_shortlist_json
    : (Array.isArray(root.branch_shortlist_json) ? root.branch_shortlist_json : []);

  const shortlistIds = new Set(
    shortlist.map(c => normalizeInt(c.category_id)).filter(v => v !== null).map(String)
  );

  const skipLlm = root.skip_llm === true || ctx.skip_llm === true || shortlist.length === 0;

  let fallback2bCategoryId = null;
  let fallback2bConfidence = null;
  let fallback2bExplanation = null;
  let fallback2bValidationPassed = false;
  let fallback2bRejectReason = null;
  let fallback2bRawJson = null;
  let fallback2bRawOutputText = null;
  let categoryOutsideShortlist = false;

  if (skipLlm) {
    fallback2bRejectReason = 'empty_branch_shortlist';
  } else {
    const rawModelOutput = root.output ?? root.text ?? root.response ?? root.content ?? root.result ?? null;
    const parsedResult = safeParseJson(rawModelOutput);
    fallback2bRawOutputText = safeText(parsedResult.raw_text);
    fallback2bRawJson = safeJson(parsedResult.ok ? parsedResult.parsed : null);

    if (!parsedResult.ok) {
      fallback2bRejectReason = parsedResult.error;
    } else {
      const parsed = parsedResult.parsed || {};
      fallback2bCategoryId = normalizeInt(parsed.category_id);
      fallback2bConfidence = normalizeConfidence(parsed.confidence);
      fallback2bExplanation = safeText(parsed.explanation);

      if (!fallback2bExplanation) {
        fallback2bRejectReason = 'missing_explanation';
      } else if (fallback2bConfidence === null) {
        fallback2bRejectReason = 'invalid_confidence';
      } else if (fallback2bCategoryId === null) {
        fallback2bRejectReason = 'null_category';
      } else if (!shortlistIds.has(String(fallback2bCategoryId))) {
        categoryOutsideShortlist = true;
        fallback2bRejectReason = 'category_outside_shortlist';
      } else {
        fallback2bValidationPassed = true;
      }
    }
  }

  const primaryConflict = llmCategoryId !== null && fallback2bCategoryId !== null && llmCategoryId !== fallback2bCategoryId;

  let decisionStatus = DECISION.needs_human_review;
  let finalSource = FINAL.system;
  let finalCategoryId = null;
  let finalConfidence = null;
  let finalExplanation = null;
  let nextAction = NEXT.human_review;
  let logStatus = LOG.needs_review;

  if (skipLlm || fallback2bRejectReason === 'empty_branch_shortlist') {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.human_review;
    logStatus = LOG.rejected;
  } else if (!fallback2bValidationPassed) {
    decisionStatus = DECISION.needs_human_review;
    nextAction = (fallback2bRejectReason === 'null_category' || categoryOutsideShortlist)
      ? NEXT.judge
      : NEXT.human_review;
    logStatus = LOG.rejected;
  } else if (primaryConflict) {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.judge;
    logStatus = LOG.needs_review;
  } else if (fallback2bConfidence > THRESHOLDS.min_confidence_2b_ok) {
    decisionStatus = DECISION.classified;
    finalSource = FINAL.fallback_2b;
    finalCategoryId = fallback2bCategoryId;
    finalConfidence = fallback2bConfidence;
    finalExplanation = fallback2bExplanation;
    nextAction = NEXT.none;
    logStatus = LOG.success;
  } else {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.judge;
    logStatus = LOG.needs_review;
  }

  const routingHint = {
    stage: STAGE.fallback_2b,
    branch_shortlist_count: shortlist.length,
    fallback_2b_validation_passed: fallback2bValidationPassed,
    fallback_2b_confidence: fallback2bConfidence,
    fallback_2b_reject_reason: fallback2bRejectReason,
    category_outside_shortlist: categoryOutsideShortlist,
    primary_conflict: primaryConflict,
    suggested_next_action: nextAction,
  };

  const productClassificationUpdate = {
    product_id: productId,
    product_raw_id: productRawId,
    latest_run_id: runId,
    workflow_version: WORKFLOW_VERSION,
    prompt_version: PROMPT_VERSION,
    rule_top_category_id: safeNumber(root.rule_top_category_id),
    rule_top_score: safeNumber(root.rule_top_score),
    rule_shortlist_id: safeNumber(root.rule_shortlist_id),
    rule_decision_status: safeText(root.rule_decision_status),
    llm_category_id: safeNumber(root.llm_category_id),
    llm_confidence: safeNumber(root.llm_confidence),
    llm_explanation: safeText(root.llm_explanation),
    llm_needs_review: root.llm_needs_review ?? null,
    llm_validation_passed: root.llm_validation_passed ?? null,
    llm_reject_reason: safeText(root.llm_reject_reason),
    llm_raw_json: safeJson(root.llm_raw_json),
    fallback_2a_direction: safeText(root.fallback_2a_direction),
    fallback_2a_block_family: safeText(root.fallback_2a_block_family),
    fallback_2a_family_code: safeText(root.fallback_2a_family_code),
    fallback_2a_nosology_hint: safeText(root.fallback_2a_nosology_hint),
    fallback_2a_confidence: safeNumber(root.fallback_2a_confidence),
    fallback_2a_explanation: safeText(root.fallback_2a_explanation),
    fallback_2a_raw_json: safeJson(root.fallback_2a_raw_json),
    fallback_2b_category_id: fallback2bCategoryId,
    fallback_2b_confidence: fallback2bConfidence,
    fallback_2b_explanation: fallback2bExplanation,
    fallback_2b_raw_json: fallback2bRawJson,
    final_category_id: finalCategoryId,
    final_confidence: finalConfidence,
    final_explanation: finalExplanation,
    final_source: finalSource,
    decision_status: decisionStatus,
    next_action: nextAction,
    routing_hint: routingHint,
  };

  return {
    json: {
      ...root,
      run_id: runId,
      product_id: productId,
      product_raw_id: productRawId,
      stage: STAGE.fallback_2b,
      actor_type: ACTOR.llm,
      actor_name: MODEL.fallback_actor_name,
      workflow_version: WORKFLOW_VERSION,
      prompt_version: PROMPT_VERSION,
      fallback_2b_category_id: fallback2bCategoryId,
      fallback_2b_confidence: fallback2bConfidence,
      fallback_2b_explanation: fallback2bExplanation,
      fallback_2b_validation_passed: fallback2bValidationPassed,
      fallback_2b_reject_reason: fallback2bRejectReason,
      fallback_2b_raw_json: fallback2bRawJson,
      fallback_2b_raw_output_text: fallback2bRawOutputText,
      branch_shortlist_json: shortlist,
      branch_shortlist_count: shortlist.length,
      validation_passed: fallback2bValidationPassed,
      error_message: fallback2bRejectReason,
      decision_status: decisionStatus,
      next_action: nextAction,
      final_source: finalSource,
      final_category_id: finalCategoryId,
      final_confidence: finalConfidence,
      final_explanation: finalExplanation,
      routing_hint: routingHint,
      product_classification_update: productClassificationUpdate,
    },
    pairedItem: index,
  };
});
