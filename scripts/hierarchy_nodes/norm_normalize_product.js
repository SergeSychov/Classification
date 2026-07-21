// Norm — Normalize Product (hierarchy B3). Embeds norm_helpers_v1.

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

const MAX_NORMALIZED_TEXT = 12000;

return items.map((item, index) => {
  const j = item.json || {};
  const warnings = [];

  const sourceFields = [];
  let rawText = asString(j.combined_text);
  if (rawText !== null && rawText.trim() !== '') {
    sourceFields.push('combined_text');
  } else {
    const parts = [];
    for (const key of ['product_name', 'name', 'title', 'description', 'product_description']) {
      const v = asString(j[key]);
      if (v !== null && v.trim() !== '') {
        parts.push(v.trim());
        sourceFields.push(key);
      }
    }
    rawText = parts.length ? parts.join(' ') : null;
  }

  let normalizedText = normProductText(rawText);
  let truncated = false;
  if (normalizedText !== null && normalizedText.length > MAX_NORMALIZED_TEXT) {
    normalizedText = normalizedText.slice(0, MAX_NORMALIZED_TEXT);
    truncated = true;
  }

  const emptyFlags = {
    combined_text: !(asString(j.combined_text) || '').trim(),
  };

  if (!normalizedText) {
    pushWarning(warnings, 'combined_text', 'empty', j.combined_text ?? null);
  }

  const mnnRaw =
    j.mnn !== undefined && j.mnn !== null && j.mnn !== ''
      ? j.mnn
      : j.mnn_cluster !== undefined && j.mnn_cluster !== null && j.mnn_cluster !== ''
        ? j.mnn_cluster
        : null;
  const normMnnProduct = mnnRaw !== null ? normMnn(mnnRaw) : null;

  const attrNorm = {};
  for (const key of [
    'brand_guess',
    'form_guess',
    'dosage_guess',
    'pack_size_guess',
    'product_type_guess',
  ]) {
    if (j[key] === undefined || j[key] === null || j[key] === '') continue;
    const n = normProductText(j[key]);
    if (n !== null) attrNorm[`norm_${key}`] = n.toLowerCase();
  }

  const stageName =
    (j.constants && j.constants.stage && j.constants.stage.normalize) || 'normalize';

  // merge-safe: keep existing cascade_trace keys; append normalize stage
  const prevTrace =
    j.cascade_trace && typeof j.cascade_trace === 'object' && !Array.isArray(j.cascade_trace)
      ? j.cascade_trace
      : {};
  const path = Array.isArray(prevTrace.path) ? [...prevTrace.path] : [];
  if (!path.includes(stageName)) path.push(stageName);
  const stages = Array.isArray(prevTrace.stages) ? [...prevTrace.stages] : [];
  stages.push({
    stage: stageName,
    actor_type: 'system',
    norm_warnings: warnings,
    notes: 'product_norm_v1',
  });

  return {
    json: {
      ...j,
      normalized_text: normalizedText,
      normalize_meta: {
        source_fields: sourceFields,
        truncated,
        empty_flags: emptyFlags,
      },
      norm_mnn_product: normMnnProduct,
      ...attrNorm,
      norm_warnings: warnings,
      cascade_trace: {
        ...prevTrace,
        path,
        stages,
      },
    },
    pairedItem: index,
  };
});
