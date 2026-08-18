// Rx — Build Product Identity (M3.2a). Deterministic; no HTTP/LLM.
// n8n Code node pattern: ...item.json

function safeText(v) {
  if (v === undefined || v === null) return '';
  return String(v).trim();
}

function collapseSpaces(s) {
  return String(s || '').replace(/\s+/g, ' ').trim();
}

const FORM_RULES = [
  { out: 'фильтр-пакеты', re: /фильтр[\s-]*пакет|ф\s*\/\s*п/i },
  { out: 'таблетки жевательные', re: /жеват/i },
  { out: 'лиофилизат', re: /лиофил/i },
  { out: 'капсулы', re: /капсул|капс\.?/i },
  { out: 'таблетки', re: /таблет|табл\.?|таб\.(?![а-яёa-z])/i },
  { out: 'гранулы', re: /гранул/i },
  { out: 'суспензия', re: /суспенз|сусп\.?/i },
  { out: 'порошок', re: /порош/i },
  { out: 'раствор', re: /раствор|\bр-р\b|\bр\/р\b/i },
  { out: 'сироп', re: /сироп/i },
  { out: 'мазь', re: /мазь/i },
  { out: 'крем', re: /крем/i },
  { out: 'гель', re: /гель/i },
  { out: 'аэрозоль', re: /аэрозол/i },
  { out: 'спрей', re: /спрей/i },
  { out: 'капли', re: /капли/i },
  { out: 'трава', re: /трава/i },
];

function normalizeUnits(s) {
  let t = String(s || '');
  t = t.replace(/(\d+(?:[.,]\d+)?)\s*[мm]кг(?![а-яёa-z])/gi, '$1 мкг');
  t = t.replace(/(\d+(?:[.,]\d+)?)\s*[мm][гg](?![а-яёa-z])/gi, '$1 мг');
  t = t.replace(/(\d+(?:[.,]\d+)?)\s*[мm][лl](?![а-яёa-z])/gi, '$1 мл');
  t = t.replace(/(\d+(?:[.,]\d+)?)\s*%/g, '$1%');
  t = t.replace(/(\d+(?:[.,]\d+)?)\s*[гg](?![а-яёa-z])/gi, '$1 г');
  t = t.replace(/(?:№|Nо|No|N)\s*(\d+)/gi, 'N$1');
  return collapseSpaces(t);
}

function findForm(head) {
  let best = null;
  for (const rule of FORM_RULES) {
    const m = head.match(rule.re);
    if (!m || m.index === undefined) continue;
    if (!best || m.index < best.index || (m.index === best.index && m[0].length > best.match.length)) {
      best = { out: rule.out, index: m.index, match: m[0] };
    }
  }
  return best;
}

function manufacturerShort(mfr) {
  const t = safeText(mfr);
  if (!t) return '';
  const stop = new Set(['ооо', 'ао', 'пао', 'зао', 'оао', 'ип', 'пao']);
  const tokens = t.split(/\s+/).filter((tok) => !stop.has(tok.toLowerCase()));
  return tokens[0] || t.split(/\s+/)[0] || t;
}

function quotePart(s) {
  const t = safeText(s);
  if (!t) return null;
  return `"${t.replace(/"/g, '')}"`;
}

function buildIdentity(j) {
  const warnings = [];
  const original = j.normalized_text_full != null && j.normalized_text_full !== ''
    ? String(j.normalized_text_full)
    : String(j.normalized_text || '');
  const normalized_text_full = original;

  const segments = original.split('|').map((s) => collapseSpaces(s)).filter(Boolean);
  const head = segments[0] || '';
  const tails = [];
  for (let i = 1; i < segments.length; i++) {
    if (!tails.includes(segments[i])) tails.push(segments[i]);
  }

  const formHit = findForm(head);
  let brand = safeText(j.brand_or_product_name);
  let form = safeText(j.dosage_form);
  let after = head;
  if (formHit) {
    if (!brand) brand = collapseSpaces(head.slice(0, formHit.index));
    if (!form) form = formHit.out;
    after = head.slice(formHit.index + formHit.match.length);
  } else if (!brand) {
    const toks = head.split(/\s+/).filter(Boolean);
    brand = toks[0] || '';
    after = toks.slice(1).join(' ');
    if (!form) warnings.push('form_missing');
  }

  after = normalizeUnits(after);

  let strength = safeText(j.strength);
  if (!strength) {
    const sm = after.match(/(\d+(?:[.,]\d+)?\s*(?:мкг|мг|%))/i);
    if (sm) strength = sm[1].replace(/\s+/g, ' ');
  }
  strength = strength ? normalizeUnits(strength) : '';

  let pack = safeText(j.pack);
  if (!pack) {
    const pm = after.match(/\bN(\d+)\b/i);
    if (pm) pack = `N${pm[1]}`;
  }
  if (!pack) {
    const vm = after.match(/(\d+(?:[.,]\d+)?\s*мл)(?![а-яёa-z])/i);
    if (vm) pack = normalizeUnits(vm[1]);
  }
  if (!pack) {
    const gm = after.match(/(\d+(?:[.,]\d+)?\s*г)(?![а-яёa-z])/i);
    if (gm && !/мг/i.test(gm[1])) pack = normalizeUnits(gm[1]);
  }

  let manufacturer = safeText(j.manufacturer_normalized) || tails[0] || '';

  if (!brand) warnings.push('brand_missing');
  if (!form) warnings.push('form_missing');
  if (!strength) warnings.push('strength_missing');
  if (!pack) warnings.push('pack_missing');
  if (!manufacturer) warnings.push('manufacturer_missing');

  const identityParts = [brand, form, strength, pack, manufacturer].filter(Boolean);
  const rx_otc_identity_text = identityParts.join(' ');

  const queryBits = [];
  if (brand) queryBits.push(quotePart(brand));
  if (form) queryBits.push(quotePart(form));
  if (strength) queryBits.push(quotePart(strength));
  const rx_otc_identity_query = queryBits.filter(Boolean).join(' ');

  const rx_otc_identity_fingerprint = rx_otc_identity_text
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/\s+/g, ' ')
    .trim();

  const mnn = safeText(j.mnn_if_known);
  const used_mnn_as_primary_query = !brand && Boolean(mnn);

  return {
    normalized_text_full,
    rx_otc_brand_norm: brand || null,
    rx_otc_form_norm: form || null,
    rx_otc_strength_norm: strength || null,
    rx_otc_pack_norm: pack || null,
    rx_otc_manufacturer_norm: manufacturer || null,
    rx_otc_manufacturer_short: manufacturerShort(manufacturer) || null,
    rx_otc_identity_text: rx_otc_identity_text || null,
    rx_otc_identity_query: rx_otc_identity_query || null,
    rx_otc_identity_fingerprint: rx_otc_identity_fingerprint || null,
    identity_build_warnings: warnings,
    used_mnn_as_primary_query,
  };
}

const items = $input.all();
return items.map((item, i) => ({
  json: { ...item.json, ...buildIdentity(item.json || {}) },
  pairedItem: { item: i },
}));
