const allItems = $input.all();
const products = [];
const categories = [];
for (const it of allItems) {
  const row = it.json || {};
  if (row.category_code !== undefined && row.category_code !== null && row.category_code !== '') {
    categories.push(row);
  } else if (row.product_id !== undefined && row.product_id !== null && row.product_id !== '') {
    products.push(row);
  }
}

function norm(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^\p{L}\p{N}\s/+.-]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function tokenize(text) {
  return norm(text).split(/\s+/).map(t => t.trim()).filter(Boolean);
}

function splitTerms(text) {
  if (!text) return [];
  const stop = new Set([
    'мг', 'мл', 'г', 'кг', 'ml', 'mg', 'n', 'na', 'cl', 'ca', 'k', 'd',
    'и', 'или', 'для', 'при', 'под', 'над', 'без', 'от', 'до', 'по',
    'средство', 'средства', 'форма', 'формы', 'дети', 'взрослые'
  ]);
  return Array.from(new Set(
    norm(text)
      .split(/[/,;|()+]+/)
      .flatMap(part => part.split(/\s+/))
      .map(s => s.trim())
      .filter(Boolean)
      .filter(t => t.length >= 3)
      .filter(t => !/^\d+$/.test(t))
      .filter(t => !stop.has(t))
  ));
}

function hasAnyWord(text, words) {
  if (!words || !words.length) return false;
  const tokens = new Set(tokenize(text).filter(w => w.length >= 3));
  const list = Array.isArray(words) ? words : [];
  return list.some(w => tokens.has(norm(w)));
}

function routeHints(text) {
  const t = norm(text);
  return {
    oral: /(сироп|таблет|капсул|капс\.|пастил|леденц|порошок|суспенз|внутрь|оральн)/.test(t),
    nasal: /(назал|в нос|капли в нос|спрей в нос)/.test(t),
    throat: /(горло|спрей для горла|пастил|леденц)/.test(t),
    eye: /(глаз|глазн)/.test(t),
    skin: /(крем|маз|гель|лосьон|сыворотк|маска|пенка|шампунь|флюид|бальзам)/.test(t),
    external: /(наруж|местн|крем|маз|гель|лосьон|сыворотк|маска|пенка|шампунь|флюид|бальзам)/.test(t),
    infusion: /(инфуз|р-р д\/инфуз|раствор д\/инфуз|в\/в)/.test(t),
    injection: /(ампул|инъекц|шприц)/.test(t),
  };
}

function ageHints(text) {
  const t = norm(text);
  return {
    child: /(дет|baby|kid|junior|малыш|младен|0\+|1\+|2\+|3\+)/.test(t),
    adult: /(взросл)/.test(t),
  };
}

function guessProductType(text) {
  const t = norm(text);
  if (/(подгузник|трусики-подгузники|трусики подгузники|трусики|памперс)/.test(t)) return 'infant_hygiene';
  if (/(прокладк|тампон|ежедневк)/.test(t)) return 'female_hygiene';
  if (/(шампунь|пенка|гель д\/умывания|умыван|лосьон|маска д\/лица|сыворотк|крем д\/рук|крем д\/лица|крем для рук|крем для лица|увлажняющ|солнцезащитн|флюид|косметическ)/.test(t)) return 'cosmetic';
  if (/(шприц|игл|катетер|тест[- ]?полоск|тест система|межпальцевый разделитель|ортопед|бинт|пластыр|ингалятор|термометр)/.test(t)) return 'device';
  if (/(витамин|бета-каротин|бета каротин|спирулин|бад|now foods|нау фудс)/.test(t)) return 'supplement';
  if (/(р-р д\/инфуз|инфузи|натрия хлорид|ампул|инъекц)/.test(t)) return 'infusion_drug';
  if (/(таб\.|таблет|капсул|сироп|суспенз|порошок|драже)/.test(t)) return 'drug';
  if (/(закваск|сметан|йогурт|кефир)/.test(t)) return 'food';
  return 'other';
}

function familyCodePrefix(code) {
  const parts = String(code || '').split('_').filter(Boolean);
  if (parts.length >= 2) return parts.slice(0, 2).join('_');
  return parts[0] || '';
}

function blockFamilyFromCategory(c) {
  const level = Number(c.hierarchy_level) || 0;
  if (level <= 2) return c.category_name || familyCodePrefix(c.category_code);
  return familyCodePrefix(c.category_code);
}

function matchesBranch(c, branch) {
  const dir = norm(branch.direction);
  const blockFamily = norm(branch.block_family);
  const familyCode = String(branch.family_code || '').toUpperCase();
  if (dir && norm(c.direction) !== dir) return false;
  if (familyCode && familyCodePrefix(c.category_code).toUpperCase() !== familyCode) return false;
  if (blockFamily) {
    const catBlock = norm(blockFamilyFromCategory(c));
    const catName = norm(c.category_name);
    if (catBlock !== blockFamily && !catName.includes(blockFamily) && !blockFamily.includes(catBlock)) {
      return false;
    }
  }
  return true;
}

return products.map((j, index) => {
  const baseText = norm([j.combined_text, j.product_type_guess].filter(Boolean).join(' '));
  const productTypeGuess = j.product_type_guess || guessProductType(baseText);
  const rh = routeHints(baseText);
  const ah = ageHints(baseText);
  const nosologyHint = norm(j.fallback_2a_nosology_hint || '');

  const branch = {
    direction: j.fallback_2a_direction,
    block_family: j.fallback_2a_block_family,
    family_code: j.fallback_2a_family_code,
  };

  const branchCategories = categories.filter(c => matchesBranch(c, branch));
  const scored = [];

  for (const c of branchCategories) {
    const catCode = (c.category_code || '').toUpperCase();
    let score = 0;
    const reasons = [];

    const categoryTerms = splitTerms(c.category_name);
    const nosologyTerms = splitTerms(c.need_nosology);
    const mnnTerms = splitTerms(c.mnn_cluster);
    const commentTerms = splitTerms(c.inclusion_comment).filter(t => t.length >= 5);

    for (const term of categoryTerms) {
      if (term && baseText.includes(term)) { score += 7; reasons.push(`category:${term}`); }
    }
    for (const term of nosologyTerms) {
      if (term && baseText.includes(term)) { score += 5; reasons.push(`nosology:${term}`); }
    }
    for (const term of mnnTerms) {
      if (term && baseText.includes(term)) { score += 6; reasons.push(`mnn:${term}`); }
    }
    for (const term of commentTerms.slice(0, 8)) {
      if (term && baseText.includes(term)) { score += 2; reasons.push(`comment:${term}`); }
    }

    if (hasAnyWord(baseText, c.include_keywords || [])) { score += 10; reasons.push('include_keywords'); }
    if (hasAnyWord(baseText, c.exclude_keywords || [])) { score -= 12; reasons.push('exclude_keywords'); }

    const ageSegment = norm(c.age_segment);
    const route = norm(c.administration_route);
    if (ageSegment.includes('дет') && ah.child) { score += 4; reasons.push('age:child'); }
    if (ageSegment.includes('взрос') && ah.adult) { score += 4; reasons.push('age:adult'); }
    if (route.includes('назал') && rh.nasal) { score += 5; reasons.push('route:nasal'); }
    if (route.includes('внутрь') && rh.oral) { score += 4; reasons.push('route:oral'); }
    if (route.includes('орофар') && rh.throat) { score += 5; reasons.push('route:throat'); }
    if (route.includes('наруж') && rh.external) { score += 3; reasons.push('route:external'); }
    if (route.includes('глаз') && rh.eye) { score += 5; reasons.push('route:eye'); }

    if (nosologyHint) {
      const needNosology = norm(c.need_nosology);
      if (needNosology && (needNosology.includes(nosologyHint) || nosologyHint.includes(needNosology))) {
        score += 8;
        reasons.push('nosology_hint');
      }
    }

    const hasStrongMatch =
      reasons.some(r => r.startsWith('category:')) ||
      reasons.some(r => r.startsWith('nosology:')) ||
      reasons.some(r => r.startsWith('mnn:')) ||
      reasons.includes('include_keywords') ||
      reasons.includes('nosology_hint');

    if (!hasStrongMatch) score = 0;
    if (score <= 0) continue;

    scored.push({
      category_id: String(c.id),
      category_code: c.category_code,
      category_name: c.category_name,
      score,
      reasons: Array.from(new Set(reasons)).slice(0, 12),
    });
  }

  scored.sort((a, b) => b.score - a.score);
  const branchShortlist = scored.slice(0, 8).map((c, idx) => ({
    rank: idx + 1,
    category_id: c.category_id,
    category_code: c.category_code,
    category_name: c.category_name,
    score: c.score,
    reasons: c.reasons,
  }));

  const skipLlm = branchShortlist.length === 0;

  return {
    json: {
      ...j,
      branch_shortlist_json: branchShortlist,
      branch_shortlist_count: branchShortlist.length,
      branch_filter_count: branchCategories.length,
      skip_llm: skipLlm,
      product_type_guess: productTypeGuess,
      shortlist_metadata: {
        strategy: 'branch_scoped_keywords',
        scope: branch,
        nosology_hint: j.fallback_2a_nosology_hint || null,
        fallback_2a_confidence: j.fallback_2a_confidence ?? null,
        branch_filter_count: branchCategories.length,
        run_id: $('Run — Create Run').first().json.id,
      },
    },
    pairedItem: { item: index },
  };
});
