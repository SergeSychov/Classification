// Sem0 — Build Prompt (product_kind / product_family / attr_profile).
// Policy v3: kind borderlines + cosmetic route/form applicable.
// No category_id / direction / need. Soft-continue into Sem1.

const DRUG_FAMILIES = [
  'кожные заболевания',
  'простуда и ОРВИ',
  'ЖКТ',
  'Кровь / Кровеносная система',
  'Нервная система',
  'Боль и Температура',
  'Сердце и сосуды',
  'Опорно-двигательный аппарат',
  'Кашель',
  'Урология',
  'Слух и зрение',
  'Гормоны',
  'Стоматология',
  'Бактериофаги',
  'Противоклещевые',
  'Инъекции',
  'Инфузии',
  'Гомеопатия',
  'Травы',
];

const DEVICE_FAMILIES = [
  'Измерительные приборы',
  'Гигиена и косметика',
  'Товары для мам и детей',
  'Приборы для терапии',
  'Приборы и средства для инъекций',
  'Перевязочные материалы',
  'Пластыри',
  'Другое медизделие',
];

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
    'You analyze a pharmacy product and determine its top-level kind, therapeutic or usage family, and which semantic attributes are applicable.\n\n' +
    'Return ONLY valid JSON with keys:\n' +
    'product_kind, product_family, attr_profile, confidence, explanation.\n\n' +
    'Do NOT return category_id, direction, need, block_family, or any leaf category.\n\n' +
    'product_kind must be one of: drug, vitamin_or_baa, medical_device, cosmetic_hygiene, other.\n' +
    'attr_profile must contain all keys mnn, brand, rx_otc, nosology, administration_route, dosage_form, dosage, age_segment, package_hint, combination_hint with values "applicable" or "not_applicable".\n\n' +
    '=== Kind borderlines (important) ===\n' +
    '- Empty / disposable syringe, insulin syringe (U-40/U-100), injection needle/pen needle WITHOUT a drug brand → product_kind=medical_device (clinical_like / «Приборы и средства для инъекций»).\n' +
    '- «Шприц инсулиновый» alone is a DEVICE, not a drug (insulin here = syringe scale, not insulin medicine).\n' +
    '- Prefilled cartridge / pen / syringe WITH named drug (Туджео, Тресиба, НовоРапид, Велгия, Гонал-Ф, Теваграстим, Метортрит, …) + solution dose (ЕД/мл, мг/мл, МЕ) → product_kind=drug (family Инъекции).\n' +
    '- Pediculicide / anti-lice / biocide («педикулицид», «от вшей») → product_kind=other (not cosmetic_hygiene).\n' +
    '- Herbal leaf / herb filter-packs (ф/п, листья, трава) without clear pharmaceutical INN → vitamin_or_baa (not drug).\n' +
    '- Multi-herb calming tinctures without INN → vitamin_or_baa preferred over drug.\n' +
    '- Capsules/tablets marketed as supplement / BAA / vitamin complex → vitamin_or_baa (not other).\n\n' +
    '=== vitamin_or_baa ===\n' +
    'attr_profile: mnn, brand, nosology, administration_route, dosage_form, dosage, age_segment, package_hint, combination_hint = applicable; rx_otc = not_applicable.\n' +
    'Later Sem1 meanings: vitamins nosology ∈ {отдельные нутриенты, комплексные профили}; BAA nosology ∈ {нутрицевтики, парафармацевтики, эубиотики}; nutrient goes to mnn.\n\n' +
    '=== medical_device ===\n' +
    'Choose product_family from the device list. Split via family:\n' +
    '- hygiene_like (Гигиена и косметика; Товары для мам и детей): mnn, rx_otc, nosology, administration_route, dosage_form, dosage, combination_hint = not_applicable; brand, age_segment, package_hint = applicable.\n' +
    '- clinical_like (Пластыри; Перевязочные материалы; Приборы и средства для инъекций; Приборы для терапии; Измерительные приборы; Другое медизделие when clinically useful): mnn, rx_otc, nosology, combination_hint = not_applicable; brand, administration_route, dosage_form, dosage, age_segment, package_hint = applicable.\n\n' +
    '=== cosmetic_hygiene ===\n' +
    'attr_profile: mnn, rx_otc, nosology, dosage, combination_hint = not_applicable; brand, administration_route, dosage_form, age_segment, package_hint = applicable.\n' +
    'Route/form allowed when text clearly has topical cue (крем, гель, шампунь, аэрозоль, дезодорант, помада) → typically наружно + form.\n\n' +
    '=== drug ===\n' +
    'Pharma attrs usually applicable.\n\n' +
    '=== other ===\n' +
    'Pediculicides, household biocides, unclear non-pharma: conservative not_applicable for mnn/rx/nosology; brand/package/age often applicable.\n\n' +
    'confidence must be a number from 0.0 to 1.0.\n' +
    'explanation must be a short Russian string (1–3 sentences).';

  const promptUser = `
Товар (normalized_text):
${j.normalized_text || j.combined_text || ''}

Подсказки после Norm (могут быть null):
${JSON.stringify(attrHints, null, 2)}

Мягкая подсказка Stage 1 shortlist (НЕ обязательный набор):
${shortlistHint}

normalize_meta:
${JSON.stringify(j.normalize_meta || {}, null, 2)}

Списки product_family:
- если product_kind=drug, выбери один из: ${DRUG_FAMILIES.join('; ')}
- если product_kind=medical_device, выбери один из: ${DEVICE_FAMILIES.join('; ')}
- если product_kind=vitamin_or_baa: свободный короткий текст или null
- иначе: null

Задача:
- Определи product_kind с учётом borderlines (шприц+доза→drug; педикулицид→other; трава ф/п→vitamin_or_baa; БАД-капсулы→vitamin_or_baa).
- Определи product_family по правилам выше (или null).
- Заполни attr_profile по policy (для cosmetic_hygiene route/form = applicable).
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
        stage: 'sem0',
      },
    },
    pairedItem: index,
  };
});
