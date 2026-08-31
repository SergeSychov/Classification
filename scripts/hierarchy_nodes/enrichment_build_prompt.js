// Enrichment — Build Prompt (offline MNN/RX enrichment, prompt_enrichment_v1).
// Mirror of prompts in scripts/sem_enrich_mnn_rx.py — keep in sync.
// Branches: drug | vitamin_or_baa. Does not mutate attr_* baseline.

const PROMPT_VERSION = 'prompt_enrichment_v1';

const SYSTEM_DRUG =
  'You are a clinical pharmacology assistant. Given normalized Russian text of a pharmacy product\n' +
  'and its basic attributes (brand, dosage form, route, dosage, therapeutic class),\n' +
  'you must determine:\n\n' +
  '- mnn: international nonproprietary name (INN) of the active substance(s) (in Russian, short form),\n' +
  '- rx_otc: "rx" for prescription drugs, "otc" for non-prescription, or "unknown" if cannot be determined.\n\n' +
  'Return ONLY valid JSON with keys: mnn, rx_otc, confidence, explanation.\n' +
  'All fields may be null. confidence must be a number from 0.0 to 1.0.\n' +
  'Explanation must be a short Russian string (1–3 sentences).\n' +
  'If you are not sure, prefer mnn=null and rx_otc="unknown".\n' +
  'Never invent an INN if the brand name does not clearly imply it.';

const SYSTEM_VITAMIN =
  'You are a nutraceuticals and vitamins assistant. Given normalized text of a BAA/vitamin product\n' +
  'and its basic attributes (brand, dosage form, dosage, therapeutic profile),\n' +
  'you must determine:\n\n' +
  '- mnn: key nutraceutical or vitamin (e.g., "Куркумин", "Омега-3", "Таурин", "Коэнзим Q10", "Коллаген", "L-метилфолат", "Аскорбиновая кислота", "Хром", "Лецитин", "Псиллиум"),\n' +
  '  or "Комплекс" only when no single dominant nutrient can be determined,\n' +
  '- combination_hint: "monocomponent" or "multicomponent" or "unknown".\n\n' +
  'Return ONLY valid JSON with keys: mnn, combination_hint, confidence, explanation.\n' +
  'All fields may be null. confidence must be a number from 0.0 to 1.0.\n' +
  'Explanation must be a short Russian string (1–3 sentences).\n' +
  'If you are not sure about the nutrient, prefer mnn=null and combination_hint="unknown".';

function buildDrugUser(j) {
  return (
    `Товар (normalized_text):\n${j.normalized_text || ''}\n\n` +
    `Базовые атрибуты:\n` +
    `- Бренд: ${j.attr_brand ?? null}\n` +
    `- Лекарственная форма: ${j.attr_dosage_form ?? null}\n` +
    `- Путь введения: ${j.attr_administration_route ?? null}\n` +
    `- Дозировка: ${j.attr_dosage ?? null}\n` +
    `- Семантическое объяснение (класс/группа):\n${j.semantic_explanation || ''}\n\n` +
    `Текущие значения:\n` +
    `- attr_mnn (Sem): ${j.attr_mnn ?? null}\n` +
    `- attr_rx_otc (Sem): ${j.attr_rx_otc ?? null}\n\n` +
    `Задача:\n` +
    `- Если товар является лекарственным препаратом (ЛС), определи MNN (или оставь null, если состав неочевиден).\n` +
    `- Определи rx_otc: "rx" для рецептурного препарата, "otc" для безрецептурного, "unknown" если по тексту это неясно.\n` +
    `- Если действующее вещество и рецептурность неочевидны — лучше вернуть mnn=null и rx_otc="unknown", чем угадывать.\n` +
    `- Верни только JSON без markdown.`
  );
}

function buildVitaminUser(j) {
  return (
    `Товар (normalized_text):\n${j.normalized_text || ''}\n\n` +
    `Базовые атрибуты:\n` +
    `- Бренд: ${j.attr_brand ?? null}\n` +
    `- Форма: ${j.attr_dosage_form ?? null}\n` +
    `- Дозировка: ${j.attr_dosage ?? null}\n` +
    `- Нозология/профиль (Sem): ${j.attr_nosology ?? null}\n` +
    `- Семантическое объяснение:\n${j.semantic_explanation || ''}\n\n` +
    `Текущие значения:\n` +
    `- attr_mnn (Sem): ${j.attr_mnn ?? null}\n` +
    `- attr_combination_hint (Sem): ${j.attr_combination_hint ?? null}\n\n` +
    `Задача:\n` +
    `- Определи ключевой нутриент или витамин (mnn), если он явно указан (например, "Куркумин", "Омега-3", "Таурин", "Коэнзим Q10", "Коллаген", "L-метилфолат", "Аскорбиновая кислота", "Хром", "Лецитин", "Псиллиум").\n` +
    `- Если продукт явно многокомпонентный (мультивитамин, многокомпонентный комплекс) и нет одного доминирующего нутриента — mnn="Комплекс".\n` +
    `- Определи combination_hint: "monocomponent" или "multicomponent" или "unknown".\n` +
    `- Верни только JSON без markdown.`
  );
}

return items.map((item, index) => {
  const j = item.json || {};
  const kind = j.enrich_kind || j.product_kind || '';
  const isVitamin = kind === 'vitamin_or_baa';

  const promptSystem = isVitamin ? SYSTEM_VITAMIN : SYSTEM_DRUG;
  const promptUser = isVitamin ? buildVitaminUser(j) : buildDrugUser(j);

  return {
    json: {
      ...j,
      prompt_system: promptSystem,
      prompt_user: promptUser,
      prompt_version: PROMPT_VERSION,
      stage: 'mnn_rx_enrichment',
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
