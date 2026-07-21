// norm_helpers_v1 — shared Norm helpers for hierarchy cascade (B3).
// Duplicated identically into Norm — Normalize Product / Norm — Normalize Dict
// (n8n Code nodes cannot share modules). Keep both copies in sync.

function asString(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return null;
}

function collapseWhitespace(s) {
  const t = asString(s);
  if (t === null) return null;
  return t.replace(/\s+/g, ' ').trim();
}

function asciiHyphen(s) {
  const t = asString(s);
  if (t === null) return null;
  // U+2011 non-breaking hyphen, en/em dashes → ASCII hyphen
  return t.replace(/[\u2011\u2010\u2012\u2013\u2014\u2212]/g, '-');
}

function unifyQuotes(s) {
  const t = asString(s);
  if (t === null) return null;
  return t
    .replace(/[\u00AB\u00BB\u201C\u201D\u201E\u201F]/g, '"')
    .replace(/[\u2018\u2019\u201A\u201B]/g, "'");
}

function stripHtmlNoise(s) {
  const t = asString(s);
  if (t === null) return null;
  return t
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/gi, "'");
}

function normDirection(s) {
  const t = asString(s);
  if (t === null) return null;
  const out = t.trim().toLowerCase();
  return out === '' ? null : out;
}

function normNeed(s) {
  const collapsed = collapseWhitespace(s);
  if (collapsed === null || collapsed === '') return null;
  return asciiHyphen(collapsed).toLowerCase();
}

function normCategory(s) {
  const collapsed = collapseWhitespace(s);
  if (collapsed === null || collapsed === '') return null;
  // ascii hyphen so need_flat_like / membership match norm_need on U+2011 rows
  return asciiHyphen(collapsed).toLowerCase();
}

function normMnn(s) {
  const collapsed = collapseWhitespace(s);
  if (collapsed === null || collapsed === '') return null;
  return asciiHyphen(collapsed).toLowerCase();
}

function normProductText(s) {
  let t = asString(s);
  if (t === null) return null;
  t = stripHtmlNoise(t);
  t = unifyQuotes(t);
  t = asciiHyphen(t);
  t = collapseWhitespace(t);
  return t === '' ? null : t;
}

function isMultiSepMnn(raw) {
  const t = asString(raw);
  if (t === null || t === '') return false;
  if (!/[,;/\\|]/.test(t)) return false;
  // Slash-list / multi-token heuristic: separator plus another non-trivial chunk
  const parts = t.split(/[,;/\\|]+/).map((p) => p.trim()).filter(Boolean);
  return parts.length >= 2;
}

function isDeviceSkuLike(raw) {
  const t = asString(raw);
  if (t === null || t === '') return false;
  const s = asciiHyphen(t).toLowerCase();
  // no \b after Cyrillic units — JS \b is ASCII-only without /u
  if (/\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?\s*(?:см|mm|мм)/.test(s)) return true;
  if (/\d+\s*[×xх]\s*\d+/i.test(t)) return true;
  if (/мме\s*\/\s*мл|мме\/мл/.test(s)) return true;
  if (/чувствительность/.test(s)) return true;
  if (/объ[её]м\s*~?\s*\d/.test(s)) return true;
  if (/тип\s+[аa]\s*№?\s*\d/i.test(t)) return true;
  if (/размер\s+\d/i.test(t)) return true;
  if (/длина\s*~?\s*\d/.test(s)) return true;
  return false;
}

function pushWarning(warnings, field, reason, raw) {
  warnings.push({
    field,
    reason,
    raw: raw === undefined ? null : raw,
  });
}
