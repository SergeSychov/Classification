// Sem — Build Prompt (hierarchy B3 Sem / semantic_primary v4).
// Uses Sem0 product_kind / product_family / attr_profile hints (policy v3).
// No category_id / direction / need selection.

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
    product_kind: j.product_kind ?? null,
    product_family: j.product_family ?? null,
    attr_profile: j.attr_profile ?? null,
    medical_device_profile: j.medical_device_profile ?? null,
    product_kind_group_hint: j.product_kind_group_hint ?? null,
  };

  const promptSystem =
    'You extract semantic attributes for a pharmacy product. Return ONLY valid JSON with keys: mnn, brand, rx_otc, nosology, administration_route, dosage_form, dosage, age_segment, package_hint, combination_hint, confidence, explanation. Do NOT return category_id, direction, need, block_family, or any final leaf category. All attribute fields may be null. confidence must be a number from 0.0 to 1.0. explanation must be a short Russian string (1–3 sentences).\n\n' +
    'Учитывай product_kind / attr_profile:\n' +
    '- Если attr_profile[key]="not_applicable" — верни null.\n\n' +
    '=== mnn ===\n' +
    '- drug: заполняй mnn ТОЛЬКО если действующее вещество явно читается в тексте (как МНН/INN). Если вещество неочевидно и пришлось бы угадывать по бренду — верни mnn=null. Лучше null, чем чужой МНН.\n' +
    '- vitamin_or_baa: один доминирующий нутриент (Куркумин, Коллаген, Омега-3, Таурин, Коэнзим Q10, Лецитин, Хром, Псиллиум, L-метилфолат, …) → в mnn; только если нет доминанты и продукт явно мультивитаминный/многокомпонентный → mnn="Комплекс".\n\n' +
    '=== combination_hint (vitamin_or_baa) ===\n' +
    '- монокомпонентный — один нутриент;\n' +
    '- комбинированный — 2–3 явных компонента;\n' +
    '- многокомпонентный витаминно-минеральный комплекс — Компливит/Алфавит/Супрадин/Daily Vits и аналоги;\n' +
    '- не дублируй название нутриента в combination_hint.\n\n' +
    '=== rx_otc ===\n' +
    '- drug: только "rx" или "otc" (не пиши «рецептурный»/«без рецепта»).\n' +
    '- non-drug: null (нормализатор поставит «не применимо»).\n\n' +
    '=== nosology ===\n' +
    '- vitamin_or_baa: ТОЛЬКО одно из: нутрицевтики | парафармацевтики | эубиотики | отдельные нутриенты | комплексные профили.\n' +
    '  НЕ пиши «Витамин C» / название нутриента в nosology — это поле mnn.\n' +
    '- drug: терапевтический класс по смыслу текста; не выдумывай.\n' +
    '- medical_device / cosmetic_hygiene: обычно null.\n\n' +
    '=== age_segment ===\n' +
    'Допустимые значения: взрослые | дети | универсальный | не применимо | null.\n' +
    '- дети — только при явном детском сигнале (детский, для детей, N мес+, возрастной диапазон).\n' +
    '- взрослые — при «для взрослых» ИЛИ типичный ЛС без детских сигналов.\n' +
    '- универсальный — вся семья / любой возраст; для БАД без возраста предпочтительно.\n' +
    '- не применимо — возраст неважен (инструмент/часть гигиены без age binding).\n' +
    '- Если возраст неясен — лучше универсальный / не применимо / null, чем выдумывать узкий возраст.\n\n' +
    '=== route / form ===\n' +
    '- drug / vitamin_or_baa: заполняй при сигнале.\n' +
    '- medical_device clinical_like: route/form/dosage по attr_profile.\n' +
    '- medical_device hygiene_like: обычно null.\n' +
    '- cosmetic_hygiene: можно заполнять administration_route (часто наружно) и dosage_form (крем/гель/шампунь/аэрозоль/помада), если это явно в тексте; mnn/rx_otc/nosology/dosage/combination_hint = null.\n\n' +
    '- other: следуй attr_profile; не выдумывай.';

  const promptUser = `
Товар (normalized_text):
${j.normalized_text || j.combined_text || ''}

Подсказки после Norm / Sem0 (могут быть null):
${JSON.stringify(attrHints, null, 2)}

Мягкая подсказка Stage 1 shortlist (НЕ обязательный набор, НЕ выбирай category_id):
${shortlistHint}

normalize_meta:
${JSON.stringify(j.normalize_meta || {}, null, 2)}

Задача:
- Извлеки семантические атрибуты с учётом product_kind / attr_profile.
- Для drug: mnn только при явном веществе в тексте, иначе null.
- Для vitamin_or_baa: nosology из enum; нутриент → mnn.
- НЕ выбирай category_id / направление / потребность / финальную категорию.
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
