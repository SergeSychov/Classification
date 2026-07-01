return items.map((item, index) => {
  const j = item.json || {};
  const WORKFLOW_VERSION = 'stage2_fallback_2b_v1';
  const PROMPT_VERSION = 'prompt_fallback_2b_v1';

  const shortlist = Array.isArray(j.branch_shortlist_json) ? j.branch_shortlist_json : [];
  const skipLlm = j.skip_llm === true || shortlist.length === 0;

  const shortlistText = shortlist.length
    ? shortlist.map((c, idx) => {
        const reasons = Array.isArray(c.reasons) ? c.reasons.join(', ') : '';
        return `${idx + 1}. id=${c.category_id}, code=${c.category_code}, name=${c.category_name}, score=${c.score}, reasons=${reasons}`;
      }).join('\n')
    : 'EMPTY';

  const branchContext = {
    direction: j.fallback_2a_direction,
    block_family: j.fallback_2a_block_family,
    family_code: j.fallback_2a_family_code,
    nosology_hint: j.fallback_2a_nosology_hint,
    fallback_2a_confidence: j.fallback_2a_confidence,
    fallback_2a_explanation: j.fallback_2a_explanation,
  };

  const primaryContext = {
    llm_category_id: j.llm_category_id ?? null,
    llm_confidence: j.llm_confidence ?? null,
    llm_explanation: j.llm_explanation ?? null,
    llm_reject_reason: j.llm_reject_reason ?? null,
    rule_top_category_id: j.rule_top_category_id ?? null,
    rule_top_score: j.rule_top_score ?? null,
  };

  const promptSystem = skipLlm
    ? ''
    : 'You classify pharmacy products into one category within a pre-selected branch. Return ONLY valid JSON with keys: category_id, confidence, explanation. category_id MUST be from the branch shortlist.';

  const promptUser = skipLlm
    ? ''
    : `
Товар:
${j.combined_text || ''}

Тип товара: ${j.product_type_guess || 'unknown'}

Выбранная ветка (fallback 2A):
${JSON.stringify(branchContext, null, 2)}

Контекст неудачи primary LLM:
${JSON.stringify(primaryContext, null, 2)}

Branch shortlist (выбери ОДНУ категорию ТОЛЬКО из списка):
${shortlistText}

Политика:
- category_id ОБЯЗАН быть из shortlist выше.
- Если ни одна категория не подходит — верни category_id=null и объясни.
- confidence: 0.0–1.0; explanation: 1–3 предложения на русском.
- Только JSON, без комментариев.
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
        branch_context: branchContext,
        primary_context: primaryContext,
        branch_shortlist_json: shortlist,
        branch_shortlist_count: shortlist.length,
        skip_llm: skipLlm,
      },
      prompt_system: promptSystem,
      prompt_user: promptUser,
      skip_llm: skipLlm,
    },
    pairedItem: index,
  };
});
