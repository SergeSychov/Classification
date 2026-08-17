# Data dictionary — mnn_identity_enrichment_pass_human_review_v2

## Purpose

Audit-ready review sheet for post-identity-gate MNN enrichment pass (run 461).

**`display audit resolution != production attribute update`.**

This file does **not** change `attr_rx_otc`, `attr_age_segment`, snapshot,
`product_classification`, Sem, or live Stage2 decisions.

## Preserved columns

All columns from `mnn_identity_enrichment_pass_human_review.csv` are copied
unchanged (including empty `label_*` fields).

## Added final display fields

| Column | Meaning | Allowed values |
|--------|---------|----------------|
| `final_rx_otc` | Audit display RX/OTC | `rx`, `otc`, `not_applicable`, `unknown`, `conflict`, empty |
| `final_age` | Audit display age | `дети`, `взрослые`, `универсальный`, `not_applicable`, `unknown`, `conflict`, empty |

## Provenance fields

For each of RX/OTC and Age:

| Column | Meaning |
|--------|---------|
| `final_*_method` | How display value was chosen |
| `final_*_stage` | Pipeline stage of chosen value |
| `final_*_source` | Artifact/table provenance |
| `final_*_confidence` | `high` / `medium` / `low` / `unknown` / `not_applicable` |
| `final_*_reason` | Short audit reason (≤300 chars) |

### method values
`sem_baseline`, `catalog`, `input_explicit`, `previous_enrichment`,
`identity_enrichment`, `not_resolved`, `conflict`, `not_applicable`

### stage values
`sem0`, `sem1`, `norm`, `catalog_resolution`, `primary_llm`,
`previous_mnn_enrichment`, `mnn_identity_enrichment`, `none`, `multiple_conflict`

### source values
`product_classification`, `product_classification_log`,
`sem_wave500_mnn_v3_report`, `mnn_catalog_resolution_wave500_v3`,
`mnn_identity_enrichment_pass_results`,
`mnn_identity_enrichment_pass_searxng_raw`, `research_summary`,
`none`, `multiple`

## Candidate / source snapshot columns

| Column | Meaning |
|--------|---------|
| `sem_rx_otc` / `sem_age` | From Sem v3 report attrs (and DB semantic_attrs if readable) |
| `catalog_rx_otc` / `catalog_age` | From identity-gate/baseline catalog resolved fields only when non-unknown |
| `previous_enrichment_rx_otc` / `previous_enrichment_age` | From baseline v3 enrichment payload |
| `identity_enrichment_rx_otc` / `identity_enrichment_age` | From run 461 results / research / validated raw |
| `rx_otc_candidates_json` / `age_candidates_json` | Compact JSON array ≤8 `{value,method,stage,source,confidence}` |

## Display resolution priority (audit only)

1. Identity enrichment run 461 — only if `status=ok`, Category=Drug, normalizable value, evidence present
2. Previous enrichment — only if previous status ok and value present
3. Sem baseline attrs — only if present; must not override stronger valid enrichment without conflict flag
4. Catalog resolved attrs — only if artifact contains them for the product
5. BAS/Other → `not_applicable`
6. Conflicting valid enrichment sources → `conflict`
7. Nothing available → `unknown` / `not_resolved`

Forbidden: inventing OTC/универсальный from empty fields; LLM/search; using unidentified catalog pages.

## Review flags

| Column | Meaning |
|--------|---------|
| `needs_human_review_mnn` | From existing MNN review/unresolved signals (not recalculated business) |
| `needs_human_review_rx_otc` | true on conflict/unknown-for-drug/invalid |
| `needs_human_review_age` | true on conflict/unknown-for-drug/invalid |
| `needs_human_review_any` | OR of the three |
| `review_priority` | `high` / `medium` / `low` |
| `review_focus` | JSON array of focus areas |
| `audit_data_gaps` | `;`-separated missing-data notes |

## Manual label fields (do not auto-fill)

| Column | Reviewer task |
|--------|---------------|
| `label_mnn` | Correct MNN if needed |
| `label_rx_otc` | Correct RX/OTC |
| `label_age` | Correct age segment |
| `label_rx_otc_notes` | Free-text RX notes |
| `label_age_notes` | Free-text age notes |
| `label_source_match` | Whether catalog/enrichment matched same product |
| `label_final_method` | Agree/disagree with final_mnn_method |
| `label_notes` | General notes |

Reviewer should compare `final_*` display values against candidates and evidence URLs,
then write labels only in label columns.
