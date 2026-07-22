// Sem — LLM Prepare (hierarchy B3 Sem).

function withoutStaleLlmOutput(j) {
  const src = j || {};
  const {
    output,
    text,
    response,
    content,
    result,
    llm_raw_output_text,
    ...rest
  } = src;
  return rest;
}

return items.map((item, index) => {
  const j = withoutStaleLlmOutput(item.json);
  const WORKFLOW_VERSION = 'stage2_hierarchy_v1';
  const PROMPT_VERSION = 'prompt_semantic_v1';
  const C = j.constants || {};

  return {
    json: {
      ...j,
      workflow_version: WORKFLOW_VERSION,
      prompt_version: PROMPT_VERSION,
      stage: (C.stage && C.stage.semantic_primary) || 'semantic_primary',
      actor_type: (C.actor_type && C.actor_type.llm) || 'llm',
      actor_name:
        (C.model && C.model.cascade_actor_name) ||
        (C.model && C.model.primary_actor_name) ||
        'deepseek-chat',
      context: {
        run_id:
          j.run_id !== undefined && j.run_id !== null && j.run_id !== ''
            ? Number(j.run_id)
            : null,
        product_id:
          j.product_id !== undefined && j.product_id !== null && j.product_id !== ''
            ? Number(j.product_id)
            : null,
        product_raw_id:
          j.product_raw_id !== undefined && j.product_raw_id !== null && j.product_raw_id !== ''
            ? Number(j.product_raw_id)
            : null,
        normalized_text: j.normalized_text ?? null,
        normalize_meta: j.normalize_meta ?? null,
        norm_warnings: j.norm_warnings ?? [],
        shortlist_json: Array.isArray(j.shortlist_json) ? j.shortlist_json : [],
      },
      prompt_system: j.prompt_system || '',
      prompt_user: j.prompt_user || '',
    },
    pairedItem: index,
  };
});
