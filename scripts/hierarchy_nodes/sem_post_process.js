// Sem — Post-process (hierarchy B3 Sem).
// Soft-continue always → next_action=direction_select.
// Never classified. Never persist category_id from Sem.

function extractJsonString(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') return JSON.stringify(value);
  let text = String(value).trim();
  const codeFenceMatch = text.match(/^```(?:json)?\s*\n?([\s\S]+?)\n?```\s*$/i);
  if (codeFenceMatch) text = codeFenceMatch[1].trim();
  return text;
}

function safeParseJson(value) {
  const text = extractJsonString(value);
  if (!text) return { ok: false, error: 'empty_output', parsed: null, raw_text: null };
  try {
    return { ok: true, error: null, parsed: JSON.parse(text), raw_text: text };
  } catch (e) {
    return { ok: false, error: 'invalid_json', parsed: null, raw_text: text };
  }
}

function normalizeConfidence(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  if (n < 0 || n > 1) return null;
  return n;
}

function safeText(v) {
  if (v === undefined || v === null || v === '') return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}

function pickLlmRaw(root) {
  if (root.output !== undefined) return root.output;
  if (root.text !== undefined) return root.text;
  if (root.response !== undefined) return root.response;
  if (root.content !== undefined) return root.content;
  if (root.result !== undefined) return root.result;
  return null;
}

const ATTR_KEYS = [
  'mnn',
  'brand',
  'rx_otc',
  'nosology',
  'administration_route',
  'dosage_form',
  'dosage',
  'age_segment',
  'package_hint',
  'combination_hint',
];

const RX_OTC_ALLOWED = new Set(['rx', 'otc', 'unknown', null]);

return items.map((item, index) => {
  const root = item.json || {};
  const ctx = root.context || {};
  const C = root.constants || {};

  const WORKFLOW_VERSION = root.workflow_version || 'stage2_hierarchy_v1';
  const PROMPT_VERSION = root.prompt_version || 'prompt_semantic_v1';
  const STAGE = (C.stage && C.stage.semantic_primary) || 'semantic_primary';
  const DECISION_PENDING =
    (C.decision_status && C.decision_status.pending_fallback) || 'pending_fallback';
  const NEXT_DIR =
    (C.next_action && C.next_action.direction_select) || 'direction_select';
  const ACTOR_LLM = (C.actor_type && C.actor_type.llm) || 'llm';
  const LOG = C.log_status || {
    success: 'success',
    rejected: 'rejected',
    needs_review: 'needs_review',
  };
  const MODEL_NAME =
    (C.model && C.model.cascade_actor_name) ||
    (C.model && C.model.primary_actor_name) ||
    'deepseek-chat';

  const raw = pickLlmRaw(root);
  const parsed = safeParseJson(raw);

  let validationPassed = false;
  let rejectReason = null;
  let semanticAttrs = null;
  let semanticConfidence = null;
  let semanticExplanation = null;
  let logStatus = LOG.rejected || 'rejected';

  if (!parsed.ok) {
    rejectReason = parsed.error || 'empty_output';
  } else if (!parsed.parsed || typeof parsed.parsed !== 'object' || Array.isArray(parsed.parsed)) {
    rejectReason = 'invalid_shape';
  } else {
    const obj = parsed.parsed;
    const forbiddenCat = obj.category_id;
    if (forbiddenCat !== undefined && forbiddenCat !== null && String(forbiddenCat).trim() !== '') {
      rejectReason = 'category_id_forbidden';
    } else if (
      obj.direction !== undefined &&
      obj.direction !== null &&
      String(obj.direction).trim() !== ''
    ) {
      rejectReason = 'direction_forbidden';
    } else if (obj.need !== undefined && obj.need !== null && String(obj.need).trim() !== '') {
      rejectReason = 'need_forbidden';
    } else {
      const conf = normalizeConfidence(obj.confidence);
      const explanation = safeText(obj.explanation);
      if (conf === null) {
        rejectReason = 'invalid_confidence';
      } else if (explanation === null) {
        // soft-continue per migration: missing explanation only
        rejectReason = 'missing_explanation';
        semanticConfidence = conf;
        semanticAttrs = {};
        for (const key of ATTR_KEYS) {
          if (key === 'rx_otc') {
            const rx = safeText(obj.rx_otc);
            semanticAttrs.rx_otc =
              rx === null ? null : RX_OTC_ALLOWED.has(rx.toLowerCase()) ? rx.toLowerCase() : rx;
          } else {
            semanticAttrs[key] = safeText(obj[key]);
          }
        }
        semanticExplanation = null;
        validationPassed = false;
        logStatus = LOG.needs_review || 'needs_review';
      } else {
        semanticConfidence = conf;
        semanticExplanation = explanation;
        semanticAttrs = {};
        for (const key of ATTR_KEYS) {
          if (key === 'rx_otc') {
            const rx = safeText(obj.rx_otc);
            if (rx === null) semanticAttrs.rx_otc = null;
            else if (RX_OTC_ALLOWED.has(rx.toLowerCase())) semanticAttrs.rx_otc = rx.toLowerCase();
            else {
              semanticAttrs.rx_otc = rx;
              // non-fatal: keep attr, mark soft warning via reject_reason only if otherwise OK
            }
          } else {
            semanticAttrs[key] = safeText(obj[key]);
          }
        }
        validationPassed = true;
        rejectReason = null;
        logStatus = LOG.success || 'success';
      }
    }
  }

  // Always soft-continue to Dir seam; never classified at Sem.
  const decisionStatus = DECISION_PENDING;
  const nextAction = NEXT_DIR;

  const prevTrace =
    root.cascade_trace && typeof root.cascade_trace === 'object' && !Array.isArray(root.cascade_trace)
      ? root.cascade_trace
      : {};
  const path = Array.isArray(prevTrace.path) ? [...prevTrace.path] : [];
  if (!path.includes(STAGE)) path.push(STAGE);
  const stages = Array.isArray(prevTrace.stages) ? [...prevTrace.stages] : [];
  stages.push({
    stage: STAGE,
    actor_type: ACTOR_LLM,
    actor_name: MODEL_NAME,
    validation_passed: validationPassed,
    reject_reason: rejectReason,
    notes: 'semantic_primary_v1',
  });

  const routingHint = {
    sem_soft_continue: true,
    semantic_validation_passed: validationPassed,
    semantic_reject_reason: rejectReason,
    next_stage: NEXT_DIR,
  };

  return {
    json: {
      ...root,
      workflow_version: WORKFLOW_VERSION,
      prompt_version: PROMPT_VERSION,
      stage: STAGE,
      actor_type: ACTOR_LLM,
      actor_name: MODEL_NAME,
      semantic_attrs: semanticAttrs,
      semantic_confidence: semanticConfidence,
      semantic_explanation: semanticExplanation,
      semantic_raw_json: parsed.raw_text
        ? { raw_text: parsed.raw_text, parsed: parsed.parsed }
        : raw !== null && raw !== undefined
          ? { raw: raw }
          : null,
      semantic_validation_passed: validationPassed,
      semantic_reject_reason: rejectReason,
      decision_status: decisionStatus,
      next_action: nextAction,
      routing_hint: routingHint,
      log_status: logStatus,
      // Explicit: Sem never sets category
      selected_category_id: null,
      cascade_trace: {
        ...prevTrace,
        path,
        stages,
      },
    },
    pairedItem: index,
  };
});
