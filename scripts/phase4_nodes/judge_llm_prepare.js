return items.map((item, index) => {
  const j = item.json || {};
  const C = j.constants || {};
  const WORKFLOW_VERSION = 'stage2_judge_v1';
  const PROMPT_VERSION = 'prompt_judge_v1';

  const ruleShortlist = Array.isArray(j.shortlist_json) ? j.shortlist_json : [];
  const branchShortlist = Array.isArray(j.branch_shortlist_json) ? j.branch_shortlist_json : [];

  const formatShortlist = (list, label) => {
    if (!list.length) return `${label}: EMPTY`;
    return list.map((c, idx) => {
      const reasons = Array.isArray(c.reasons) ? c.reasons.join(', ') : '';
      return `${idx + 1}. id=${c.category_id}, code=${c.category_code || ''}, name=${c.category_name || ''}, score=${c.score ?? ''}, reasons=${reasons}`;
    }).join('\n');
  };

  const primaryRound = {
    llm_category_id: j.llm_category_id ?? null,
    llm_confidence: j.llm_confidence ?? null,
    llm_explanation: j.llm_explanation ?? null,
    llm_validation_passed: j.llm_validation_passed ?? null,
    llm_reject_reason: j.llm_reject_reason ?? null,
    rule_top_category_id: j.rule_top_category_id ?? null,
    rule_top_score: j.rule_top_score ?? null,
  };

  const fallback2a = {
    direction: j.fallback_2a_direction ?? null,
    block_family: j.fallback_2a_block_family ?? null,
    family_code: j.fallback_2a_family_code ?? null,
    nosology_hint: j.fallback_2a_nosology_hint ?? null,
    confidence: j.fallback_2a_confidence ?? null,
    explanation: j.fallback_2a_explanation ?? null,
  };

  const fallback2b = {
    category_id: j.fallback_2b_category_id ?? null,
    confidence: j.fallback_2b_confidence ?? null,
    explanation: j.fallback_2b_explanation ?? null,
    validation_passed: j.fallback_2b_validation_passed ?? null,
    reject_reason: j.fallback_2b_reject_reason ?? null,
  };

  const disputeContext = {
    routing_hint: j.routing_hint ?? null,
    primary_conflict: j.routing_hint?.primary_conflict ?? null,
    fallback_2b_reject_reason: j.fallback_2b_reject_reason ?? null,
    suggested_next_action: j.next_action ?? null,
  };

  const promptSystem =
    'You are a senior pharmacy product classification judge. Review prior automated rounds and return ONLY valid JSON with keys: winner_source, category_id, confidence, explanation, needs_human_review. winner_source must be one of: llm, fallback_2b, none. category_id must be from the allowed candidate ids or null if none fits.';

  const promptUser = `
Товар:
${j.combined_text || ''}

Тип товара: ${j.product_type_guess || 'unknown'}
run_id: ${j.run_id ?? ''}

Primary LLM (P1):
${JSON.stringify(primaryRound, null, 2)}

Fallback 2A (ветка):
${JSON.stringify(fallback2a, null, 2)}

Fallback 2B (категория в ветке):
${JSON.stringify(fallback2b, null, 2)}

Контекст спора:
${JSON.stringify(disputeContext, null, 2)}

Rule shortlist (primary):
${formatShortlist(ruleShortlist, 'rule')}

Branch shortlist (fallback 2B):
${formatShortlist(branchShortlist, 'branch')}

Задача:
- Выбери финальную category_id из объединения shortlist-ов выше, либо null если ни одна не подходит.
- winner_source: чей ответ вы предпочитаете (llm | fallback_2b | none).
- confidence: 0.0–1.0; explanation: 1–3 предложения на русском.
- needs_human_review=true если уверенность низкая или кандидаты противоречивы.
- Верни только JSON без markdown.
`.trim();

  return {
    json: {
      ...j,
      workflow_version: WORKFLOW_VERSION,
      prompt_version: PROMPT_VERSION,
      context: {
        run_id: j.run_id !== undefined && j.run_id !== null && j.run_id !== '' ? Number(j.run_id) : null,
        product_id: j.product_id !== undefined && j.product_id !== null && j.product_id !== '' ? Number(j.product_id) : null,
        product_raw_id: j.product_raw_id !== undefined && j.product_raw_id !== null && j.product_raw_id !== '' ? Number(j.product_raw_id) : null,
        primary_round: primaryRound,
        fallback_2a: fallback2a,
        fallback_2b: fallback2b,
        dispute_context: disputeContext,
        rule_shortlist_json: ruleShortlist,
        branch_shortlist_json: branchShortlist,
      },
      prompt_system: promptSystem,
      prompt_user: promptUser,
    },
    pairedItem: index,
  };
});
