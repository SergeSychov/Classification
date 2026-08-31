// Sem — Post-process (hierarchy B3 Sem).
// Soft-continue always → next_action=direction_select.
// Never classified. Never persist category_id from Sem.

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

function pickLlmRaw(root) {
  if (root.output !== undefined) return root.output;
  if (root.text !== undefined) return root.text;
  if (root.response !== undefined) return root.response;
  if (root.content !== undefined) return root.content;
  if (root.result !== undefined) return root.result;
  return null;
}

const ATTR_KEYS = [
  'mnn',
  'brand',
  'rx_otc',
  'nosology',
  'administration_route',
  'dosage_form',
  'dosage',
  'age_segment',
  'package_hint',
  'combination_hint',
];

const VITAMIN_NOSOLOGY = new Set([
  'нутрицевтики',
  'парафармацевтики',
  'эубиотики',
  'отдельные нутриенты',
  'комплексные профили',
]);

/** Ordered nutrient patterns: first match wins (more specific first). */
const NUTRIENT_RULES = [
  { out: 'L-метилфолат', re: /l[\s-]*метилфолат|метилфолат|methylfolate/ },
  { out: 'Коэнзим Q10', re: /коэнзим\s*q\s*10|коэнзим\s*q10|coq10|убихинон/ },
  { out: 'Омега-3', re: /омега[\s-]*3|omega[\s-]*3|омега\s*3/ },
  { out: 'Псиллиум', re: /псиллиум|псилли?ум|psyllium|подорожник\s+яйцевид/ },
  { out: 'Куркумин', re: /куркумин|curcumin/ },
  { out: 'Коллаген', re: /коллаген|collagen/ },
  { out: 'Таурин', re: /таурин(?!\s*табс)|таурин\b/ },
  { out: 'Лецитин', re: /лецитин/ },
  { out: 'Хром', re: /\bхром\b|chromium/ },
  { out: 'Лютеин', re: /лютеин/ },
  { out: 'МСМ', re: /\bмсм\b|\bmsm\b/ },
  { out: 'Аскорбиновая кислота', re: /аскорбин|витамин\s*c\b|ascorb/ },
];

const MULTI_VITAMIN_BRANDS =
  /компливит|алфавит|супрадин|daily\s*vits|мультивитам|поливитам|витаминно[\s-]*минеральн|нейчес\s+баунти|nature'?s\s+bounty/i;

function foldText(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeRxOtc(raw, productKind) {
  if (productKind && productKind !== 'drug') return 'не применимо';
  const t = foldText(raw);
  if (!t) return null;
  if (
    t === 'rx' ||
    /^(рецептурн|по\s+рецепту)/.test(t) ||
    t.includes('рецептурн') ||
    /\bпо\s+рецепту\b/.test(t)
  ) {
    if (/без\s*рецепт|безрецептур|otc|овер/.test(t) && !/по\s+рецепту|рецептурн/.test(t)) {
      return 'otc';
    }
    if (/без\s*рецепт|безрецептур/.test(t)) return 'otc';
    return 'rx';
  }
  if (
    t === 'otc' ||
    /без\s*рецепт|безрецептур|овер[\s-]*каунтер|over[\s-]*the[\s-]*counter/.test(t)
  ) {
    return 'otc';
  }
  if (t === 'не применимо' || t === 'n/a' || t === 'na' || t === 'unknown') return null;
  return null;
}

function detectNutrientInText(text) {
  const t = foldText(text);
  if (!t) return null;
  for (const rule of NUTRIENT_RULES) {
    if (rule.re.test(t)) return rule.out;
  }
  return null;
}

function countNutrientHits(text) {
  const t = foldText(text);
  let n = 0;
  for (const rule of NUTRIENT_RULES) {
    if (rule.re.test(t)) n += 1;
  }
  return n;
}

function mnnGroundedInText(mnn, text) {
  const m = foldText(mnn);
  const t = foldText(text);
  if (!m || !t) return false;
  if (m === 'комплекс') return true;
  // Require a substantial token from mnn to appear in text (avoid brand→random INN).
  const tokens = m
    .split(/[^a-zа-я0-9+]+/i)
    .map((x) => x.trim())
    .filter((x) => x.length >= 4);
  if (tokens.length === 0) {
    // short codes like B12, D3
    return /\b[bв]?[0-9]{1,2}\b|\b[aadeкk]\b/i.test(m) ? t.includes(m.replace(/\s/g, '')) || /витамин/.test(t) : t.includes(m);
  }
  return tokens.some((tok) => t.includes(tok));
}

function looksLikeNutrientLabel(s) {
  const t = foldText(s);
  if (!t) return false;
  if (/^витамин\b|^vitamin\b/.test(t)) return true;
  if (/^(b|в)\s*-?\s*\d+|фолиев|омега|ретинол|токоферол|аскорбин/.test(t)) return true;
  if (t === 'комплекс') return true;
  return false;
}

function normalizeVitaminNosology(raw) {
  const t = foldText(raw);
  if (!t) return null;
  for (const allowed of VITAMIN_NOSOLOGY) {
    if (t === foldText(allowed)) return allowed;
  }
  if (/эубиот|пробиот|пребиот|синбиот/.test(t)) return 'эубиотики';
  if (/парафарм/.test(t)) return 'парафармацевтики';
  if (/нутрицевт|бад|биодобав/.test(t)) return 'нутрицевтики';
  if (/комплексн|мультивитам|поливитам/.test(t)) return 'комплексные профили';
  if (/отдельн|моно|нутриент|витамин/.test(t)) return 'отдельные нутриенты';
  return null;
}

function normalizeCombinationHint(raw, mode) {
  const t = foldText(raw);
  if (mode === 'mono') return 'монокомпонентный';
  if (mode === 'multi_brand') return 'многокомпонентный витаминно-минеральный комплекс';
  if (mode === 'combo') {
    if (/монокомпонент|монопрепарат|моно\b/.test(t)) return 'комбинированный';
    if (/многокомпонентн.*витамин|витаминно[\s-]*минеральн/.test(t)) {
      return 'многокомпонентный витаминно-минеральный комплекс';
    }
    if (/многокомпонентн/.test(t)) return 'многокомпонентный комплекс';
    if (/комбинир|комплекс/.test(t) || !t) return 'комбинированный';
    // Drop free-text like «лецитин + расторопша» / «черника + лютеин»
    if (/\+|и\s+/.test(t) && t.length < 60) return 'комбинированный';
    return 'комбинированный';
  }
  return safeText(raw);
}

function enforceVitaminNosologyAndMnn(attrs, textHint) {
  let nos = safeText(attrs.nosology);
  let mnn = safeText(attrs.mnn);
  let combo = safeText(attrs.combination_hint);
  const text = foldText(textHint || '') + ' ' + foldText(mnn) + ' ' + foldText(attrs.brand);

  if (nos && looksLikeNutrientLabel(nos) && !VITAMIN_NOSOLOGY.has(foldText(nos))) {
    if (!mnn) mnn = nos;
    const isComplex = /комплекс|мульти|поливитам/i.test(nos);
    nos = isComplex ? 'комплексные профили' : 'отдельные нутриенты';
  }
  const mapped = normalizeVitaminNosology(nos);
  if (nos && !mapped) {
    nos = mnn && /комплекс/i.test(mnn) ? 'комплексные профили' : 'нутрицевтики';
  } else if (mapped) {
    nos = mapped;
  }

  const nutrient = detectNutrientInText(textHint || text);
  const hits = countNutrientHits(textHint || text);
  const isMultiBrand = MULTI_VITAMIN_BRANDS.test(textHint || text);

  if (isMultiBrand && hits !== 1) {
    mnn = 'Комплекс';
    combo = normalizeCombinationHint(combo, 'multi_brand');
    if (!nos || nos === 'нутрицевтики') nos = 'комплексные профили';
  } else if (nutrient && (hits === 1 || !mnn || foldText(mnn) === 'комплекс')) {
    // Prefer explicit single nutrient over bare «Комплекс».
    if (hits <= 1 || foldText(mnn) === 'комплекс' || !mnn) {
      mnn = nutrient;
      combo = normalizeCombinationHint(combo, hits > 1 ? 'combo' : 'mono');
      if (hits <= 1 && (!nos || nos === 'комплексные профили')) nos = 'отдельные нутриенты';
    }
  } else if (foldText(mnn) === 'комплекс' || (!mnn && hits >= 2)) {
    mnn = 'Комплекс';
    combo = normalizeCombinationHint(combo, isMultiBrand ? 'multi_brand' : 'combo');
    if (!nos) nos = 'комплексные профили';
  } else if (mnn && hits <= 1 && nutrient && foldText(mnn) === foldText(nutrient)) {
    combo = normalizeCombinationHint(combo, 'mono');
  } else if (combo) {
    // Normalize free-form combo labels when already set
    if (/монокомпонент|монопрепарат|без\s+добавок|моно\b/.test(foldText(combo))) {
      combo = 'монокомпонентный';
    } else if (/многокомпонентн.*витамин|витаминно[\s-]*минеральн/.test(foldText(combo))) {
      combo = 'многокомпонентный витаминно-минеральный комплекс';
    } else if (/многокомпонентн/.test(foldText(combo))) {
      combo = 'многокомпонентный комплекс';
    } else if (/комбинир|комплекс|\+/.test(foldText(combo))) {
      combo = 'комбинированный';
    }
  }

  attrs.nosology = nos;
  attrs.mnn = mnn;
  attrs.combination_hint = combo;
}

function enforceDrugMnnGrounding(attrs, text) {
  const mnn = safeText(attrs.mnn);
  if (!mnn) return;
  if (!mnnGroundedInText(mnn, text)) {
    attrs.mnn = null;
  }
}

return items.map((item, index) => {
  const root = item.json || {};
  const ctx = root.context || {};
  const C = root.constants || {};

  const WORKFLOW_VERSION = root.workflow_version || 'stage2_hierarchy_v1';
  const PROMPT_VERSION = 'prompt_semantic_v5';
  const STAGE = (C.stage && C.stage.semantic_primary) || 'semantic_primary';
  const productKind = safeText(root.product_kind) || 'other';
  const productFamily = safeText(root.product_family);
  const medicalDeviceProfile = safeText(root.medical_device_profile);
  const productKindGroupHint = safeText(root.product_kind_group_hint);
  const attrProfile =
    root.attr_profile && typeof root.attr_profile === 'object' && !Array.isArray(root.attr_profile)
      ? root.attr_profile
      : {};
  const DECISION_PENDING =
    (C.decision_status && C.decision_status.pending_fallback) || 'pending_fallback';
  const NEXT_DIR =
    (C.next_action && C.next_action.direction_select) || 'direction_select';
  const ACTOR_LLM = (C.actor_type && C.actor_type.llm) || 'llm';
  const LOG = C.log_status || {
    success: 'success',
    rejected: 'rejected',
    needs_review: 'needs_review',
  };
  const MODEL_NAME =
    (C.model && C.model.cascade_actor_name) ||
    (C.model && C.model.primary_actor_name) ||
    'deepseek-chat';

  const raw = pickLlmRaw(root);
  const parsed = safeParseJson(raw);

  let validationPassed = false;
  let rejectReason = null;
  let semanticAttrs = null;
  let semanticConfidence = null;
  let semanticExplanation = null;
  let logStatus = LOG.rejected || 'rejected';

  if (!parsed.ok) {
    rejectReason = parsed.error || 'empty_output';
  } else if (!parsed.parsed || typeof parsed.parsed !== 'object' || Array.isArray(parsed.parsed)) {
    rejectReason = 'invalid_shape';
  } else {
    const obj = parsed.parsed;
    const forbiddenCat = obj.category_id;
    if (forbiddenCat !== undefined && forbiddenCat !== null && String(forbiddenCat).trim() !== '') {
      rejectReason = 'category_id_forbidden';
    } else if (
      obj.direction !== undefined &&
      obj.direction !== null &&
      String(obj.direction).trim() !== ''
    ) {
      rejectReason = 'direction_forbidden';
    } else if (obj.need !== undefined && obj.need !== null && String(obj.need).trim() !== '') {
      rejectReason = 'need_forbidden';
    } else {
      const conf = normalizeConfidence(obj.confidence);
      const explanation = safeText(obj.explanation);
      if (conf === null) {
        rejectReason = 'invalid_confidence';
      } else if (explanation === null) {
        // soft-continue per migration: missing explanation only
        rejectReason = 'missing_explanation';
        semanticConfidence = conf;
        semanticAttrs = {};
        for (const key of ATTR_KEYS) {
          if (key === 'rx_otc') {
            semanticAttrs.rx_otc = normalizeRxOtc(obj.rx_otc, productKind);
          } else {
            semanticAttrs[key] = safeText(obj[key]);
          }
        }
        semanticExplanation = null;
        validationPassed = false;
        logStatus = LOG.needs_review || 'needs_review';
      } else {
        semanticConfidence = conf;
        semanticExplanation = explanation;
        semanticAttrs = {};
        for (const key of ATTR_KEYS) {
          if (key === 'rx_otc') {
            semanticAttrs.rx_otc = normalizeRxOtc(obj.rx_otc, productKind);
          } else {
            semanticAttrs[key] = safeText(obj[key]);
          }
        }
        validationPassed = true;
        rejectReason = null;
        logStatus = LOG.success || 'success';
      }
    }
  }

  // Enforce Sem0 attr_profile + kind-specific hard-nulls (policy rules patch).
  if (semanticAttrs && typeof semanticAttrs === 'object') {
    for (const key of ATTR_KEYS) {
      if (attrProfile[key] === 'not_applicable') {
        semanticAttrs[key] = null;
      }
    }
    const textHint = root.normalized_text || root.combined_text || '';
    if (productKind === 'vitamin_or_baa') {
      semanticAttrs.rx_otc = 'не применимо';
      enforceVitaminNosologyAndMnn(semanticAttrs, textHint);
    } else if (productKind === 'medical_device') {
      semanticAttrs.mnn = null;
      semanticAttrs.rx_otc = 'не применимо';
      semanticAttrs.nosology = null;
      semanticAttrs.combination_hint = null;
    } else if (productKind === 'cosmetic_hygiene') {
      semanticAttrs.mnn = null;
      semanticAttrs.rx_otc = 'не применимо';
      semanticAttrs.nosology = null;
      semanticAttrs.dosage = null;
      semanticAttrs.combination_hint = null;
      // route / form allowed when attr_profile says applicable (policy v3).
    } else if (productKind === 'drug') {
      enforceDrugMnnGrounding(semanticAttrs, textHint);
      semanticAttrs.rx_otc = normalizeRxOtc(semanticAttrs.rx_otc, 'drug');
    } else {
      // other
      semanticAttrs.rx_otc = 'не применимо';
    }
    semanticAttrs.product_kind = productKind;
    semanticAttrs.product_family = productFamily;
    semanticAttrs.attr_profile = attrProfile;
    if (medicalDeviceProfile) semanticAttrs.medical_device_profile = medicalDeviceProfile;
    if (productKindGroupHint) semanticAttrs.product_kind_group_hint = productKindGroupHint;
  }

  // Always soft-continue to Dir seam; never classified at Sem.
  const decisionStatus = DECISION_PENDING;
  const nextAction = NEXT_DIR;

  const prevTrace =
    root.cascade_trace && typeof root.cascade_trace === 'object' && !Array.isArray(root.cascade_trace)
      ? root.cascade_trace
      : {};
  const path = Array.isArray(prevTrace.path) ? [...prevTrace.path] : [];
  if (!path.includes(STAGE)) path.push(STAGE);
  const stages = Array.isArray(prevTrace.stages) ? [...prevTrace.stages] : [];
  stages.push({
    stage: STAGE,
    actor_type: ACTOR_LLM,
    actor_name: MODEL_NAME,
    validation_passed: validationPassed,
    reject_reason: rejectReason,
    notes: 'semantic_primary_v5',
  });

  const routingHint = {
    sem_soft_continue: true,
    semantic_validation_passed: validationPassed,
    semantic_reject_reason: rejectReason,
    next_stage: NEXT_DIR,
  };

  return {
    json: {
      ...root,
      workflow_version: WORKFLOW_VERSION,
      prompt_version: PROMPT_VERSION,
      stage: STAGE,
      actor_type: ACTOR_LLM,
      actor_name: MODEL_NAME,
      semantic_attrs: semanticAttrs,
      semantic_confidence: semanticConfidence,
      semantic_explanation: semanticExplanation,
      semantic_raw_json: parsed.raw_text
        ? { raw_text: parsed.raw_text, parsed: parsed.parsed }
        : raw !== null && raw !== undefined
          ? { raw: raw }
          : null,
      semantic_validation_passed: validationPassed,
      semantic_reject_reason: rejectReason,
      decision_status: decisionStatus,
      next_action: nextAction,
      routing_hint: routingHint,
      log_status: logStatus,
      // Explicit: Sem never sets category
      selected_category_id: null,
      cascade_trace: {
        ...prevTrace,
        path,
        stages,
      },
    },
    pairedItem: index,
  };
});
