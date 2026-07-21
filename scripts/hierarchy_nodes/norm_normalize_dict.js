// Norm — Normalize Dict (hierarchy B3). Embeds norm_helpers_v1.
// On canvas but NOT in live In-path. Wire in B4/Dir:
//   Dir — Load Categories → this node → Dir Merge Context.
// is_device_sku_like is a heuristic flag only — never a reject.

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
  const parts = t.split(/[,;/\\|]+/).map((p) => p.trim()).filter(Boolean);
  return parts.length >= 2;
}

function isDeviceSkuLike(raw) {
  const t = asString(raw);
  if (t === null || t === '') return false;
  const s = asciiHyphen(t).toLowerCase();
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

return items.map((item, index) => {
  const j = item.json || {};
  const warnings = [];

  const directionRaw = j.direction;
  const needRaw = j.need_nosology;
  const categoryRaw = j.category_name;
  const mnnRaw = j.mnn_cluster;

  const norm_direction = normDirection(directionRaw);
  const norm_need = normNeed(needRaw);
  const norm_category = normCategory(categoryRaw);
  const norm_mnn = normMnn(mnnRaw);

  if (directionRaw === null || directionRaw === undefined || String(directionRaw).trim() === '') {
    pushWarning(warnings, 'direction', 'empty', directionRaw ?? null);
  } else if (norm_direction === null) {
    pushWarning(warnings, 'direction', 'unusable', directionRaw);
  }

  if (needRaw === null || needRaw === undefined || String(needRaw).trim() === '') {
    pushWarning(warnings, 'need_nosology', 'empty', needRaw ?? null);
  } else if (norm_need === null) {
    pushWarning(warnings, 'need_nosology', 'unusable', needRaw);
  }

  if (categoryRaw === null || categoryRaw === undefined || String(categoryRaw).trim() === '') {
    pushWarning(warnings, 'category_name', 'empty', categoryRaw ?? null);
  } else if (norm_category === null) {
    pushWarning(warnings, 'category_name', 'unusable', categoryRaw);
  }

  const is_multi_sep = isMultiSepMnn(mnnRaw);
  const is_eq_category =
    norm_mnn !== null && norm_category !== null && norm_mnn === norm_category;
  const is_device_sku_like = isDeviceSkuLike(mnnRaw);
  const need_flat_like =
    norm_need !== null && norm_category !== null && norm_need === norm_category;

  const out = {
    ...j,
    norm_direction,
    norm_need,
    norm_category,
    norm_mnn,
    is_multi_sep,
    is_eq_category,
    is_device_sku_like,
    need_flat_like,
    norm_warnings: warnings,
  };

  if (is_multi_sep) {
    out.mnn_raw = mnnRaw;
  }

  return {
    json: out,
    pairedItem: index,
  };
});
