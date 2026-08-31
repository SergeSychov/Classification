// Sem0 — Post-process (product_kind / attr_profile). Policy v3.
// Soft-continue always into Sem1. On failure: product_kind=other, all attrs applicable.

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

const KIND_ALLOWED = new Set([
  'drug',
  'vitamin_or_baa',
  'medical_device',
  'cosmetic_hygiene',
  'other',
]);

const DEVICE_HYGIENE_FAMILIES = new Set(['Гигиена и косметика', 'Товары для мам и детей']);

const DEVICE_CLINICAL_FAMILIES = new Set([
  'Измерительные приборы',
  'Приборы для терапии',
  'Приборы и средства для инъекций',
  'Перевязочные материалы',
  'Пластыри',
  'Другое медизделие',
]);

const STAGE = 'product_kind_select';

function allApplicableProfile() {
  const out = {};
  for (const k of ATTR_KEYS) out[k] = 'applicable';
  return out;
}

function normalizeAttrProfile(raw) {
  const src = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const out = {};
  for (const k of ATTR_KEYS) {
    const v = String(src[k] || '').trim().toLowerCase();
    out[k] = v === 'not_applicable' ? 'not_applicable' : 'applicable';
  }
  return out;
}

function profileFromSpec(spec) {
  const out = {};
  for (const k of ATTR_KEYS) {
    out[k] = spec[k] === 'not_applicable' ? 'not_applicable' : 'applicable';
  }
  return out;
}

function classifyMedicalDeviceProfile(family) {
  const f = safeText(family);
  if (!f) return null;
  if (DEVICE_HYGIENE_FAMILIES.has(f)) return 'hygiene_like';
  if (DEVICE_CLINICAL_FAMILIES.has(f)) return 'clinical_like';
  return null;
}

/** Named injectable drug brands / pen products (keep as drug). */
const INJECTABLE_DRUG_BRANDS =
  /туджео|тресиба|новорапид|новомикс|велгия|гонал|теваграстим|метортрит|хумалог|лантус|левомир|апидра|фиасп|оземпик|саксенда|виктоза|трулисити|дулага|форсига|джардинс|инсуман|актрапид|протафан|хумулин|генсулин|ринсулин|биосулин|розинсулин/i;

function hasInjectableDrugSignal(text) {
  if (INJECTABLE_DRUG_BRANDS.test(text)) return true;
  // Solution for injection + concentration units typical of filled pens/syringes.
  const hasSolution =
    /р-р|раствор|лиофил|картридж\s+в\s+шприц|шприц[\s-]*ручк/.test(text) &&
    !/^(шприц|игла)(?:\s|[.,]|$)/.test(text.trim());
  const hasDrugDose =
    /\d+([.,]\d+)?\s*(ед|ме|млн\.?\s*ме|мг|мкг)\s*\/\s*(мл|доза)/i.test(text) ||
    /\d+\s*млн\.?\s*ме/i.test(text);
  return hasSolution && hasDrugDose;
}

function isEmptySyringeOrNeedle(text) {
  const t = text.trim();
  // Avoid JS \b with Cyrillic (\\b is ASCII-word only).
  const deviceLead =
    /^(шприц|игла)(?:\s|[.,]|$)/.test(t) ||
    /шприц\s+инсулин|шприц\s+однораз|шприц\s+инекта|игла\s+(для|sfm|ime|универсал|инъекц)/.test(
      t
    );
  if (!deviceLead) return false;
  // Explicit drug brand / filled pen → not empty device.
  if (hasInjectableDrugSignal(text)) return false;
  // Volume-only (мл) / gauge (G) / U-40/U-100 scale are device specs, not drug dose.
  return true;
}

/** Heuristic kind corrections after model output (policy v3 rules patch). */
function correctProductKind(kind, family, textRaw) {
  const text = String(textRaw || '')
    .toLowerCase()
    .replace(/ё/g, 'е');
  if (!text) return { kind, family, note: null };

  // Pediculicide / anti-lice → other (not cosmetic).
  if (/педикулиц|от\s+вшей|против\s+вшей|средство\s+педикул|вши\b/.test(text)) {
    return { kind: 'other', family: null, note: 'kind_fix:pediculicide_other' };
  }

  // Empty syringe / needle / insulin syringe device → medical_device (even if LLM said drug).
  if (isEmptySyringeOrNeedle(text) && kind !== 'medical_device') {
    return {
      kind: 'medical_device',
      family: 'Приборы и средства для инъекций',
      note: 'kind_fix:empty_syringe_device',
    };
  }

  // Prefilled drug pen/syringe with named drug or solution+concentration → drug.
  if (
    hasInjectableDrugSignal(text) &&
    /шприц|картридж|ручк/.test(text) &&
    (kind === 'medical_device' || kind === 'other' || kind === 'cosmetic_hygiene')
  ) {
    return {
      kind: 'drug',
      family: family && String(family).trim() ? family : 'Инъекции',
      note: 'kind_fix:syringe_drug',
    };
  }

  // Herbal filter-packs / leaves without clear mg drug dose → vitamin_or_baa.
  const herbalPack =
    /(ф\s*\/\s*п|фильтр[\s-]*пакет|листья|листья|трава|фиточай|настойка)/.test(text) &&
    !/\d+\s*мг\b/.test(text) &&
    !/лиофил|р-р\s+д\/ин|раствор\s+для\s+ин/.test(text);
  if (kind === 'drug' && herbalPack) {
    return { kind: 'vitamin_or_baa', family: family || 'фито', note: 'kind_fix:herbal_baa' };
  }

  // Capsule/tablet supplement-looking with foreign brand + мг №N and kind=other → vitamin_or_baa.
  if (
    kind === 'other' &&
    /(капс|табл|таб\.)/.test(text) &&
    /\d+\s*мг/.test(text) &&
    !/р-р\s+д\/|лиофил|шприц/.test(text)
  ) {
    return { kind: 'vitamin_or_baa', family: family || null, note: 'kind_fix:caps_baa' };
  }

  return { kind, family, note: null };
}

function applyPolicyOverlay(kind, family, rawProfile) {
  const base = normalizeAttrProfile(rawProfile);
  let medicalDeviceProfile = null;
  let productKindGroupHint = kind;

  if (kind === 'vitamin_or_baa') {
    return {
      attrProfile: profileFromSpec({
        mnn: 'applicable',
        brand: 'applicable',
        rx_otc: 'not_applicable',
        nosology: 'applicable',
        administration_route: 'applicable',
        dosage_form: 'applicable',
        dosage: 'applicable',
        age_segment: 'applicable',
        package_hint: 'applicable',
        combination_hint: 'applicable',
      }),
      medicalDeviceProfile: null,
      productKindGroupHint: 'vitamin_or_baa',
    };
  }

  if (kind === 'cosmetic_hygiene') {
    return {
      attrProfile: profileFromSpec({
        mnn: 'not_applicable',
        brand: 'applicable',
        rx_otc: 'not_applicable',
        nosology: 'not_applicable',
        administration_route: 'applicable',
        dosage_form: 'applicable',
        dosage: 'not_applicable',
        age_segment: 'applicable',
        package_hint: 'applicable',
        combination_hint: 'not_applicable',
      }),
      medicalDeviceProfile: null,
      productKindGroupHint: 'cosmetic_hygiene',
    };
  }

  if (kind === 'medical_device') {
    medicalDeviceProfile = classifyMedicalDeviceProfile(family);
    // Fallback: if family unknown, prefer clinical_like when route/form marked applicable by model.
    if (!medicalDeviceProfile) {
      const clinicalSignal =
        base.administration_route === 'applicable' ||
        base.dosage_form === 'applicable' ||
        base.dosage === 'applicable';
      medicalDeviceProfile = clinicalSignal ? 'clinical_like' : 'hygiene_like';
    }
    productKindGroupHint = `medical_device:${medicalDeviceProfile}`;
    if (medicalDeviceProfile === 'hygiene_like') {
      return {
        attrProfile: profileFromSpec({
          mnn: 'not_applicable',
          brand: 'applicable',
          rx_otc: 'not_applicable',
          nosology: 'not_applicable',
          administration_route: 'not_applicable',
          dosage_form: 'not_applicable',
          dosage: 'not_applicable',
          age_segment: 'applicable',
          package_hint: 'applicable',
          combination_hint: 'not_applicable',
        }),
        medicalDeviceProfile,
        productKindGroupHint,
      };
    }
    return {
      attrProfile: profileFromSpec({
        mnn: 'not_applicable',
        brand: 'applicable',
        rx_otc: 'not_applicable',
        nosology: 'not_applicable',
        administration_route: 'applicable',
        dosage_form: 'applicable',
        dosage: 'applicable',
        age_segment: 'applicable',
        package_hint: 'applicable',
        combination_hint: 'not_applicable',
      }),
      medicalDeviceProfile,
      productKindGroupHint,
    };
  }

  if (kind === 'drug') {
    return {
      attrProfile: base,
      medicalDeviceProfile: null,
      productKindGroupHint: 'drug',
    };
  }

  // other: keep model profile (soft), after normalize
  return {
    attrProfile: base,
    medicalDeviceProfile: null,
    productKindGroupHint: 'other',
  };
}

return items.map((item, index) => {
  const root = item.json || {};
  const C = root.constants || {};
  const ACTOR_LLM = (C.actor_type && C.actor_type.llm) || 'llm';
  const MODEL_NAME =
    (C.model && C.model.cascade_actor_name) ||
    (C.model && C.model.primary_actor_name) ||
    'deepseek-chat';

  const raw = pickLlmRaw(root);
  const parsed = safeParseJson(raw);

  let validationPassed = false;
  let rejectReason = null;
  let productKind = 'other';
  let productFamily = null;
  let attrProfile = allApplicableProfile();
  let medicalDeviceProfile = null;
  let productKindGroupHint = 'other';
  let confidence = null;
  let explanation = null;

  if (!parsed.ok) {
    rejectReason = parsed.error || 'empty_output';
  } else if (!parsed.parsed || typeof parsed.parsed !== 'object' || Array.isArray(parsed.parsed)) {
    rejectReason = 'invalid_shape';
  } else {
    const obj = parsed.parsed;
    if (obj.category_id !== undefined && obj.category_id !== null && String(obj.category_id).trim() !== '') {
      rejectReason = 'category_id_forbidden';
    } else if (obj.direction !== undefined && obj.direction !== null && String(obj.direction).trim() !== '') {
      rejectReason = 'direction_forbidden';
    } else if (obj.need !== undefined && obj.need !== null && String(obj.need).trim() !== '') {
      rejectReason = 'need_forbidden';
    } else {
      const kind = safeText(obj.product_kind);
      const conf = normalizeConfidence(obj.confidence);
      const expl = safeText(obj.explanation);
      if (!kind || !KIND_ALLOWED.has(kind)) {
        rejectReason = 'invalid_product_kind';
      } else if (conf === null) {
        rejectReason = 'invalid_confidence';
      } else if (expl === null) {
        rejectReason = 'missing_explanation';
        productKind = kind;
        productFamily = safeText(obj.product_family);
        const overlay = applyPolicyOverlay(kind, productFamily, obj.attr_profile);
        attrProfile = overlay.attrProfile;
        medicalDeviceProfile = overlay.medicalDeviceProfile;
        productKindGroupHint = overlay.productKindGroupHint;
        confidence = conf;
      } else {
        productKind = kind;
        productFamily = safeText(obj.product_family);
        const overlay = applyPolicyOverlay(kind, productFamily, obj.attr_profile);
        attrProfile = overlay.attrProfile;
        medicalDeviceProfile = overlay.medicalDeviceProfile;
        productKindGroupHint = overlay.productKindGroupHint;
        confidence = conf;
        explanation = expl;
        validationPassed = true;
        rejectReason = null;
      }
    }
  }

  // Soft-fail: other + all applicable (do not regress drugs when Sem0 breaks).
  if (!validationPassed && rejectReason && rejectReason !== 'missing_explanation') {
    productKind = 'other';
    productFamily = null;
    attrProfile = allApplicableProfile();
    medicalDeviceProfile = null;
    productKindGroupHint = 'other';
  } else if (productKind) {
    const textHint = root.normalized_text || root.combined_text || '';
    const fixed = correctProductKind(productKind, productFamily, textHint);
    if (fixed.note) {
      productKind = fixed.kind;
      productFamily = fixed.family;
      const overlay = applyPolicyOverlay(productKind, productFamily, attrProfile);
      attrProfile = overlay.attrProfile;
      medicalDeviceProfile = overlay.medicalDeviceProfile;
      productKindGroupHint = overlay.productKindGroupHint;
      if (explanation) explanation = `${explanation} [${fixed.note}]`;
    }
  }

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
    notes: 'sem0_v3_rules1',
  });

  const {
    output,
    text,
    response,
    content,
    result,
    llm_raw_output_text,
    prompt_system,
    prompt_user,
    llm_prompt_debug,
    ...rest
  } = root;

  return {
    json: {
      ...rest,
      workflow_version: root.workflow_version || 'stage2_hierarchy_v1',
      prompt_version: 'prompt_sem0_v3',
      stage: STAGE,
      actor_type: ACTOR_LLM,
      actor_name: MODEL_NAME,
      product_kind: productKind,
      product_family: productFamily,
      attr_profile: attrProfile,
      medical_device_profile: medicalDeviceProfile,
      product_kind_group_hint: productKindGroupHint,
      sem0_confidence: confidence,
      sem0_explanation: explanation,
      sem0_validation_passed: validationPassed,
      sem0_reject_reason: rejectReason,
      sem0_raw_json: parsed.raw_text
        ? { raw_text: parsed.raw_text, parsed: parsed.parsed }
        : raw !== null && raw !== undefined
          ? { raw: raw }
          : null,
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
