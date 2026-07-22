// Sem — Smoke Inject Bad JSON (temporary S2 live only).
// Deterministic: only first item (index === 0) when sem_smoke_wave === 'S2_live'.
// Wave is read from Run — Init Constants (Load SQL drops item-level constants).

const BROKEN_MISSING_EXPLANATION = JSON.stringify({
  mnn: 'paracetamol',
  brand: null,
  rx_otc: 'otc',
  nosology: null,
  administration_route: 'oral',
  dosage_form: 'tablet',
  dosage: '500 mg',
  age_segment: null,
  package_hint: null,
  combination_hint: null,
  confidence: 0.72,
  // explanation intentionally omitted for S2 live smoke
});

function resolveSmokeWave(root) {
  try {
    const init = $('Run — Init Constants').first().json || {};
    const fromInit = (init.constants && init.constants.sem_smoke_wave) || init.sem_smoke_wave;
    if (fromInit) return fromInit;
  } catch (e) {
    // Init node reference unavailable
  }
  const C = root.constants || {};
  return C.sem_smoke_wave || null;
}

return items.map((item, index) => {
  const root = item.json || {};
  const wave = resolveSmokeWave(root);

  if (wave === 'S2_live' && index === 0) {
    return {
      json: {
        ...root,
        output: BROKEN_MISSING_EXPLANATION,
        text: BROKEN_MISSING_EXPLANATION,
        sem_smoke_injected: true,
        sem_smoke_inject_reason: 'missing_explanation',
      },
      pairedItem: item.pairedItem !== undefined ? item.pairedItem : index,
    };
  }

  return {
    json: root,
    pairedItem: item.pairedItem !== undefined ? item.pairedItem : index,
  };
});
