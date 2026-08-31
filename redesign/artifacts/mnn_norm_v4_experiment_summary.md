# mnn_norm_v4_experiment summary

M5.0 offline Norm v4 experiment. Audit/analysis only.
Current `normalized_text` is **not** replaced. No web / LLM / DB / n8n.
No attr / snapshot / product_kind / prod / Sem changes.

Policy: `norm_v4_experiment_m5_0` · date 2026-08-19

## Preflight

- expected rows: **100**
- actual rows: **100**
- unique product_id: **100**
- required `normalized_text` present: **True**
- count mismatch vs 100: **False**
- duplicate product_id: **0**
- all review ids in results: **True**
- research_context overlap: **55**
- optional age file present: **True**

### Input SHA256 (script does not modify inputs)

- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`: `ec167da556040e71e458c6bc74ba832b9f5cc60372d4e6e3de346f1373f93f5b`
- `mnn_identity_enrichment_pass_review_text_quality_v1.csv`: `2ad6c69e6f7bfac410ec2270f7c1d608fdf45fdd48fdd66564405cd6c2d4c344`
- `mnn_identity_enrichment_pass_results.csv`: `be3e8c74ec63c303261ae2aa3d7a79fbf545e2b7df60f4b9e5c485d276f94736`
- `mnn_identity_enrichment_pass_research_context.csv`: `7fe535fd4bf4dc9c22df995e61f3c542fd84be84275e5becd23a863d12a45146`
- `mnn_age_threshold_reconciliation_reviewed_v1_1.csv`: `9b853de53c9f61343cefc28764582c5433906afabdc288feb95957bd55e9bd2f`

## Length metrics (characters)

- source `normalized_text`: min=37, median=82.0, p90=124.1, max=214
- `normalized_text_full_v4`: min=45, median=85.0, p90=110.5, max=133
- `product_identity_text_v4`: min=34, median=57.5, p90=78.0, max=88
- `enrichment_query_text_v4`: min=19, median=31.5, p90=44.0, max=66

## Manufacturer / pack dedupe

- rows with duplicated manufacturer before: **100**
- rows deduplicated (mfr): **100**
- mfr dedup_count distribution: `{'1': 49, '2': 51}`
- rows with duplicated pack before: **14**
- rows deduplicated (pack): **14**
- pack dedup_count distribution: `{'0': 86, '1': 14}`

## Structured extraction coverage

- brand: **100** / 100 (100.0%)
- brand_extracted: **100** / 100 (100.0%)
- form_non_unknown: **99** / 100 (99.0%)
- strength: **84** / 100 (84.0%)
- pack: **100** / 100 (100.0%)
- manufacturer: **100** / 100 (100.0%)

## Flag distribution

- `manufacturer_conflict`: 0
- `missing_brand`: 0
- `missing_form`: 1
- `missing_strength`: 16
- `missing_pack`: 0
- `parse_ambiguous`: 3
- `multi_component_strength`: 8
- `manufacturer_deduped`: 100
- `pack_deduped`: 14
- `manufacturer_multi_entity`: 2
- `missing_manufacturer`: 0

## Safety diff

- exception rows: **3**
- empty v4 with non-empty source: **0**
- product_id duplicates in output: **0**
- brand token preserved (no possible_brand_loss): **100**
- strength tokens retained in full_v4 (no possible_strength_loss): **100**
- pack tokens retained in full_v4 (no possible_pack_loss): **100**
- canonical manufacturer occurs in original (non-conflict rows with mfr): **100**

Safety flag counts:

- `ambiguous_parse`: 3
- `manufacturer_conflict`: 0
- `possible_brand_loss`: 0
- `possible_form_loss`: 0
- `possible_pack_loss`: 0
- `possible_strength_loss`: 0

## Human-review sample (N=50, labels empty)

- requested: {'manufacturer_duplicates': 15, 'pack_duplicates': 10, 'multi_component_strength': 10, 'herbal_or_form_special': 5, 'distinct_manufacturer_segments': 5, 'ordinary': 5}
- actual size: **50**
- actual composition: `{'manufacturer_duplicates': 15, 'pack_duplicates': 10, 'multi_component_strength': 8, 'herbal_or_form_special': 5, 'distinct_manufacturer_segments': 2, 'ordinary': 5, 'fill_flagged': 5}`
- product_id list: `['8', '28', '34', '45', '54', '56', '68', '70', '72', '73', '75', '88', '92', '249', '354', '456', '486', '777', '844', '884', '1053', '1668', '1765', '2023', '2348', '2621', '3027', '3065', '3556', '3759', '3763', '3781', '4133', '4403', '4481', '4487', '4593', '4684', '4922', '4924', '5010', '5258', '5267', '5270', '8055', '13125', '14758', '20614', '22468', '24750']`

## Representative before/after (5)

### 1. product_id=68

- before: `ЭПЛЕРЕНОН-ТЕВА 25мг N30 таб. покрытые пленочной оболочкой Тева фармасьютикал воркс прайвэт Лимитед Компани | Тева фармасьютикал воркс прайвэт Лимитед Компани | Тева фармасьютикал воркс прайвэт Лимитед Компани | N30`
- full_v4: `ЭПЛЕРЕНОН-ТЕВА; таблетки, покрытые пленочной оболочкой; 25 мг; N30; производитель: Тева фармасьютикал воркс прайвэт Лимитед Компани`
- identity_v4: `Эплеренон-Тева; таблетки; 25 мг; N30; Тева фармасьютикал воркс прайвэт Лимитед Компани`
- query_v4: `Эплеренон-Тева таблетки 25 мг N30`

### 2. product_id=88

- before: `ГЕСПЕРИДИН+ДИОСМИН 100мг+900мг N30 таб. покрытые пленочной оболочкой Алиум АО | Алиум АО | Алиум АО | N30`
- full_v4: `ГЕСПЕРИДИН+ДИОСМИН; таблетки, покрытые пленочной оболочкой; 100 мг + 900 мг; N30; производитель: Алиум АО`
- identity_v4: `Гесперидин+Диосмин; таблетки; 100 мг + 900 мг; N30; Алиум АО`
- query_v4: `Гесперидин+Диосмин таблетки 100 мг + 900 мг N30`

### 3. product_id=13616

- before: `МЕЛИССЫ ЛЕКАРСТВЕННОЙ ТРАВА Ф/П 1,5Г №20 ЗДОРОВЬЕ | ЗДОРОВЬЕ ФИРМА ООО | ЗДОРОВЬЕ ФИРМА ООО`
- full_v4: `МЕЛИССЫ ЛЕКАРСТВЕННОЙ; трава, фильтр-пакеты; 1.5 г; N20; производитель: ЗДОРОВЬЕ ФИРМА ООО`
- identity_v4: `Мелиссы Лекарственной; фильтр-пакеты; 1.5 г; N20; ЗДОРОВЬЕ ФИРМА ООО`
- query_v4: `Мелиссы Лекарственной фильтр-пакеты 1.5 г N20`

### 4. product_id=5270

- before: `ТАМИФЛЮ КАПС. 75МГ №10 | ДЕЛФАРМ МИЛАНО С.Р.Л./Ф.ХОФФМАНН-ЛЯ РОШ ЛТД/СЕНЕКСИ С.А.С. | ДЕЛФАРМ МИЛАНО С.Р.Л./Ф.ХОФФМАНН-ЛЯ РОШ ЛТД/СЕНЕКСИ С.А.С.`
- full_v4: `ТАМИФЛЮ; капсулы; 75 мг; N10; производитель: ДЕЛФАРМ МИЛАНО С.Р.Л./Ф.ХОФФМАНН-ЛЯ РОШ ЛТД/СЕНЕКСИ С.А.С.`
- identity_v4: `Тамифлю; капсулы; 75 мг; N10; ДЕЛФАРМ МИЛАНО С.Р.Л./Ф.ХОФФМАНН-ЛЯ РОШ ЛТД/СЕНЕКСИ С.А.С.`
- query_v4: `Тамифлю капсулы 75 мг N10`

### 5. product_id=3065

- before: `ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО`
- full_v4: `ФЛУКОНАЗОЛ-OBL; капсулы; 150 мг; N4; производитель: ОБОЛЕНСКОЕ ФП АО`
- identity_v4: `Флуконазол-OBL; капсулы; 150 мг; N4; ОБОЛЕНСКОЕ ФП АО`
- query_v4: `Флуконазол-OBL капсулы 150 мг N4`

## Isolation

```text
offline experiment only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```

## Future rollout (design only)

See `redesign/m5_norm_v4_future_n8n_plan.md`. Parallel v4 fields first; do not overwrite
`normalized_text` until explicit approval. hierarchy-dev log-only → allowlist → no prod.

