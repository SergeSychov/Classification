# mnn_norm_v4_experiment data dictionary

M5.0 offline Norm v4 text-normalization experiment (Wave-500 human-review v2, N=100).
Does **not** overwrite current `normalized_text`. Does **not** change the Norm node,
n8n, PostgreSQL, `attr_*`, snapshots, or `product_kind`.

Policy version: `norm_v4_experiment_m5_0`
Date: 2026-08-19

## Inputs (read-only)

- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv` — SHA256 `ec167da556040e71e458c6bc74ba832b9f5cc60372d4e6e3de346f1373f93f5b`
- `mnn_identity_enrichment_pass_review_text_quality_v1.csv` — SHA256 `2ad6c69e6f7bfac410ec2270f7c1d608fdf45fdd48fdd66564405cd6c2d4c344`
- `mnn_identity_enrichment_pass_results.csv` — SHA256 `be3e8c74ec63c303261ae2aa3d7a79fbf545e2b7df60f4b9e5c485d276f94736`
- `mnn_identity_enrichment_pass_research_context.csv` — SHA256 `7fe535fd4bf4dc9c22df995e61f3c542fd84be84275e5becd23a863d12a45146`
- `mnn_age_threshold_reconciliation_reviewed_v1_1.csv` — SHA256 `9b853de53c9f61343cefc28764582c5433906afabdc288feb95957bd55e9bd2f`

## Outputs

- `mnn_norm_v4_experiment_full.csv` — one row per input product; original columns preserved; v4 fields added
- `mnn_norm_v4_experiment_text_quality.csv` — before/after length and dedupe flags
- `mnn_norm_v4_experiment_human_review.csv` — stratified N=50; label fields empty
- `mnn_norm_v4_experiment_exceptions.csv` — safety/conflict/ambiguous rows
- `mnn_norm_v4_experiment_summary.md` / `.json`
- `scripts/mnn_norm_v4_experiment.py`

Related design (not applied):

- `redesign/m5_norm_v4_design.md`
- `redesign/m5_norm_v4_future_n8n_plan.md`

## New v4 fields

| field | meaning |
|---|---|
| `normalized_text_full_v4` | Audit display: brand (source case), form, strength, pack, one manufacturer |
| `product_identity_text_v4` | Compact identity gate text; display-normalized brand; `[missing_*]` placeholders |
| `enrichment_query_text_v4` | Query without manufacturer |
| `enrichment_query_disambiguator_v4` | Manufacturer only, for optional query disambiguation |
| `brand_or_product_name_v4` | Trade name / product name; never replaced by MNN |
| `dosage_form_v4` | Canonical form vocabulary or `unknown` |
| `dosage_form_display_v4` | Longer form phrase for audit text |
| `dosage_form_raw_v4` | Matched raw form token |
| `strength_v4` | Normalized strength; multi-component joined with ` + ` |
| `pack_v4` | `N##` or quantity mass/volume when that is the pack |
| `volume_or_fill_v4` | Vial/tube/packet fill that is not the pack count |
| `manufacturer_v4` | Canonical manufacturer; conflict keeps all joined with ` / ` |
| `manufacturer_short_v4` | Short display token |
| `normalization_flags_v4` | Pipe-joined flags |
| `normalization_warnings_v4` | Human-readable warnings; flagged rows are not auto-fixed |
| `manufacturer_dedup_count_v4` | Extra manufacturer copies removed |
| `pack_dedup_count_v4` | Extra pack copies removed |
| `source_segment_count_v4` | `|` segments in original |
| `retained_segment_count_v4` | Structured chunks kept |
| `safety_flags_v4` | Semantic preservation / destruction flags |
| `*_loss_v4` / `manufacturer_conflict_v4` / `ambiguous_parse_v4` | Boolean safety columns |

## Canonical dosage forms

`таблетки`, `капсулы`, `раствор`, `крем`, `мазь`, `гель`, `спрей`, `лак`, `капли`, `сироп`, `суспензия`, `порошок`, `суппозитории`, `фильтр-пакеты`, `трава`, `настойка`, `unknown`

## Flags

`manufacturer_deduped`, `pack_deduped`, `manufacturer_conflict`, `manufacturer_multi_entity`,
`missing_brand`, `missing_form`, `missing_strength`, `missing_pack`, `missing_manufacturer`,
`multi_component_strength`, `parse_ambiguous`

## Safety flags

`possible_brand_loss`, `possible_form_loss`, `possible_strength_loss`, `possible_pack_loss`,
`manufacturer_conflict`, `ambiguous_parse`, `empty_output`, `manufacturer_not_in_original`

## Hard rules

- Original `normalized_text` is copied, never overwritten.
- Do not infer drug/non-drug, RX/OTC, Age, category, or MNN.
- Distinct manufacturers are not collapsed arbitrarily.
- Clinical identity tokens (form, strength, pack, brand) are retained or flagged.

