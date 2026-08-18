# mnn_rx_otc_source_audit_v1 data dictionary

Offline source audit of existing Wave-500 RX/OTC review-error evidence.
Does not correct RX/OTC values.

## Inputs (read-only)

- `mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv`
- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`
- `mnn_identity_enrichment_pass_results.csv`
- `mnn_identity_enrichment_pass_research_context.csv`
- `mnn_identity_enrichment_pass_searxng_raw.jsonl`

## Outputs

- `mnn_rx_otc_source_audit_v1.csv` — one row per RX/OTC error case
- `mnn_rx_otc_source_audit_v1_summary.md`
- `mnn_rx_otc_source_audit_v1_summary.json`
- `mnn_rx_otc_source_audit_v1_data_dictionary.md`
- `scripts/mnn_rx_otc_source_audit_v1.py`

## Key fields

| field | meaning |
|---|---|
| `final_rx_otc*` | current pipeline RX/OTC fields (unchanged copies) |
| `label_rx_otc` / `label_notes` / `manual_expected_rx_otc_hint` | human review provenance |
| `rx_otc_source_best_type` | taxonomy class of best saved URL |
| `rx_otc_source_best_url` | best URL under ranking rules |
| `rx_otc_source_product_specificity` | product_specific / brand_form_specific / brand_only / generic / unknown |
| `rx_otc_source_identity_grade` | A/B/C/D/unknown from brand/form/dose match to SKU text |
| `rx_otc_source_contains_explicit_status` | yes/no/unclear from saved titles/excerpts only |
| `rx_otc_existing_evidence_sufficient` | yes only if GRLS/official + specificity + A/B + explicit + no conflict |
| `rx_otc_existing_evidence_gap` | primary gap label or `multiple` |
| `rx_otc_root_cause_primary` | single root-cause bucket |

## Source taxonomy

- `grls_official`
- `official_instruction_or_manufacturer`
- `rls_or_vidal_product_card`
- `pharmacy_product_card`
- `generic_mnn_or_molecule_page`
- `regulatory_context_not_product_specific`
- `search_snippet_or_unknown`
- `other`

## Sufficient rule

`yes` iff best source is `grls_official` or `official_instruction_or_manufacturer`
AND specificity in (`product_specific`, `brand_form_specific`)
AND identity grade in (`A`, `B`)
AND explicit status = `yes`
AND no comparable-source conflict.
