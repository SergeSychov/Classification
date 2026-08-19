# mnn_age_threshold_reconciliation_reviewed_v1_1 summary

M4.2.2 reviewed Age mapping v1.1. Accepts explicit integer min years 0–18
(including 10). Does not overwrite v1. Audit only. No DB / routing / attr write.

## 1. Preflight

- labelled follow-up: `mnn_age_threshold_reconciliation_v1_followup - mnn_age_threshold_reconciliation_v1_followup.csv`
- generated follow-up: `mnn_age_threshold_reconciliation_v1_followup.csv`
- source reconciliation: `mnn_age_threshold_reconciliation_v1.csv`
- pilot rows: **40**; unique: **40**
- follow-up rows: **7**; subset of pilot: **True**
- filled min/scope/segment/notes: 7/7/7/7

Manual min vocabulary (as labelled, including invalid):

| value | n |
|---|---|
| `0` | 5 |
| `10` | 1 |
| `6` | 1 |

Manual scope vocabulary:

| value | n |
|---|---|
| `children_and_adults` | 7 |

Manual segment vocabulary:

| value | n |
|---|---|
| `универсальный` | 7 |

- invalid-vocabulary rows: **0** `[]`
- in-vocab contract-conflict / normalize rows: **0** `[]`

### Input SHA256 (unchanged)

- `redesign/artifacts/mnn_age_policy_replay_v2_drug_age_pilot_sample.csv`: `ba887ded2499287874d694cc576930e117728f7ce943e7340cb0d63704f5fcf7`
- `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1.csv`: `eb267c0f40cfe4b78464584a48d5cb07438abb556dce18d1b5598df3c043411d`
- `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1_data_dictionary.md`: `2b2e84ac033dbfcc8caa77ebc35ba713ae6b9499970e7893592861f53e6b5f22`
- `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1_exceptions.csv`: `c90b188000db305d36f69991651175ffe2a2ff9a2771779024d31187f4d54d76`
- `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1_human_review.csv`: `11202c98f12e6bc66481ac39ac6b50a4247f7d4e71ac082a065cc3b784397373`
- `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1_summary.json`: `32b7addf7095532d481d39ab8f6ddd9b4811b3b984b6bec562fe2a4c6d166efb`
- `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1_summary.md`: `12a193a0ce957a4564b9d9746a6dd5c4f43f9d2cd878dadd8ffb53599a5e9668`
- `redesign/artifacts/mnn_age_threshold_reconciliation_v1.csv`: `355cf65ef63cd86f2e11f8a570089f6f202eb3ea4b9ff6e73abcaf8eb759d39b`
- `redesign/artifacts/mnn_age_threshold_reconciliation_v1_followup - mnn_age_threshold_reconciliation_v1_followup.csv`: `6b27521f8496275b163bf0fd9cdf2a6554037d4c3982b71a72a44f1b54ea7879`
- `redesign/artifacts/mnn_age_threshold_reconciliation_v1_followup.csv`: `c47394405d6d8d215ebe09ef48dc8075c04fe8f15671ed71c07e0be6ff600679`
- `redesign/artifacts/mnn_age_threshold_reconciliation_v1_summary.md`: `f1ca4970036f83ff52456c84a221edaef1da48842765d573d6c46b9539a84a01`
- `redesign/artifacts/mnn_non_drug_override_policy_v1_reviewed.csv`: `2a30637e73d6ddf2d5ff8096ac57f8d2ae06c692b208135dcd5c676c0b900a12`
- `redesign/m4_age_segment_contract_v1.md`: `ba0927931f8bf732ab293e528d3456e9429b44374f25374483bd3495402eea40`
- `redesign/m4_age_threshold_mapping_v1.md`: `1149d776b98751df386989042178655cf2b0ddd6cca020ff6705ad84f5e3f9bb`
- `redesign/m4_age_threshold_reconciliation_reviewed_contract_v1.md`: `75709e48e06b53ecc2ba3c4ff07546045511381b49ca106c4ea0a654e9681ee1`

## 2. Manual follow-up threshold distribution

| value | n |
|---|---|
| `0` | 5 |
| `1` | 0 |
| `2` | 0 |
| `3` | 0 |
| `4` | 0 |
| `5` | 0 |
| `6` | 1 |
| `7` | 0 |
| `8` | 0 |
| `9` | 0 |
| `10` | 1 |
| `11` | 0 |
| `12` | 0 |
| `13` | 0 |
| `14` | 0 |
| `15` | 0 |
| `16` | 0 |
| `17` | 0 |
| `18` | 0 |
| `unknown` | 0 |

Reviewed min-years distribution (all 40):

| value | n |
|---|---|
| `0` | 5 |
| `1` | 1 |
| `2` | 1 |
| `3` | 3 |
| `4` | 0 |
| `5` | 0 |
| `6` | 3 |
| `7` | 0 |
| `8` | 0 |
| `9` | 0 |
| `10` | 1 |
| `11` | 0 |
| `12` | 8 |
| `13` | 0 |
| `14` | 0 |
| `15` | 1 |
| `16` | 1 |
| `17` | 0 |
| `18` | 16 |
| `unknown` | 0 |

## 3. Reviewed segment distribution

| value | n |
|---|---|
| `дети` | 0 |
| `взрослые` | 16 |
| `универсальный` | 24 |
| `unknown` | 0 |
| `conflict` | 0 |
| `not_applicable` | 0 |

## 4. Main decision table

| value | n |
|---|---|
| `reviewed_adult_only` | 16 |
| `reviewed_child_or_adolescent_plus_adult` | 24 |
| `reviewed_children_only` | 0 |
| `reviewed_unknown` | 0 |
| `manual_segment_normalized_by_contract` | 0 |
| `manual_input_invalid` | 0 |
| `manual_input_conflict` | 0 |

## 5. Explicit analysis

- adult-only 18+: **16**
- 12–16+ normalized to universal: **10**
- child+adult 0–6+ universal: **13**
- min=10 + children_and_adults → universal: **1**
- children-only: **0**
- unknown thresholds: **0**
- remaining manual exceptions: **0** ids=`[]`

## 6. Contrast to original labels

- original `should_be_adults`: **26**
- stayed adults: **16** ids=`['45', '54', '88', '486', '884', '1765', '3556', '4593', '4922', '5267', '7816', '7858', '15150', '18125', '20122', '24095']`
- normalized to universal: **10** ids=`['72', '1668', '3065', '9301', '9511', '11272', '16485', '16623', '19198', '24750']`
- original `should_be_universal`: **14**
- got explicit threshold: **14** ids=`['844', '2621', '4481', '4487', '5270', '9941', '10046', '10536', '11142', '20614', '21010', '21019', '24255', '26115']`
- remain provisional unknown / exception: **0** ids=`[]`

## 7. Examples

### Adult-only

- `45` min=`18` segment=`взрослые` decision=`reviewed_adult_only` label=`should_be_adults` — Взрослый с 18 лет — АКВИОН КОЖА ВОЛОСЫ НОГТИ таб. N60 ВТФ ООО | ВТФ ООО | ВТФ ООО | N60
- `54` min=`18` segment=`взрослые` decision=`reviewed_adult_only` label=`should_be_adults` — Взрослый с 18 лет — ГЕПАРИН 5000ЕД/мл 5мл N5 р-р для в/в и п/к введения Армавирская биологическая ф…
- `88` min=`18` segment=`взрослые` decision=`reviewed_adult_only` label=`should_be_adults` — Взрослый с 18 лет — ГЕСПЕРИДИН+ДИОСМИН 100мг+900мг N30 таб. покрытые пленочной оболочкой Алиум АО |…

### 12–16 → universal

- `72` min=`12` segment=`универсальный` decision=`reviewed_child_or_adolescent_plus_adult` label=`should_be_adults` — Взрослый с 12 лет — ФАРИНГАЛ таб. 650мг N10 Салута-М | Салута-М ООО | Салута-М ООО | N10
- `1668` min=`12` segment=`универсальный` decision=`reviewed_child_or_adolescent_plus_adult` label=`should_be_adults` — Взрослый с 12 лет — ЧАБРЕЦА ТРАВА Ф/П 1,5Г №20 ЗДОРОВЬЕ | Здоровье фирма ЗАО | Здоровье фирма ЗАО
- `3065` min=`16` segment=`универсальный` decision=`reviewed_child_or_adolescent_plus_adult` label=`should_be_adults` — Взрослый с 16 лет — ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО

### Child + adult

- `844` min=`0` segment=`универсальный` decision=`reviewed_child_or_adolescent_plus_adult` label=`should_be_universal` — Применение у детей с рождения и у взрослых. — ЭЛЬКАР Р-Р Д/ПРИЕМА ВНУТРЬ 300МГ/МЛ ФЛ. 25МЛ | ///ПИК-ФАРМА ЛЕК | ///ПИК-ФАРМА …
- `2621` min=`0` segment=`универсальный` decision=`reviewed_child_or_adolescent_plus_adult` label=`should_be_universal` — Применение у детей с рождения и у взрослых. — ФУРАЦИЛИН ТАБЛ. Д/Р-РА Д/МЕСТН. И НАРУЖ. ПРИМ. 20МГ №20 ТАТХИМФАРМПРЕПАРАТЫ | Т…
- `4481` min=`3` segment=`универсальный` decision=`reviewed_child_or_adolescent_plus_adult` label=`should_be_universal` — Подтверждено применение у детей с 3 лет — ТРАНЕКСАМОВАЯ КИСЛОТА ТАБЛ. П/ПЛЕН/ОБ. 250МГ №30 МЭЗ | МОСКОВСКИЙ ЭНДОКРИННЫЙ З…

### Exceptions

_none_

## 8. Conclusion

Age threshold and age segment are separate. 12/14/15/16+ is not adults-only if child+adult scope is confirmed. This remains manual/audit-only and is not a DB/routing update.

## 9. v1 → v1.1 diff

- changed rows: **7** ids=`['844', '2621', '5270', '10046', '11142', '20614', '24255']`
- exceptions: **1** → **0**
- adults: **16** → **16**
- universal: **23** → **24**
- unknown: **1** → **0**

- `844` reviewed_age_reconciliation_status: `reviewed_manual_child_or_adolescent_plus_adult` → `resolved_from_explicit_threshold`
- `2621` reviewed_age_reconciliation_status: `reviewed_manual_child_or_adolescent_plus_adult` → `resolved_from_explicit_threshold`
- `5270` reviewed_age_reconciliation_status: `reviewed_manual_child_or_adolescent_plus_adult` → `resolved_from_explicit_threshold`
- `10046` reviewed_age_min_years: `unknown` → `10`, reviewed_age_population_scope: `unknown` → `children_and_adults`, reviewed_age_segment: `unknown` → `универсальный`, reviewed_age_decision: `manual_input_invalid` → `reviewed_child_or_adolescent_plus_adult`, reviewed_age_reconciliation_status: `manual_input_invalid` → `resolved_from_explicit_threshold`, reviewed_age_needs_manual_reconciliation: `true` → `false`, reviewed_age_source: `manual_input_rejected` → `manual_followup`
- `11142` reviewed_age_reconciliation_status: `reviewed_manual_child_or_adolescent_plus_adult` → `resolved_from_explicit_threshold`
- `20614` reviewed_age_reconciliation_status: `reviewed_manual_child_or_adolescent_plus_adult` → `resolved_from_explicit_threshold`
- `24255` reviewed_age_reconciliation_status: `reviewed_manual_child_or_adolescent_plus_adult` → `resolved_from_explicit_threshold`

```text
offline reviewed reconciliation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```
