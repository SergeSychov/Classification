// MNN — Catalog Consensus Resolver (hierarchy mirror, offline-ready).
// Does NOT rewrite attr_mnn / attr_rx_otc / semantic_attrs.mnn.
// Preserve ...item.json + pairedItem.

function fold(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[\u2010-\u2014\u2212]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();
}

function isDescriptiveNonMnn(raw) {
  const t = fold(raw);
  if (!t) return true;
  return /^(не присвоен|прочие|другие|препараты)\b|в комбинации|отхаркивающ|психостимулятор|ноотропн|противовирусн|поливитамин|бад\b|гомеопат|для лечения заболеван/.test(
    t
  );
}

function isHomeopathy(text) {
  return /гомеоп|homeop/i.test(String(text || ''));
}

function normalizeRx(raw) {
  const t = fold(raw);
  if (!t) return 'unknown';
  if (/без\s*рецепт|безрецептур|\botc\b/.test(t)) return 'otc';
  if (/по\s+рецепту|рецептурн|\brx\b/.test(t)) return 'rx';
  if (t === 'rx' || t === 'otc') return t;
  return 'unknown';
}

function normalizeAge(raw) {
  const t = fold(raw);
  if (!t) return 'unknown';
  if (/универсал|все\s*возраст|взрослые\s*и\s*дети/.test(t)) return 'универсальный';
  if (/детск|ребен|ребён|для\s*детей|\bдети\b|\bchild/.test(t)) return 'дети';
  if (/взросл|\badult/.test(t)) return 'взрослые';
  return 'unknown';
}

function splitComponents(raw) {
  if (!raw || isDescriptiveNonMnn(raw)) return [];
  const t = String(raw).replace(/\*/g, ' ').replace(/\s+/g, ' ').trim();
  const parts = t.split(/\s*[+;/]\s*/).flatMap((chunk) => {
    // keep thiamphenicol-style comma tails together — light heuristic
    if (!chunk.includes(',')) return [chunk.trim()];
    const bits = chunk.split(/\s*,\s*/);
    const out = [];
    let buf = bits[0];
    for (let i = 1; i < bits.length; i += 1) {
      const bit = bits[i];
      if (!bit) continue;
      if (/^[a-zа-яё]/.test(bit) || /^(глицинат|гидроксид|экстракт|комплекс)/i.test(bit)) {
        buf = `${buf}, ${bit}`;
      } else {
        out.push(buf);
        buf = bit;
      }
    }
    out.push(buf);
    return out.map((x) => x.trim()).filter(Boolean);
  });
  const seen = new Set();
  const out = [];
  for (const p of parts) {
    if (!p || isDescriptiveNonMnn(p)) continue;
    const key = fold(p).replace(/\[d\s*,\s*l\]/gi, '').replace(/\s+/g, ' ').trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(p.replace(/\s+/g, ' ').trim());
  }
  return out;
}

function voteScalar(values, allowed, minAgree = 2) {
  const counts = {};
  for (const v of values) {
    if (!allowed.has(v)) continue;
    counts[v] = (counts[v] || 0) + 1;
  }
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return 'unknown';
  if (entries.length > 1 && entries[0][1] === entries[1][1]) return 'unknown';
  return entries[0][1] >= minAgree ? entries[0][0] : 'unknown';
}

function resolveFromSources(sources) {
  const bySource = {};
  for (const s of sources || []) {
    const name = String(s.source || '').toLowerCase();
    if (!name) continue;
    bySource[name] = s;
  }
  const list = Object.values(bySource);
  const formulas = [];
  const sourceRaw = [];
  let descriptiveOnly = 0;

  for (const s of list) {
    const fieldType = s.field_type || 'unknown';
    const raw = s.raw_mnn || null;
    const matchStatus = s.match_status == null ? null : s.match_status;
    const sourceClass = s.source_class || null;
    const canVote =
      matchStatus == null
        ? true
        : matchStatus === 'accepted' &&
          (sourceClass == null || sourceClass === 'product_card') &&
          !!(s.url && (s.title || s.matched_product_title));
    let comps = [];
    if (
      canVote &&
      (fieldType === 'explicit_mnn' || fieldType === 'active_ingredient') &&
      raw &&
      !isDescriptiveNonMnn(raw)
    ) {
      comps = splitComponents(raw);
    } else if (raw && isDescriptiveNonMnn(raw)) {
      descriptiveOnly += 1;
    }
    sourceRaw.push({
      source: s.source,
      raw_mnn: raw,
      field_type: fieldType,
      canonical_components: comps,
      url: s.url || null,
      match_status: matchStatus,
      source_class: sourceClass,
    });
    if (comps.length) {
      formulas.push({ source: s.source, set: new Set(comps.map(fold)), display: comps });
    }
  }

  const votingList = list.filter((s) => {
    const matchStatus = s.match_status == null ? null : s.match_status;
    if (matchStatus == null) return true;
    const sourceClass = s.source_class || null;
    return (
      matchStatus === 'accepted' &&
      (sourceClass == null || sourceClass === 'product_card') &&
      !!(s.url && (s.title || s.matched_product_title))
    );
  });
  const resolvedRx = voteScalar(
    votingList.map((s) => normalizeRx(s.raw_rx_otc)),
    new Set(['rx', 'otc'])
  );
  const resolvedAge = voteScalar(
    votingList.map((s) => normalizeAge(s.raw_age)),
    new Set(['взрослые', 'дети', 'универсальный'])
  );

  const base = {
    mnn_resolution_status: 'unresolved_catalog',
    resolved_mnn: null,
    resolved_mnn_components: [],
    resolved_mnn_component_stats: [],
    resolved_mnn_sources: [],
    source_raw_mnn: sourceRaw,
    resolved_rx_otc: resolvedRx,
    resolved_age_segment: resolvedAge,
    needs_mnn_enrichment: true,
    resolution_reason: 'empty',
  };

  if (!formulas.length) {
    base.resolution_reason = descriptiveOnly ? 'descriptive_only' : 'empty';
    return base;
  }

  const freq = {};
  const sourcesFor = {};
  for (const f of formulas) {
    for (const d of f.display) {
      const k = fold(d);
      if (!sourcesFor[k]) sourcesFor[k] = [];
      if (!sourcesFor[k].includes(f.source)) {
        sourcesFor[k].push(f.source);
        freq[k] = (freq[k] || 0) + 1;
      }
    }
  }
  const anchors = Object.keys(freq).filter((k) => freq[k] >= 2);
  if (!anchors.length) {
    base.resolution_reason = formulas.length === 1 ? 'single_source' : 'incompatible_sets';
    return base;
  }

  // Compatible union: formulas sharing an anchor
  const accepted = formulas.filter((f) => anchors.some((a) => f.set.has(a)));
  const accFreq = {};
  const accSources = {};
  const disp = {};
  for (const f of accepted) {
    for (const d of f.display) {
      const k = fold(d);
      disp[k] = d;
      if (!accSources[k]) accSources[k] = [];
      if (!accSources[k].includes(f.source)) {
        accSources[k].push(f.source);
        accFreq[k] = (accFreq[k] || 0) + 1;
      }
    }
  }
  const threshold = accepted.length >= 3 ? 2 : 1;
  const keys = Object.keys(accFreq).filter((k) => accFreq[k] >= threshold || anchors.includes(k));
  keys.sort((a, b) => accFreq[b] - accFreq[a] || String(disp[a]).localeCompare(disp[b], 'ru'));
  const components = keys.map((k) => disp[k]);
  base.mnn_resolution_status = 'resolved_catalog';
  base.resolved_mnn = components.join(', ');
  base.resolved_mnn_components = components;
  base.resolved_mnn_component_stats = keys.map((k) => ({
    component: disp[k],
    source_count: accFreq[k],
    sources: accSources[k],
  }));
  base.resolved_mnn_sources = [...new Set(accepted.map((f) => f.source))];
  base.needs_mnn_enrichment = false;
  base.resolution_reason = 'consensus';
  return base;
}

return items.map((item, index) => {
  const j = item.json || {};
  const kind = j.product_kind || (j.semantic_attrs && j.semantic_attrs.product_kind) || null;
  const text = j.normalized_text || '';
  const sources = j.catalog_mnn_sources || j.mnn_catalog_sources || [];

  let resolved;
  if (kind && kind !== 'drug') {
    resolved = {
      mnn_resolution_status: 'unresolved_catalog',
      resolved_mnn: null,
      resolved_mnn_components: [],
      resolved_mnn_component_stats: [],
      resolved_mnn_sources: [],
      source_raw_mnn: [],
      resolved_rx_otc: 'unknown',
      resolved_age_segment: 'unknown',
      needs_mnn_enrichment: false,
      resolution_reason: 'not_drug',
    };
  } else if (isHomeopathy(text)) {
    resolved = {
      mnn_resolution_status: 'unresolved_catalog',
      resolved_mnn: null,
      resolved_mnn_components: [],
      resolved_mnn_component_stats: [],
      resolved_mnn_sources: [],
      source_raw_mnn: [],
      resolved_rx_otc: 'unknown',
      resolved_age_segment: 'unknown',
      needs_mnn_enrichment: false,
      resolution_reason: 'homeopathy_skip',
    };
  } else {
    resolved = resolveFromSources(sources);
  }

  return {
    json: {
      ...j,
      ...resolved,
      mnn_enriched: j.mnn_enriched ?? null,
      mnn_enrichment_status: j.mnn_enrichment_status ?? null,
      mnn_evidence: j.mnn_evidence ?? [],
      // baseline untouched
      attr_mnn: j.attr_mnn,
      attr_rx_otc: j.attr_rx_otc,
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
