// Enrichment — Post-process (offline MNN/RX enrichment, prompt_enrichment_v1).
// Parses Qwen JSON → mnn_enriched / rx_otc_enriched / combination_hint_enriched.
// Does NOT rewrite attr_mnn / attr_rx_otc baseline.

const RX_CANON = new Set(['rx', 'otc', 'unknown', 'не применимо']);
const COMBO_CANON = new Set(['monocomponent', 'multicomponent', 'unknown']);

const NUTRIENT_RULES = [
  { out: 'L-метилфолат', re: /l[\s-]*метилфолат|метилфолат|methylfolate/i },
  { out: 'Коэнзим Q10', re: /коэнзим\s*q\s*10|коэнзим\s*q10|coq10|убихинон/i },
  { out: 'Омега-3', re: /омега[\s-]*3|omega[\s-]*3|омега\s*3/i },
  { out: 'Псиллиум', re: /псиллиум|псилли?ум|psyllium|подорожник\s+яйцевид/i },
  { out: 'Куркумин', re: /куркумин|curcumin/i },
  { out: 'Коллаген', re: /коллаген|collagen/i },
  { out: 'Таурин', re: /таурин(?!\s*табс)|таурин\b/i },
  { out: 'Лецитин', re: /лецитин/i },
  { out: 'Хром', re: /\bхром\b|chromium/i },
  { out: 'Лютеин', re: /лютеин/i },
  { out: 'МСМ', re: /\bмсм\b|\bmsm\b/i },
  { out: 'Аскорбиновая кислота', re: /аскорбин|витамин\s*c\b|ascorb/i },
];

const MULTI_VITAMIN_BRANDS =
  /компливит|алфавит|супрадин|daily\s*vits|мультивитам|поливитам|витаминно[\s-]*минеральн|нейчес\s+баунти|nature'?s\s+bounty/i;

const RX_BASELINE_CANON = new Set(['rx', 'otc', 'не применимо']);

function foldText(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/\s+/g, ' ')
    .trim();
}

function nutrientHit(text) {
  const t = String(text || '');
  for (const rule of NUTRIENT_RULES) {
    if (rule.re.test(t)) return rule.out;
  }
  return null;
}

function isMultiVitaminBrand(text) {
  return MULTI_VITAMIN_BRANDS.test(String(text || ''));
}

/** Eligibility for offline enrichment filter. Returns { enrich, enrich_kind, enrich_skip_reason }. */
function decideEligibility(row) {
  const kind = String(row.product_kind || '').trim();
  const mnn = String(row.attr_mnn || '').trim();
  const rx = String(row.attr_rx_otc || '').trim();
  const text = `${row.normalized_text || ''} ${row.attr_brand || ''}`;

  if (kind === 'drug') {
    const mnnEmpty = !mnn;
    const rxBad = !rx || !RX_BASELINE_CANON.has(rx);
    if (mnnEmpty || rxBad) {
      return { enrich: true, enrich_kind: 'drug', enrich_skip_reason: null };
    }
    return { enrich: false, enrich_kind: 'drug', enrich_skip_reason: 'drug_mnn_and_rx_ok' };
  }

  if (kind === 'vitamin_or_baa') {
    const hit = nutrientHit(text);
    const multi = isMultiVitaminBrand(text);

    if (mnn === 'Комплекс' && (multi || !hit)) {
      return {
        enrich: false,
        enrich_kind: 'vitamin_or_baa',
        enrich_skip_reason: 'vitamin_complex_skip',
      };
    }
    if (hit || (!mnn && !multi)) {
      return { enrich: true, enrich_kind: 'vitamin_or_baa', enrich_skip_reason: null };
    }
    return {
      enrich: false,
      enrich_kind: 'vitamin_or_baa',
      enrich_skip_reason: multi ? 'vitamin_multivitamin_skip' : 'vitamin_no_signal',
    };
  }

  return { enrich: false, enrich_kind: kind || null, enrich_skip_reason: 'kind_out_of_scope' };
}

function extractJsonString(raw) {
  if (raw == null) return null;
  if (typeof raw === 'object') return JSON.stringify(raw);
  let s = String(raw).trim();
  if (!s) return null;
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();
  const start = s.indexOf('{');
  const end = s.lastIndexOf('}');
  if (start >= 0 && end > start) s = s.slice(start, end + 1);
  return s;
}

function safeParseJson(raw) {
  const s = extractJsonString(raw);
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function normalizeMnn(raw) {
  if (raw == null) return null;
  const t = String(raw).trim();
  if (!t || t.toLowerCase() === 'null' || t === '-' || t === 'n/a') return null;
  return t;
}

function normalizeRxEnriched(raw, productKind) {
  if (productKind === 'vitamin_or_baa') return 'не применимо';
  if (raw == null) return 'unknown';
  const t = foldText(raw);
  if (!t || t === 'null' || t === 'n/a' || t === 'na') return 'unknown';
  if (t === 'rx' || /^(рецептурн|по\s+рецепту)/.test(t) || t.includes('рецептурн')) {
    if (/без\s*рецепт|безрецептур|otc/.test(t)) return 'otc';
    return 'rx';
  }
  if (t === 'otc' || /без\s*рецепт|безрецептур|овер[\s-]*каунтер/.test(t)) return 'otc';
  if (t === 'не применимо' || t === 'not_applicable') return 'не применимо';
  if (t === 'unknown') return 'unknown';
  return 'unknown';
}

function normalizeCombinationHint(raw) {
  if (raw == null) return null;
  const t = foldText(raw);
  if (!t || t === 'null') return null;
  if (
    t === 'monocomponent' ||
    t.includes('монокомпонент') ||
    t === 'моно'
  ) {
    return 'monocomponent';
  }
  if (
    t === 'multicomponent' ||
    t.includes('многокомпонент') ||
    t.includes('мульти') ||
    t.includes('комбинирован')
  ) {
    return 'multicomponent';
  }
  if (t === 'unknown' || t === 'неизвестно') return 'unknown';
  return 'unknown';
}

function clampConfidence(v) {
  if (v == null || v === '') return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return Math.round(n * 1000) / 1000;
}

function buildEnrichedRecord(row, parsed, errorMessage) {
  const kind = row.enrich_kind || row.product_kind || '';
  const err = errorMessage || null;

  if (err || !parsed) {
    return {
      product_id: row.product_id ?? null,
      product_kind: kind || row.product_kind || null,
      normalized_text: row.normalized_text ?? null,
      attr_mnn: row.attr_mnn ?? null,
      attr_rx_otc: row.attr_rx_otc ?? null,
      attr_brand: row.attr_brand ?? null,
      attr_combination_hint: row.attr_combination_hint ?? null,
      mnn_enriched: null,
      rx_otc_enriched: kind === 'vitamin_or_baa' ? 'не применимо' : 'unknown',
      combination_hint_enriched: kind === 'vitamin_or_baa' ? 'unknown' : null,
      mnn_source: 'qwen_enrichment',
      rx_source: 'qwen_enrichment',
      confidence_enriched: null,
      explanation_enriched: null,
      error_message: err || 'parse_failed',
      enrich_kind: kind || null,
      enrich_skip_reason: row.enrich_skip_reason ?? null,
      prompt_version: row.prompt_version || 'prompt_enrichment_v1',
    };
  }

  const mnn = normalizeMnn(parsed.mnn);
  const rx = normalizeRxEnriched(parsed.rx_otc, kind);
  const combo =
    kind === 'vitamin_or_baa'
      ? normalizeCombinationHint(parsed.combination_hint)
      : null;

  return {
    product_id: row.product_id ?? null,
    product_kind: kind || row.product_kind || null,
    normalized_text: row.normalized_text ?? null,
    attr_mnn: row.attr_mnn ?? null,
    attr_rx_otc: row.attr_rx_otc ?? null,
    attr_brand: row.attr_brand ?? null,
    attr_combination_hint: row.attr_combination_hint ?? null,
    mnn_enriched: mnn,
    rx_otc_enriched: rx,
    combination_hint_enriched: combo,
    mnn_source: 'qwen_enrichment',
    rx_source: 'qwen_enrichment',
    confidence_enriched: clampConfidence(parsed.confidence),
    explanation_enriched:
      parsed.explanation != null ? String(parsed.explanation).trim() || null : null,
    error_message: null,
    enrich_kind: kind || null,
    enrich_skip_reason: row.enrich_skip_reason ?? null,
    prompt_version: row.prompt_version || 'prompt_enrichment_v1',
  };
}

return items.map((item, index) => {
  const j = item.json || {};
  const rawOut =
    j.enrichment_raw ??
    j.output ??
    j.text ??
    j.response ??
    (j.message && j.message.content) ??
    null;
  const errHint = j.error_message || j.enrichment_error || null;
  const parsed = errHint ? null : safeParseJson(rawOut);
  const record = buildEnrichedRecord(j, parsed, errHint);

  return {
    json: {
      ...j,
      ...record,
      enrichment_eligibility: decideEligibility(j),
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
