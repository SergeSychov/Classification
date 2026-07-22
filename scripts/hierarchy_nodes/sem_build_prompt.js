// Sem — Build Prompt (hierarchy B3 Sem). No category_id / direction / need selection.

return items.map((item, index) => {
  const j = item.json || {};
  const shortlist = Array.isArray(j.shortlist_json) ? j.shortlist_json : [];

  const shortlistHint = shortlist.length
    ? shortlist
        .slice(0, 5)
        .map((c, idx) => {
          const name = c.category_name || c.name || '';
          const code = c.category_code || c.code || '';
          return `${idx + 1}. code=${code}, name=${name}`;
        })
        .join('\n')
    : 'NONE';

  const attrHints = {
    norm_mnn_product: j.norm_mnn_product ?? null,
    norm_brand_guess: j.norm_brand_guess ?? null,
    norm_form_guess: j.norm_form_guess ?? null,
    norm_dosage_guess: j.norm_dosage_guess ?? null,
    norm_pack_size_guess: j.norm_pack_size_guess ?? null,
    norm_product_type_guess: j.norm_product_type_guess ?? j.product_type_guess ?? null,
  };

  const promptSystem =
    'You extract semantic attributes for a pharmacy product. Return ONLY valid JSON with keys: mnn, brand, rx_otc, nosology, administration_route, dosage_form, dosage, age_segment, package_hint, combination_hint, confidence, explanation. Do NOT return category_id, direction, need, block_family, or any final leaf category. All attribute fields may be null. confidence must be a number from 0.0 to 1.0. explanation must be a short Russian string (1–3 sentences).';

  const promptUser = `
Товар (normalized_text):
${j.normalized_text || j.combined_text || ''}

Подсказки после Norm (могут быть null):
${JSON.stringify(attrHints, null, 2)}

Мягкая подсказка Stage 1 shortlist (НЕ обязательный набор, НЕ выбирай category_id):
${shortlistHint}

normalize_meta:
${JSON.stringify(j.normalize_meta || {}, null, 2)}

Задача:
- Извлеки семантические атрибуты товара.
- НЕ выбирай category_id / направление / потребность / финальную категорию.
- Если признак неизвестен — верни null (не выдумывай).
- confidence: 0.0–1.0; explanation: 1–3 предложения на русском.
- Верни только JSON без markdown.
`.trim();

  return {
    json: {
      ...j,
      prompt_system: promptSystem,
      prompt_user: promptUser,
      llm_prompt_debug: {
        system: promptSystem,
        user: promptUser,
      },
    },
    pairedItem: index,
  };
});
