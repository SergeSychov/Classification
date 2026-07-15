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

function safeBoolean(v) {
  if (v === undefined || v === null || v === '') return null;
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (['true', '1', 'yes', 'y'].includes(s)) return true;
    if (['false', '0', 'no', 'n'].includes(s)) return false;
  }
  return null;
}

return items.map((item, index) => {
  const root = item.json || {};
  const ctx = root.context || {};
  const C = root.constants || {};

  const STAGE = C.stage || { judge: 'judge' };
  const DECISION = C.decision_status || {
    classified: 'classified',
    needs_human_review: 'needs_human_review',
    error: 'error',
  };
  const FINAL = C.final_source || { judge: 'judge', system: 'system' };
  const NEXT = C.next_action || { none: 'none', human_review: 'human_review' };
  const ACTOR = C.actor_type || { llm: 'llm' };
  const LOG = C.log_status || { success: 'success', needs_review: 'needs_review', rejected: 'rejected' };
  const THRESHOLDS = C.thresholds || { min_confidence_judge_ok: 0.60 };
  const MODEL = C.model || { judge_actor_name: 'qwen/qwen3.5-flash-02-23' };

  const WORKFLOW_VERSION = root.workflow_version || 'stage2_judge_v1';
  const PROMPT_VERSION = root.prompt_version || 'prompt_judge_v1';

  const runId = normalizeInt(ctx.run_id ?? root.run_id);
  const productId = normalizeInt(ctx.product_id ?? root.product_id);
  const productRawId = normalizeInt(ctx.product_raw_id ?? root.product_raw_id);

  const ruleShortlist = Array.isArray(ctx.rule_shortlist_json)
    ? ctx.rule_shortlist_json
    : (Array.isArray(root.shortlist_json) ? root.shortlist_json : []);
  const branchShortlist = Array.isArray(ctx.branch_shortlist_json)
    ? ctx.branch_shortlist_json
    : (Array.isArray(root.branch_shortlist_json) ? root.branch_shortlist_json : []);

  const allowedIds = new Set();
  for (const list of [ruleShortlist, branchShortlist]) {
    for (const c of list) {
      const id = normalizeInt(c.category_id);
      if (id !== null) allowedIds.add(String(id));
    }
  }
  const llmId = normalizeInt(root.llm_category_id);
  const fb2bId = normalizeInt(root.fallback_2b_category_id);
  if (llmId !== null) allowedIds.add(String(llmId));
  if (fb2bId !== null) allowedIds.add(String(fb2bId));

  const rawModelOutput = root.output ?? root.text ?? root.response ?? root.content ?? root.result ?? null;
  const parsedResult = safeParseJson(rawModelOutput);

  let judgeCategoryId = null;
  let judgeConfidence = null;
  let judgeExplanation = null;
  let judgeNeedsReview = null;
  let judgeWinnerSource = null;
  let judgeValidationPassed = false;
  let judgeRejectReason = null;
  let judgeRawJson = safeJson(parsedResult.ok ? parsedResult.parsed : null);
  let judgeRawOutputText = safeText(parsedResult.raw_text);

  const validWinnerSources = new Set(['llm', 'fallback_2b', 'none']);

  if (!parsedResult.ok) {
    judgeRejectReason = parsedResult.error;
  } else {
    const parsed = parsedResult.parsed || {};
    judgeCategoryId = normalizeInt(parsed.category_id ?? parsed.final_category_id);
    judgeConfidence = normalizeConfidence(parsed.confidence);
    judgeExplanation = safeText(parsed.explanation);
    judgeNeedsReview = safeBoolean(parsed.needs_human_review);
    judgeWinnerSource = safeText(parsed.winner_source);

    if (!judgeExplanation) {
      judgeRejectReason = 'missing_explanation';
    } else if (judgeConfidence === null) {
      judgeRejectReason = 'invalid_confidence';
    } else if (judgeWinnerSource && !validWinnerSources.has(judgeWinnerSource)) {
      judgeRejectReason = 'invalid_winner_source';
    } else if (judgeCategoryId === null && judgeWinnerSource !== 'none') {
      judgeRejectReason = 'null_category';
    } else if (judgeCategoryId !== null && allowedIds.size > 0 && !allowedIds.has(String(judgeCategoryId))) {
      judgeRejectReason = 'category_outside_candidates';
    } else {
      judgeValidationPassed = true;
    }
  }

  let decisionStatus = DECISION.needs_human_review;
  let finalSource = FINAL.system;
  let finalCategoryId = null;
  let finalConfidence = null;
  let finalExplanation = null;
  let nextAction = NEXT.human_review;
  let logStatus = LOG.needs_review;

  if (!judgeValidationPassed) {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.human_review;
    logStatus = LOG.rejected;
  } else if (judgeNeedsReview === true) {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.human_review;
    logStatus = LOG.needs_review;
  } else if (judgeCategoryId === null || judgeWinnerSource === 'none') {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.human_review;
    logStatus = LOG.needs_review;
  } else if (judgeConfidence > THRESHOLDS.min_confidence_judge_ok) {
    decisionStatus = DECISION.classified;
    finalSource = FINAL.judge;
    finalCategoryId = judgeCategoryId;
    finalConfidence = judgeConfidence;
    finalExplanation = judgeExplanation;
    nextAction = NEXT.none;
    logStatus = LOG.success;
  } else {
    decisionStatus = DECISION.needs_human_review;
    nextAction = NEXT.human_review;
    logStatus = LOG.needs_review;
  }

  const routingHint = {
    stage: STAGE.judge,
    judge_validation_passed: judgeValidationPassed,
    judge_confidence: judgeConfidence,
    judge_reject_reason: judgeRejectReason,
    judge_winner_source: judgeWinnerSource,
    judge_needs_review: judgeNeedsReview,
    allowed_candidate_count: allowedIds.size,
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
    judge_category_id: judgeCategoryId,
    judge_confidence: judgeConfidence,
    judge_explanation: judgeExplanation,
    judge_needs_review: judgeNeedsReview,
    judge_raw_json: judgeRawJson,
    fallback_2a_direction: safeText(root.fallback_2a_direction),
    fallback_2a_block_family: safeText(root.fallback_2a_block_family),
    fallback_2a_family_code: safeText(root.fallback_2a_family_code),
    fallback_2a_nosology_hint: safeText(root.fallback_2a_nosology_hint),
    fallback_2a_confidence: safeNumber(root.fallback_2a_confidence),
    fallback_2a_explanation: safeText(root.fallback_2a_explanation),
    fallback_2a_raw_json: safeJson(root.fallback_2a_raw_json),
    fallback_2b_category_id: safeNumber(root.fallback_2b_category_id),
    fallback_2b_confidence: safeNumber(root.fallback_2b_confidence),
    fallback_2b_explanation: safeText(root.fallback_2b_explanation),
    fallback_2b_raw_json: safeJson(root.fallback_2b_raw_json),
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
      stage: STAGE.judge,
      actor_type: ACTOR.llm,
      actor_name: MODEL.judge_actor_name,
      workflow_version: WORKFLOW_VERSION,
      prompt_version: PROMPT_VERSION,
      judge_category_id: judgeCategoryId,
      judge_confidence: judgeConfidence,
      judge_explanation: judgeExplanation,
      judge_needs_review: judgeNeedsReview,
      judge_winner_source: judgeWinnerSource,
      judge_validation_passed: judgeValidationPassed,
      judge_reject_reason: judgeRejectReason,
      judge_raw_json: judgeRawJson,
      judge_raw_output_text: judgeRawOutputText,
      validation_passed: judgeValidationPassed,
      error_message: judgeRejectReason,
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
