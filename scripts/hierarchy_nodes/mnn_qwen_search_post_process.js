/**
 * MNN Qwen Search — Post-process
 * Parses model JSON, extracts API source annotations, enforces search confirmation.
 * Expects item.json to contain either:
 *   - polza_raw / api_response (full chat completion object), OR
 *   - message content + annotations fields already flattened.
 */
const PROMPT_VERSION = 'mnn_qwen_web_search_v1';
const ALLOWED_STATUS = new Set(['found', 'not_found', 'conflict']);

function extractJsonString(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') return JSON.stringify(value);
  let text = String(value).trim();
  const fence = text.match(/^```(?:json)?\s*\n?([\s\S]+?)\n?```\s*$/i);
  if (fence) text = fence[1].trim();
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start >= 0 && end > start) text = text.slice(start, end + 1);
  return text;
}

function asBool(v) {
  if (typeof v === 'boolean') return v;
  if (v === 'true' || v === 1 || v === '1') return true;
  if (v === 'false' || v === 0 || v === '0') return false;
  return null;
}

function extractAnnotations(api) {
  const sources = [];
  if (!api || typeof api !== 'object') return sources;
  const msg =
    (((api.choices || [])[0] || {}).message) ||
    api.message ||
    {};
  const anns = msg.annotations || api.annotations || [];
  if (Array.isArray(anns)) {
    anns.forEach((a, i) => {
      const uc = (a && a.url_citation) || a || {};
      const url = uc.url || a.url || null;
      if (!url) return;
      sources.push({
        index: i + 1,
        url: String(url),
        title: uc.title || a.title || null,
        snippet: uc.content || a.content || null,
      });
    });
  }
  // DashScope-style fallback (if ever present)
  const sr =
    (api.search_info && api.search_info.search_results) ||
    (api.search_results) ||
    [];
  if (Array.isArray(sr) && sources.length === 0) {
    sr.forEach((s, i) => {
      if (!s || !s.url) return;
      sources.push({
        index: s.index != null ? Number(s.index) : i + 1,
        url: String(s.url),
        title: s.title || null,
        snippet: s.snippet || s.content || null,
      });
    });
  }
  return sources;
}

function extractContent(api, j) {
  if (j.qwen_raw_content) return j.qwen_raw_content;
  if (!api) return j.output ?? j.text ?? j.content ?? null;
  const msg = (((api.choices || [])[0] || {}).message) || {};
  return msg.content ?? null;
}

function normalizeMnnLight(s) {
  if (s === null || s === undefined) return null;
  let t = String(s).trim();
  if (!t || t.toLowerCase() === 'null') return null;
  t = t.replace(/\*/g, ' ');
  t = t.replace(/\s+/g, ' ').trim();
  return t || null;
}

return items.map((item, index) => {
  const j = { ...(item.json || {}) };
  const started = j._qwen_started_ms != null ? Number(j._qwen_started_ms) : null;
  const latency =
    j.qwen_search_latency_ms != null
      ? Number(j.qwen_search_latency_ms)
      : started != null
        ? Date.now() - started
        : null;

  const api = j.polza_raw || j.api_response || j.qwen_api_response || null;
  const apiError = j.qwen_http_error || j.error || null;

  const base = {
    ...j,
    qwen_search_prompt_version: j.qwen_search_prompt_version || PROMPT_VERSION,
    qwen_search_model:
      j.qwen_search_model ||
      (api && api.model) ||
      'qwen/qwen3.5-flash-02-23@reasoning_effort=none',
    qwen_search_provider: j.qwen_search_provider || 'polza',
    qwen_search_enabled: true,
    qwen_search_latency_ms: latency,
  };

  // Clear transient
  delete base.polza_raw;
  delete base.api_response;
  delete base.qwen_api_response;
  delete base.qwen_raw_content;
  delete base.qwen_http_error;
  delete base._qwen_started_ms;
  delete base.qwen_search_prompt_system;
  delete base.qwen_search_prompt_user;

  if (apiError) {
    return {
      json: {
        ...base,
        qwen_search_status: 'api_error',
        qwen_search_mnn: null,
        qwen_search_model_confidence: null,
        qwen_search_short_explanation: null,
        qwen_search_evidence: null,
        qwen_search_source_count: 0,
        qwen_search_sources_json: '[]',
        qwen_search_error: String(apiError).slice(0, 500),
        qwen_search_brand_match: null,
        qwen_search_dosage_form_match: null,
        qwen_search_dosage_match: null,
        qwen_search_source_url_primary: null,
        qwen_search_source_title_primary: null,
        qwen_parsed_ok: false,
      },
      pairedItem: item.pairedItem ?? { item: index },
    };
  }

  const sources = extractAnnotations(api);
  const content = extractContent(api, j);
  const rawText = extractJsonString(content);
  let parsed = null;
  let parseError = null;
  if (rawText) {
    try {
      parsed = JSON.parse(rawText);
    } catch (e) {
      parseError = String(e);
    }
  } else {
    parseError = 'empty_model_content';
  }

  const sourcesJson = JSON.stringify(sources);
  const primary = sources[0] || null;

  if (!sources.length) {
    return {
      json: {
        ...base,
        qwen_search_status: 'search_not_confirmed',
        qwen_search_mnn: null,
        qwen_search_model_confidence:
          parsed && typeof parsed.model_confidence === 'number'
            ? parsed.model_confidence
            : null,
        qwen_search_short_explanation:
          (parsed && parsed.short_explanation) ||
          'API не вернул source annotations — web search не подтверждён',
        qwen_search_evidence: (parsed && parsed.evidence) || null,
        qwen_search_source_count: 0,
        qwen_search_sources_json: sourcesJson,
        qwen_search_error: parseError,
        qwen_search_brand_match: null,
        qwen_search_dosage_form_match: null,
        qwen_search_dosage_match: null,
        qwen_search_source_url_primary: null,
        qwen_search_source_title_primary: null,
        qwen_parsed_ok: Boolean(parsed),
        qwen_model_claimed_mnn: parsed ? normalizeMnnLight(parsed.mnn) : null,
        qwen_model_claimed_status: parsed ? parsed.status : null,
      },
      pairedItem: item.pairedItem ?? { item: index },
    };
  }

  if (!parsed) {
    return {
      json: {
        ...base,
        qwen_search_status: 'invalid_json',
        qwen_search_mnn: null,
        qwen_search_model_confidence: null,
        qwen_search_short_explanation: null,
        qwen_search_evidence: null,
        qwen_search_source_count: sources.length,
        qwen_search_sources_json: sourcesJson,
        qwen_search_error: parseError || 'json_parse_failed',
        qwen_search_brand_match: null,
        qwen_search_dosage_form_match: null,
        qwen_search_dosage_match: null,
        qwen_search_source_url_primary: primary ? primary.url : null,
        qwen_search_source_title_primary: primary ? primary.title : null,
        qwen_parsed_ok: false,
      },
      pairedItem: item.pairedItem ?? { item: index },
    };
  }

  let status = String(parsed.status || '').trim();
  if (!ALLOWED_STATUS.has(status)) status = 'not_found';
  let mnn = normalizeMnnLight(parsed.mnn);
  let conf = parsed.model_confidence;
  if (typeof conf !== 'number' || conf < 0 || conf > 1) conf = null;

  const idm = parsed.identity_match || {};
  const brandMatch = asBool(idm.brand_match);
  const formMatch = asBool(idm.dosage_form_match);
  const doseMatch = asBool(idm.dosage_match);

  let used = Array.isArray(parsed.used_source_indexes)
    ? parsed.used_source_indexes.map(Number).filter((n) => Number.isFinite(n))
    : [];
  const validIndexes = new Set(sources.map((s) => s.index));
  const usedOk = used.filter((i) => validIndexes.has(i));
  // Also accept 0-based indexes from model
  const usedOk0 = used
    .filter((i) => validIndexes.has(i + 1))
    .map((i) => i + 1);
  const usedFinal = usedOk.length ? usedOk : usedOk0;

  if (status === 'found') {
    if (!mnn) status = 'not_found';
    else if (!usedFinal.length && sources.length) {
      // sources exist but indexes invalid — still allow found if sources present
      // keep found; indexes optional when annotations exist
    }
  }
  if (status !== 'found') mnn = null;

  return {
    json: {
      ...base,
      qwen_search_status: status,
      qwen_search_mnn: mnn,
      qwen_search_model_confidence: conf,
      qwen_search_short_explanation: parsed.short_explanation
        ? String(parsed.short_explanation).slice(0, 500)
        : null,
      qwen_search_evidence: parsed.evidence
        ? String(parsed.evidence).slice(0, 500)
        : null,
      qwen_search_source_count: sources.length,
      qwen_search_sources_json: sourcesJson,
      qwen_search_error: null,
      qwen_search_brand_match: brandMatch,
      qwen_search_dosage_form_match: formMatch,
      qwen_search_dosage_match: doseMatch,
      qwen_search_source_url_primary: primary ? primary.url : null,
      qwen_search_source_title_primary: primary ? primary.title : null,
      qwen_search_used_source_indexes: usedFinal,
      qwen_parsed_ok: true,
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
