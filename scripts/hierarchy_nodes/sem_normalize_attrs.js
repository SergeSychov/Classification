// Norm — Normalize Sem attrs (hierarchy-dev only).
// After Sem — Post-process, before Sem — Route / Prepare Log.
// Canonical dictionaries: see sem_attr_dictionaries.md
// Does not invent attrs when signal is absent (except policy fallbacks below).

const ROUTE_ALLOWED = new Set([
  'перорально',
  'наружно',
  'ингаляционно',
  'внутримышечно',
  'внутривенно',
  'подкожно',
  'ректально',
  'сублингвально',
  'офтальмологический',
  'назальный',
  'отологический',
  'инъекционное',
  'не применимо',
]);

const FORM_ALLOWED = new Set([
  'таблетки',
  'таблетки жевательные',
  'капсулы',
  'порошок',
  'гранулы',
  'сироп',
  'суспензия',
  'раствор',
  'лиофилизат',
  'мазь',
  'крем',
  'гель',
  'спрей',
  'аэрозоль',
  'фильтр-пакеты',
  'батончик',
  'смесь',
  'пластырь',
  'капли',
  'не применимо',
]);

const AGE_ALLOWED = new Set(['взрослые', 'дети', 'универсальный', 'не применимо']);

const NA = 'не применимо';

function safeText(v) {
  if (v === undefined || v === null || v === '') return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}

function lower(s) {
  return s == null ? '' : String(s).toLowerCase().replace(/ё/g, 'е');
}

function collapse(s) {
  return lower(s).replace(/\s+/g, ' ').trim();
}

function isNaToken(s) {
  const t = collapse(s);
  return (
    t === 'не применимо' ||
    t === 'n/a' ||
    t === 'na' ||
    t === 'неприменимо' ||
    t === 'не применим' ||
    t === 'неприменим'
  );
}

function profileNotApplicable(attrProfile, key) {
  return attrProfile && attrProfile[key] === 'not_applicable';
}

function forceNaContext(j, attrs, attrProfile) {
  const kind = safeText(j.product_kind) || safeText(attrs.product_kind) || 'other';
  const mdp =
    safeText(j.medical_device_profile) || safeText(attrs.medical_device_profile) || null;
  // cosmetic_hygiene: route/form applicable when signal exists (policy v3) — do not force NA.
  if (kind === 'medical_device' && mdp === 'hygiene_like') return true;
  if (profileNotApplicable(attrProfile, 'administration_route') && profileNotApplicable(attrProfile, 'dosage_form')) {
    return true;
  }
  return false;
}

/** Ordered route rules: first match wins. */
const ROUTE_RULES = [
  { out: 'внутримышечно', re: /внутримыш|в\s*\/\s*м\b|\bвм\b|\bi\.?\s*m\.?\b/ },
  { out: 'внутривенно', re: /внутривен|инфуз|в\s*\/\s*в\b|\bвв\b|\bi\.?\s*v\.?\b/ },
  { out: 'подкожно', re: /подкож|п\s*\/\s*к\b|\bпк\b|\bs\.?\s*c\.?\b/ },
  { out: 'сублингвально', re: /сублингв|под\s+язык/ },
  { out: 'ректально', re: /ректаль|суппозитор/ },
  { out: 'ингаляционно', re: /ингаляц/ },
  { out: 'офтальмологический', re: /офтальм|глазн|в\s+глаз/ },
  { out: 'назальный', re: /назальн|интраназаль|в\s+нос/ },
  { out: 'отологический', re: /отолог|ушн|в\s+ухо|ушной/ },
  { out: 'перорально', re: /пероральн|оральн|внутрь|для\s+приема\s+внутрь|прием\s+внутрь|per\s*os|\bpo\b/ },
  { out: 'наружно', re: /наружн|местн(ое|о|ого)?\s+(применен|использован)|на\s+кожу/ },
  { out: 'инъекционное', re: /инъекц|для\s+инъекц|inject/ },
];

function matchRoute(text) {
  const t = collapse(text);
  if (!t) return null;
  if (ROUTE_ALLOWED.has(t)) return t;
  if (isNaToken(t)) return NA;
  for (const rule of ROUTE_RULES) {
    if (rule.re.test(t)) return rule.out;
  }
  return null;
}

/** Ordered form rules: more specific first. */
const FORM_RULES = [
  { out: 'таблетки жевательные', re: /жеват/ },
  { out: 'фильтр-пакеты', re: /фильтр[\s-]*пакет|ф\s*\/\s*п(?:\b|[.\s]|$)|фиточай/ },
  { out: 'лиофилизат', re: /лиофил/ },
  // Abbreviations like «табл.» / «капс.» — avoid trailing \b after '.'
  { out: 'таблетки', re: /таблет|табл\.?|таб\.(?![а-яa-z])/ },
  { out: 'капсулы', re: /капсул|капс\.?/ },
  { out: 'гранулы', re: /гранул|гран\.?/ },
  { out: 'суспензия', re: /суспенз|сусп\.?/ },
  { out: 'порошок', re: /порош|пор\.(?![а-яa-z])/ },
  { out: 'раствор', re: /раствор|\bр-р\b|\bр\/р\b/ },
  { out: 'сироп', re: /сироп/ },
  { out: 'мазь', re: /мазь/ },
  { out: 'крем', re: /крем/ },
  { out: 'гель', re: /гель/ },
  { out: 'аэрозоль', re: /аэрозол/ },
  { out: 'спрей', re: /спрей/ },
  { out: 'батончик', re: /батончик/ },
  { out: 'пластырь', re: /пластыр|plastyr/ },
  { out: 'капли', re: /капли|кап\.(?![а-яa-z])/ },
  { out: 'смесь', re: /смесь|смеси/ },
];

function matchForm(text) {
  const t = collapse(text);
  if (!t) return null;
  if (FORM_ALLOWED.has(t)) return t;
  if (isNaToken(t)) return NA;
  // Cosmetic bath salt etc. → NA when form is non-pharm cosmetic wording
  if (/соль\s+.*ванн|для\s+ванн|морская\s+соль/.test(t) && !/таблет|капс|раствор|порош/.test(t)) {
    return NA;
  }
  for (const rule of FORM_RULES) {
    if (rule.re.test(t)) return rule.out;
  }
  return null;
}

function matchAge(text) {
  const t = collapse(text);
  if (!t) return null;
  if (AGE_ALLOWED.has(t)) return t;
  if (isNaToken(t)) return NA;

  const hasKids =
    /(?:^|[^а-яa-z])(?:детск|дети|для\s+детей|ребен|ребёнок|ребенок|infant|kids?|child)/.test(
      t
    ) ||
    /\d+\s*[-–—]\s*\d+\s*(лет|мес|года|год)/.test(t) ||
    /\d+\s*(мес|лет)\+/.test(t) ||
    /с\s+\d+\s*(мес|лет)/.test(t) ||
    /0\s*[-–—]\s*\d+\s*мес/.test(t) ||
    /старше\s+\d+\s*(лет|мес)/.test(t);
  const hasAdults = /для\s+взрослых|adults?|взрослый|взрослые/.test(t);
  if (hasKids && hasAdults) return 'универсальный';
  if (hasKids) return 'дети';
  if (hasAdults) return 'взрослые';
  if (/универсал|вся\s+семья|любой\s+возраст|для\s+всей\s+семьи/.test(t)) {
    return 'универсальный';
  }
  return null;
}

function hintText(j, attrs) {
  return [
    j.normalized_text,
    j.combined_text,
    attrs && attrs.dosage_form,
    attrs && attrs.administration_route,
    attrs && attrs.age_segment,
  ]
    .filter(Boolean)
    .join(' | ');
}

function normRoute(raw, ctx) {
  const { forceNa, textHints, productKind, medicalDeviceProfile } = ctx;
  if (forceNa || profileNotApplicable(ctx.attrProfile, 'administration_route')) return NA;
  if (raw != null && ROUTE_ALLOWED.has(collapse(raw))) return collapse(raw);
  if (isNaToken(raw)) return NA;

  const fromRaw = matchRoute(raw);
  if (fromRaw) return fromRaw;

  // clinical_like syringe / injectables without explicit route
  if (productKind === 'medical_device' && medicalDeviceProfile === 'clinical_like') {
    const h = collapse(textHints);
    if (/шприц/.test(h)) return 'инъекционное';
    if (/пластыр/.test(h)) return 'наружно';
  }

  const fromHint = matchRoute(textHints);
  if (fromHint) return fromHint;

  // vitamin_or_baa oral forms → перорально when form signal exists
  if (productKind === 'vitamin_or_baa') {
    const formHit = matchForm(textHints);
    if (
      formHit &&
      [
        'таблетки',
        'таблетки жевательные',
        'капсулы',
        'порошок',
        'гранулы',
        'сироп',
        'суспензия',
        'раствор',
        'батончик',
        'капли',
        'смесь',
      ].includes(formHit)
    ) {
      return 'перорально';
    }
  }

  // Do not invent for drug / other when no signal
  return null;
}

function normForm(raw, ctx) {
  const { forceNa, textHints, productKind, medicalDeviceProfile } = ctx;
  if (forceNa || profileNotApplicable(ctx.attrProfile, 'dosage_form')) return NA;
  if (raw != null && FORM_ALLOWED.has(collapse(raw))) return collapse(raw);
  if (isNaToken(raw)) return NA;

  const fromRaw = matchForm(raw);
  if (fromRaw) return fromRaw;

  if (productKind === 'medical_device' && medicalDeviceProfile === 'clinical_like') {
    const h = collapse(textHints);
    if (/пластыр/.test(h)) return 'пластырь';
    // шприц is not in form dictionary → leave null (route carries injectables)
  }

  const fromHint = matchForm(textHints);
  if (fromHint) return fromHint;

  return null;
}

function normAge(raw, ctx) {
  const { forceNa, textHints, productKind, attrProfile } = ctx;
  if (profileNotApplicable(attrProfile, 'age_segment')) return NA;
  if (raw != null && AGE_ALLOWED.has(collapse(raw))) return collapse(raw);
  if (isNaToken(raw)) return NA;

  const fromRaw = matchAge(raw);
  if (fromRaw) return fromRaw;

  const fromHint = matchAge(textHints);
  if (fromHint) return fromHint;

  // hygiene / tool without age binding
  if (forceNa) return NA;

  // BAA policy: no signal → универсальный
  if (productKind === 'vitamin_or_baa') return 'универсальный';

  // drug: no invent
  return null;
}

function normRxOtc(raw, productKind) {
  if (productKind && productKind !== 'drug') return 'не применимо';
  const t = collapse(raw);
  if (!t) return null;
  if (t === 'rx' || t === 'otc' || t === 'не применимо') return t;
  if (/без\s*рецепт|безрецептур|^otc$|овер/.test(t)) return 'otc';
  if (/рецептур|^rx$|по\s+рецепту/.test(t)) return 'rx';
  return null;
}

return items.map((item, index) => {
  const j = item.json || {};
  const attrs =
    j.semantic_attrs && typeof j.semantic_attrs === 'object' && !Array.isArray(j.semantic_attrs)
      ? { ...j.semantic_attrs }
      : {};
  const attrProfile =
    (attrs.attr_profile && typeof attrs.attr_profile === 'object' && !Array.isArray(attrs.attr_profile)
      ? attrs.attr_profile
      : null) ||
    (j.attr_profile && typeof j.attr_profile === 'object' && !Array.isArray(j.attr_profile)
      ? j.attr_profile
      : {}) ||
    {};

  const productKind = safeText(j.product_kind) || safeText(attrs.product_kind) || 'other';
  const medicalDeviceProfile =
    safeText(j.medical_device_profile) || safeText(attrs.medical_device_profile) || null;
  const forceNa = forceNaContext(j, attrs, attrProfile);
  const textHints = hintText(j, attrs);

  const rawRoute = attrs.administration_route ?? j.attr_administration_route ?? null;
  const rawForm = attrs.dosage_form ?? j.attr_dosage_form ?? null;
  const rawAge = attrs.age_segment ?? j.attr_age_segment ?? null;
  const rawRx = attrs.rx_otc ?? j.attr_rx_otc ?? null;

  const ctx = {
    forceNa,
    textHints,
    productKind,
    medicalDeviceProfile,
    attrProfile,
  };

  const route = normRoute(rawRoute, ctx);
  const form = normForm(rawForm, ctx);
  const age = normAge(rawAge, ctx);
  const rxOtc = normRxOtc(rawRx, productKind);

  const semanticAttrsNext = {
    ...attrs,
    administration_route: route,
    dosage_form: form,
    age_segment: age,
    rx_otc: rxOtc,
  };

  return {
    json: {
      ...j,
      semantic_attrs: semanticAttrsNext,
      attr_administration_route: route,
      attr_dosage_form: form,
      attr_age_segment: age,
      attr_rx_otc: rxOtc,
      // Keep pre-norm for smoke/debug (not consumed by Prepare Log contract).
      sem_attr_norm_meta: {
        administration_route_raw: safeText(rawRoute),
        dosage_form_raw: safeText(rawForm),
        age_segment_raw: safeText(rawAge),
        rx_otc_raw: safeText(rawRx),
        administration_route: route,
        dosage_form: form,
        age_segment: age,
        rx_otc: rxOtc,
      },
    },
    pairedItem: item.pairedItem !== undefined ? item.pairedItem : index,
  };
});
