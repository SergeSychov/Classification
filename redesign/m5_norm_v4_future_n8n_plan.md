# M5 — Future Norm v4 n8n plan (design only)

**Status:** DESIGN ONLY. No workflow edit, no Code-node implementation, no deploy.  
**Date:** 2026-08-19  
**Depends on:** offline experiment `norm_v4_experiment_m5_0` + human review of `mnn_norm_v4_experiment_human_review.csv`.

This is not authorization to patch `classification-stage2-hierarchy-dev` or prod Stage 2.

---

## 1. Where a future node would sit

Current hierarchy-dev live path (B3, unchanged):

```text
Load — Attach Run ID
  → Norm — Normalize Product          # product_norm_v1; writes normalized_text
  → Load — Limit Batch
  → Sem zone …
```

Proposed **future** placement (additive, after current Norm):

```text
Load — Attach Run ID
  → Norm — Normalize Product          # KEEP as-is; do not rewrite normalized_text
  → Norm — Product Text v4            # NEW Code node; parallel fields only
  → Load — Limit Batch
```

Do **not** replace `Norm — Normalize Product`. Do **not** put v4 on prod `classification-stage2-dev`.

Optional later consumer (only after review + explicit ask): identity / enrichment query builders read `enrichment_query_text_v4` instead of raw `normalized_text`. Not in this plan’s implementation.

---

## 2. Code-node contract (`...item.json`)

Follow Stage 2 conventions (`Categories/stage2_workflow_contract.md`):

- Input: `item.json` from `Norm — Normalize Product`
- Output: `{ json: { ...j, <v4 fields> }, pairedItem: index }`
- Constants from `item.json.constants` with local fallback
- Do not `$('…')` into parallel branches
- No HTTP, no LLM, no Postgres in the Code node

### Input (read)

| Field | Use |
|-------|-----|
| `normalized_text` | Source string (v1). Never overwritten |
| `product_id` | Pass-through |
| existing `normalize_meta` / `norm_*` | Pass-through |

### Output (add only)

Same v4 fields as the offline experiment:

```text
normalized_text_full_v4
product_identity_text_v4
enrichment_query_text_v4
enrichment_query_disambiguator_v4
brand_or_product_name_v4
dosage_form_v4
strength_v4
pack_v4
manufacturer_v4
manufacturer_short_v4
normalization_flags_v4
normalization_warnings_v4
manufacturer_dedup_count_v4
pack_dedup_count_v4
source_segment_count_v4
retained_segment_count_v4
```

`cascade_trace.stages[]` append `{ stage: 'normalize_v4', notes: 'product_norm_v4_parallel' }`.

Parser source of truth: port `scripts/mnn_norm_v4_experiment.py` into `scripts/hierarchy_nodes/norm_product_text_v4.js` **when implementation is asked**. Until then, JS is not created.

---

## 3. Migration strategy

```text
1. Parallel fields first
2. No overwrite of normalized_text
3. Downstream still reads normalized_text until a later explicit switch
```

| Phase | `normalized_text` | v4 fields | Consumers |
|-------|-------------------|-----------|-----------|
| Now (M5.0) | unchanged | artifacts only | none |
| hierarchy-dev log-only | unchanged | written on item + log JSON | log/audit |
| allowlist | unchanged | item fields | optional query builder on allowlist SKUs |
| prod | blocked | blocked | blocked until approval |

---

## 4. Safe rollout

```text
offline experiment
  → human review (label_norm_v4_*)
  → hierarchy-dev log-only (Load still WHERE false or tiny allowlist)
  → controlled allowlist
  → no prod until explicit approval
```

Gates before any live wiring:

- Human review of the 50-row sample: identity preserved, query appropriate, manufacturer correct
- Exception rows (`ambiguous_parse`, conflicts, possible_*_loss) inspected; no silent “fixes”
- Chunk size ≤ 10 if any later LLM consumer is involved (n8n execution contract)
- Kill switch / Load stub restored after smoke
- Do not enable error-workflow autoresume while the task runner is unhealthy

Rollback: delete/unwire `Norm — Product Text v4`; v1 `normalized_text` remains the only text field.

---

## 5. Explicit non-goals

- No change to `Norm — Normalize Dict`
- No change to `Norm — Normalize Sem attrs`
- No RX/OTC, Age, MNN, or `product_kind` inference in this node
- No SearXNG / LLM / DB writes
- Do not activate `rx-otc-product-retrieval-dev` as part of Norm v4
