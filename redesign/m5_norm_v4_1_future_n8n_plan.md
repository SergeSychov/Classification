# M5.1 — Future Norm v4.1 n8n plan (design only)

**Status:** DESIGN ONLY. No workflow edit, no Code-node implementation, no deploy, no wiring.  
**Date:** 2026-08-20  
**Depends on:** offline remediation `norm_v4_1_offline_pack_and_retrieval_remediation` + human review of `mnn_norm_v4_1_remediation_human_review.csv`.

This is not authorization to patch `classification-stage2-hierarchy-dev` or prod Stage 2.  
M5.0 is **not** accepted for rollout. Do not implement v4.0 query text as the retrieval default.

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
  → Norm — Product Text v4.1          # NEW Code node; parallel *_v4_1 fields only
  → Load — Limit Batch
```

Do **not** replace `Norm — Normalize Product`.  
Do **not** overwrite `normalized_text`.  
Do **not** put v4.1 on prod `classification-stage2-dev`.  
Do **not** reuse M5.0 `enrichment_query_text_v4` as the retrieval string.

If a later consumer needs retrieval, it should read `enrichment_retrieval_text_v4_1` (product + manufacturer), not the base query alone. Not implemented here.

---

## 2. Code-node contract (`...item.json`)

Follow Stage 2 conventions (`Categories/stage2_workflow_contract.md`):

- Input: `item.json` from `Norm — Normalize Product`
- Output: `{ json: { ...j, <v4.1 fields> }, pairedItem: index }`
- Constants from `item.json.constants` with local fallback
- Do not `$('…')` into parallel branches
- No HTTP, no LLM, no Postgres in the Code node

### Input (read)

| Field | Use |
|-------|-----|
| `normalized_text` | Source string (v1). Never overwritten |
| `product_id` | Pass-through |
| existing `normalize_meta` / `norm_*` | Pass-through |
| optional M5.0 `*_v4` | Pass-through if already present; do not reinterpret |

### Output (add only)

Parallel v4.1 fields from the offline script, including at minimum:

```text
normalized_text_full_v4_1
product_identity_text_v4_1
enrichment_query_text_v4_1
enrichment_query_disambiguator_v4_1
enrichment_retrieval_text_v4_1
brand_or_product_name_v4_1
dosage_form_v4_1
dosage_form_raw_v4_1
strength_v4_1
container_type_raw_v4_1
container_type_v4_1
unit_content_amount_v4_1
pack_unit_count_v4_1
pack_structure_raw_v4_1
pack_structure_v4_1
manufacturer_v4_1
manufacturer_short_v4_1
product_name_raw_v4_1
manufacturer_prefix_raw_v4_1
product_name_remainder_raw_v4_1
```

`cascade_trace.stages[]` append `{ stage: 'normalize_v4_1', notes: 'product_norm_v4_1_parallel' }`.

Parser source of truth: port `scripts/mnn_norm_v4_1_remediation.py` into `scripts/hierarchy_nodes/norm_product_text_v4_1.js` **when implementation is asked**. Until then, JS is not created. Do not overwrite a hypothetical v4.0 JS port.

---

## 3. Migration strategy

```text
1. Parallel *_v4_1 fields first
2. No overwrite of normalized_text
3. Downstream still reads normalized_text until a later explicit switch
4. Default future retrieval text = enrichment_retrieval_text_v4_1
   (query without manufacturer + disambiguator)
```

| Phase | `normalized_text` | v4.1 fields | Consumers |
|-------|-------------------|-------------|-----------|
| Now (M5.1) | unchanged | artifacts only | none |
| hierarchy-dev log-only | unchanged | written on item + log JSON | log/audit |
| allowlist | unchanged | item fields | optional retrieval on allowlist SKUs |
| prod | blocked | blocked | blocked until approval |

---

## 4. Safe rollout

```text
offline reviewed remediation
  → human review (label_norm_v4_1_*)
  → hierarchy-dev log-only (Load still WHERE false or tiny allowlist)
  → controlled allowlist
  → no prod until explicit approval
```

Gates before any live wiring:

- Human review of the 50-row M5.1 sample: identity, query, manufacturer, pack structure, product-name role
- Exception rows inspected (partial pack, manufacturer-prefix, Гепарин container-absent)
- Chunk size ≤ 10 if any later LLM consumer is involved (n8n execution contract)
- Kill switch / Load stub restored after smoke
- Do not enable error-workflow autoresume while the task runner is unhealthy

Rollback: delete/unwire `Norm — Product Text v4.1`; v1 `normalized_text` remains the only text field.

---

## 5. Explicit non-goals (this task and any future wiring)

- No change to `Norm — Normalize Dict`
- No change to `Norm — Normalize Sem attrs`
- No overwrite of M5.0 v4 fields as the live contract
- No RX/OTC, Age, MNN, or `product_kind` inference in this node
- No SearXNG / LLM / DB writes
- Do not activate `rx-otc-product-retrieval-dev` as part of Norm v4.1
- No wiring or deploy in M5.1
