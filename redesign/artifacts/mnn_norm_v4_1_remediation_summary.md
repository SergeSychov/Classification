# M5.1 Norm v4.1 remediation summary

**Policy:** `norm_v4_1_offline_pack_and_retrieval_remediation`  
**Date:** 2026-08-20  
**Rows:** 100 (unique product_id=100)

M5.0 is a historical baseline and was **not overwritten**. M5.0 is **not** accepted for hierarchy-dev / n8n rollout.

## Isolation

```text
offline reviewed remediation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```

## Preflight input SHA256

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

## M5.0 human-review labels

| Label | yes | no | uncertain | blank |
|-------|-----|----|-----------|-------|
| identity_preserved | 41 | 4 | 5 | 0 |
| query_appropriate | 41 | 3 | 6 | 0 |
| manufacturer_correct | 50 | 0 | 0 | 0 |

Reviewed file rows: **50**. Rows with ≥1 no/uncertain: **9**.

### Notes (non-empty)

- `54` (no/no): severity=major; reason=unit_volume_and_container_lost; source_pack="амп. 5 мл N5"; actual_pack="N5"; expected="амп. 5 мл N5"; action="add_container_and_unit_content_fields"
- `844` (uncertain/uncertain): severity=policy_needed; reason=container_not_structured; source_pack="фл. 2.5 мл"; actual_pack="2.5 мл"; expected="фл. 2.5 мл; count=1"; action="add_container_and_unit_content_fields"
- `1053` (uncertain/uncertain): severity=policy_needed; reason=container_not_structured; source_pack="фл. 100 мл"; actual_pack="100 мл"; expected="фл. 100 мл; count=1"; action="add_container_and_unit_content_fields"
- `2348` (uncertain/uncertain): severity=policy_needed; reason=container_not_structured; source_pack="фл. 100 мл"; actual_pack="100 мл"; expected="фл. 100 мл; count=1"; action="add_container_and_unit_content_fields"
- `3763` (no/uncertain): severity=critical; reason=brand_role_misattributed_and_product_name_loss; source_head="ФАРМГРУПП НАСТОЙКА 5 ТРАВ УСПОКОИТЕЛЬНАЯ"; source_manufacturer="ФАРМГРУПП ООО"; actual_brand="Фармгрупп"; expected_brand="5 трав успокоительная"; lost_tokens="5 трав|успокоительная"; actual_query="Фармгрупп настойка 250 мл"; expected_query="5 трав успокоительная настойка флакон 250 мл"; action="add_manufacturer_prefix_detection_and_name_recovery_rule"
- `4487` (no/no): severity=major; reason=unit_volume_and_container_lost; source_pack="амп. 5 мл N10"; actual_pack="N10"; expected="амп. 5 мл N10"; action="add_container_and_unit_content_fields"
- `4922` (uncertain/uncertain): severity=policy_needed; reason=container_not_structured; source_pack="фл. 30 г"; actual_pack="30 г"; expected="фл. 30 г; count=1"; action="add_container_and_unit_content_fields"
- `4924` (uncertain/uncertain): severity=policy_needed; reason=container_not_structured; source_pack="фл. 30 г"; actual_pack="30 г"; expected="фл. 30 г; count=1"; action="add_container_and_unit_content_fields"
- `8055` (no/no): severity=major; reason=unit_volume_and_container_lost; source_pack="фл. 5 мл N1"; actual_pack="N1"; expected="фл. 5 мл N1"; action="add_container_and_unit_content_fields"

## M5.1 resolution of M5.0 defects

- resolved: **8**
- partially_resolved: **1**
- still_open: **0**
- not_applicable: **91**

### Per defect row

- `54`: partially_resolved — Restored unit volume 5 мл and N5 in query/retrieval; kept 5000 ЕД/мл as strength. Source has no амп./ампула marker, so container stays unknown (not inferred). Reviewer note source_pack=амп. 5 мл N5 does not match actual source.
- `844`: resolved — Structured флакон + 25 мл (source ФЛ. 25МЛ). Reviewer note 2.5 мл was a copy-paste error vs source.
- `1053`: resolved — Structured флакон + 2.5 мл from source ФЛ. 2,5МЛ. Reviewer note фл. 100 мл was a copy-paste error.
- `2348`: resolved — Structured флакон + 100 мл from source ФЛ. 100МЛ. Strength left empty (none in source).
- `3763`: resolved — Manufacturer prefix stripped from brand; remainder 5 трав успокоительная used. Query keeps remainder+настойка+флакон+250 мл; retrieval adds ФАРМГРУПП ООО. Flagged product_name_variant_needs_policy (no invented 'средство').
- `4487`: resolved — Structured ампула + 5 мл + N10 from source АМП. 5МЛ №10. Strength 50 мг/мл kept.
- `4922`: resolved — Structured флакон + 30 г from source ФЛ. 30Г.
- `4924`: resolved — Structured туба + 15 г from actual source ТУБА 15Г. Reviewer note фл. 30 г was a copy-paste error.
- `8055`: resolved — Structured флакон + 5 мл + N1 from source ФЛ. 5МЛ №1. Multi-component strength kept.

## Retrieval policy

- query mean/p50/p90 chars: 35.64 / 34.0 / 47.1
- retrieval mean/p50/p90 chars: 54.76 / 54.0 / 74.0
- rows with non-empty disambiguator: **100** / 100
- retrieval join mismatches: **0**
- query manufacturer leaks: **0**

Base query does not include manufacturer. Retrieval = query + `, ` + disambiguator when disambiguator is non-empty.

## Pack structure coverage

- explicit container (not unknown/empty): **17**
- unit amount present: **30**
- explicit N count (source N/№/No): **83**
- inferred N1: **12**
- status parsed/partial/ambiguous/not_applicable: **95** / **5** / **0** / **0**
- query gained container: **17**
- query gained unit amount: **6**
- query gained pack count: **12**

## Manufacturer-prefix recovery

- detected: **1**
- recovered: **1**
- ambiguous: **0**
- unresolved: **0**

### product_id=3763

- brand_or_product_name_v4_1: `5 трав успокоительная`
- prefix: `ФАРМГРУПП`
- remainder: `5 ТРАВ УСПОКОИТЕЛЬНАЯ`
- query: `5 трав успокоительная настойка флакон 250 мл N1`
- retrieval: `5 трав успокоительная настойка флакон 250 мл N1, ФАРМГРУПП ООО`

## Dosage-form policy

- 3759: `гранулы` (must be гранулы, not порошок)
- 22548: `драже` (must be драже, not таблетки)
- 9941: `ополаскиватель` (must be ополаскиватель, not unknown)

## Regression

- checks: **60**; pass **60**; fail **0**

## Exceptions / human-review sample

- exceptions: **7**
- exception reasons: `{"m50_defect_partially_resolved": 1, "manufacturer_prefix_in_product_name": 1, "pack_parse_status=partial": 5}`
- human-review sample: **50**
- strata: `{"m50_label_no": 3, "manufacturer_prefix_recovery": 1, "m50_label_uncertain": 5, "dosage_form_vocab_policy": 3, "ordinary_successfully_remediated": 22, "pack_container_amount_count": 2, "single_container_implicit_n1": 6, "multi_component_strength_pack": 6, "retained_multi_entity_manufacturer": 2}`
- mandatory IDs present: `8, 54, 844, 1053, 2348, 3763, 4487, 4922, 4924, 8055, 3759, 22548`

## Output SHA256

- `mnn_norm_v4_1_remediation_full.csv`: `466c6164ef8b13be70ab61795de5c9e0c12cdee061e4e7869282d230b25d7470`
- `mnn_norm_v4_1_remediation_summary.md`: `13ad2a1c33f4182c49fc91c54c7950b12d149d7d02b3512b6d9b2361e99df6e5`
- `mnn_norm_v4_1_remediation_text_quality.csv`: `9fbd0315eaa9c96293a33bc81223e3ae7e962826da1ecd94c1139d968893a1b0`
- `mnn_norm_v4_1_remediation_human_review.csv`: `f51d76195dc1d3cfb404f9b67cada4d0aa1f5f92d36c6bc95a76606570dc88ef`
- `mnn_norm_v4_1_remediation_exceptions.csv`: `827f7632f5812d6138381854f7b395cdf0d4077a054242a94e986386b0a450bb`
- `mnn_norm_v4_1_remediation_data_dictionary.md`: `921169455657170e639fabee4ba99b734b14362c51de80c2683da597d2e8d440`
- `mnn_norm_v4_1_remediation_regression_cases.csv`: `9c9187829a7ae6b4752c1c7671d93e8c83a8df1b23b5174c67bb779d0922a392`
- `mnn_norm_v4_1_remediation_summary.json`: `b6edc5d3ba90bb9fab02d79931ce59c760004f67e3057b02c68d9ba5c63c9283`

## Next

- Human labels on `label_norm_v4_1_*` in the new 50-row sample.
- No hierarchy-dev / n8n wiring in this task.
- No overwrite of `normalized_text`.

