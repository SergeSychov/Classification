// Shared MNN normalization helpers for n8n Code nodes (mirror of scripts/lib/mnn_normalization.py).
// Export via global functions in-file; paste or require pattern depends on n8n bundling.

function normalizeMnnAlias(raw) {
  if (raw == null) return null;
  let t = String(raw)
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[.\s;,\-~•|]+|[.\s;,\-~•|]+$/g, '');
  if (!t) return null;
  const f = t.toLowerCase().replace(/ё/g, 'е');
  if (['null', '-', 'n/a', 'нет', 'не указано', '~'].includes(f)) return null;
  if (t.length < 2) return null;
  if (/^[a-z0-9_]+$/.test(t)) return null;
  if (t.length > 200) t = t.slice(0, 200).replace(/\s+\S*$/, '');
  return t;
}

function isDescriptiveNonMnn(raw) {
  const t = normalizeMnnAlias(raw);
  if (!t) return true;
  const f = t.toLowerCase().replace(/ё/g, 'е');
  return /^(не присвоен|прочие|другие|препараты)\b|в комбинации|отхаркивающ|психостимулятор|ноотропн|противовирусн|поливитамин|бад\b|гомеопат|для лечения заболеван|терапевтическ\w*\s+групп/.test(
    f
  );
}

function splitMnnComponents(raw) {
  const t = normalizeMnnAlias(raw);
  if (!t || isDescriptiveNonMnn(t)) return [];
  const folded = t.toLowerCase().replace(/ё/g, 'е');
  // Protected Detralex-style complex (parity with Python mnn_normalization)
  if (/очищенн\w*\s+микронизированн\w*\s+флавоноидн\w*\s+фракц\w*/.test(folded)) {
    return ['Очищенная микронизированная флавоноидная фракция'];
  }
  const parts = t.split(/\s*[+;/]\s*/).map((x) => x.replace(/\*/g, '').trim()).filter(Boolean);
  // diosmin + hesperidin → same protected complex
  const keyset = new Set(
    parts.map((p) => p.toLowerCase().replace(/ё/g, 'е').replace(/[^a-zа-я0-9]+/g, ''))
  );
  if (
    keyset.size >= 2 &&
    [...keyset].every((k) => k === 'диосмин' || k === 'гесперидин' || k === 'diosmin' || k === 'hesperidin')
  ) {
    return ['Очищенная микронизированная флавоноидная фракция'];
  }
  const out = [];
  const seen = new Set();
  for (const p of parts) {
    if (isDescriptiveNonMnn(p)) continue;
    if ((p.match(/\(/g) || []).length !== (p.match(/\)/g) || []).length) continue;
    let key = p.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ');
    if (/хондроитин(?:а)?\s*сульфат|хондроитинсульфат|^хондроитин(?:а|у|ом)?$/.test(key)) {
      key = 'хондроитина сульфат натрия';
    }
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(
      key === 'хондроитина сульфат натрия' ? 'Хондроитина сульфат натрия' : p
    );
  }
  return out;
}

// n8n Code nodes typically don't module.export; keep no-op return for paste safety.
return items.map((item, index) => ({
  json: {
    ...(item.json || {}),
    _mnn_normalization_loaded: true,
  },
  pairedItem: item.pairedItem ?? { item: index },
}));
