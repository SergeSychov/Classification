# M5.1 Norm v4.1 remediation — data dictionary

Policy: `norm_v4_1_offline_pack_and_retrieval_remediation`
Date: 2026-08-20

M5.0 fields are copied unchanged. New columns are `*_v4_1` only.

## Inputs (SHA256 at run start)

- `mnn_norm_v4_experiment_full.csv`: `7a33e7423b8e94aa7c3f36f888b46f8c9bbfe013bdc1e9d054f9d628b41b5473`
- `mnn_norm_v4_experiment_text_quality.csv`: `e519c8212cbbeccc95e43105fd726d272352dc5032e5e800bbff77342a92c49c`
- `mnn_norm_v4_experiment_human_review.csv`: `07910f68ffe93a8d129778a4751e5bf9a4f936219f161f7fce3fef3d56303674`
- `mnn_norm_v4_experiment_human_reviewed.csv`: `d06fd739a1de9aaf2f982f2808c72d0c5c78efa8298b64a05f4c40260a743c43`
- `mnn_norm_v4_experiment_exceptions.csv`: `fd53e01059c237bd15864832ab6fa2a8333a106ac8e0f274adaadb9bcb09d110`
- `mnn_norm_v4_experiment_summary.json`: `7d8e1bdfc07342d2b089f72d59e6015d57e094a5025564df25135cd94edf0781`
- `mnn_norm_v4_experiment_summary.md`: `7f4b947676809e9454d88c08780ddfc14e8d2d6bd5acf661af15efe2414c985d`
- `m5_norm_v4_design.md`: `85e0a641bf4b817feaeea59b728a7408adaf85c01567fcf8267fa3d96adb3a4c`
- `m5_norm_v4_future_n8n_plan.md`: `35e8250a2b0f16af479a1c42b731c07b1209dc6358ce910e00f0d63fc1e9c603`
- `mnn_norm_v4_experiment.py`: `19947797e06ec094f36d2a444cb5fba4535c729f154885e11c3d936a96a4189d`
- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`: `ec167da556040e71e458c6bc74ba832b9f5cc60372d4e6e3de346f1373f93f5b`
- `mnn_identity_enrichment_pass_review_text_quality_v1.csv`: `2ad6c69e6f7bfac410ec2270f7c1d608fdf45fdd48fdd66564405cd6c2d4c344`
- `mnn_identity_enrichment_pass_results.csv`: `be3e8c74ec63c303261ae2aa3d7a79fbf545e2b7df60f4b9e5c485d276f94736`
- `mnn_identity_enrichment_pass_research_context.csv`: `7fe535fd4bf4dc9c22df995e61f3c542fd84be84275e5becd23a863d12a45146`

## New v4.1 fields

| Field | Meaning |
|-------|---------|
| `enrichment_query_text_v4_1` | Compact product query; no manufacturer |
| `enrichment_query_disambiguator_v4_1` | Manufacturer (or retained multi-entity string) |
| `enrichment_retrieval_text_v4_1` | query + `, ` + disambiguator when disambiguator non-empty |
| `container_type_raw_v4_1` | Exact source container marker |
| `container_type_v4_1` | Canonical container or `unknown` |
| `unit_content_amount_v4_1` | Volume/mass of one unit (not strength, not count) |
| `pack_unit_count_v4_1` | `N<n>` consumer units |
| `pack_structure_raw_v4_1` | Source presentation fragment |
| `pack_structure_v4_1` | Canonical presentation |
| `pack_parse_status_v4_1` | parsed / partial / ambiguous / not_applicable |
| `product_name_raw_v4_1` | Source product-head name core |
| `manufacturer_prefix_raw_v4_1` | Detected manufacturer prefix in head |
| `product_name_remainder_raw_v4_1` | Head remainder after prefix+form |
| `product_name_recovery_status_v4_1` | not_applicable / recovered / ambiguous / unresolved |
| `review_findings_v4_1` | JSON of imported M5.0 labels + M5.1 resolution |
| `m5_1_resolution_status` | resolved / partially_resolved / still_open / not_applicable |

Do not treat blank M5.0 labels as `yes`.

