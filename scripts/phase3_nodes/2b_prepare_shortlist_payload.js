return items.map((item, index) => {
  const j = item.json || {};
  const shortlist = Array.isArray(j.branch_shortlist_json) ? j.branch_shortlist_json : [];
  const top = shortlist[0] || null;

  return {
    json: {
      ...j,
      shortlist_insert: {
        product_id: Number(j.product_id),
        product_raw_id: Number(j.product_raw_id),
        product_type_guess: j.product_type_guess || null,
        rule_top_category_id: top ? Number(top.category_id) : null,
        rule_top_score: top ? top.score : 0,
        shortlist_count: shortlist.length,
        shortlist_json: shortlist,
        combined_text: j.combined_text || null,
        stage: 'fallback_2b',
        shortlist_type: 'branch_shortlist',
        parent_stage: 'fallback_2a',
        shortlist_metadata: j.shortlist_metadata || null,
        rules_version: 'branch_shortlist_v1',
      },
    },
    pairedItem: { item: index },
  };
});
