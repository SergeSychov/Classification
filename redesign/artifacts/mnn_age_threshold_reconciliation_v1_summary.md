# mnn_age_threshold_reconciliation_v1 summary

M4.2 Age threshold reconciliation. Offline conversion of the labelled
Age pilot sample into structured fields where **age_min_years** and
**age_segment** are separate. 12/14/15/16+ is not adults-only.
Audit only. No DB / routing / attr write.

## 1. Input / review coverage

- labelled input: `mnn_age_policy_replay_v2_drug_age_pilot_sample - mnn_age_policy_replay_v2_drug_age_pilot_sample.csv`
- expected unique product_id: **40**
- actual rows: **40**; unique: **40**
- unique matches expected: **True**
- filled `label_age_pilot`: **40**
- filled `label_age_pilot_notes`: **40**
- notes with explicit numeric age threshold: **33**
- explicit thresholds extracted into `manual_age_min_years`: **33**

Label vocabulary:

| value | n |
|---|---|
| `should_be_adults` | 26 |
| `should_be_universal` | 14 |

### Input SHA256 (unchanged)

- `m4_age_evidence_model_v1.json`: `df51b20e09948d49c018bd616ff474ead859519d0078c8a18a864030cec8a9e9`
- `m4_age_segment_contract_v1.md`: `ba0927931f8bf732ab293e528d3456e9429b44374f25374483bd3495402eea40`
- `mnn_age_policy_replay_v2.csv`: `90b945d796fd3648862eede8c9d82b8475c9dded9f71db0c92ad3fcfdb1133d2`
- `mnn_age_policy_replay_v2_drug_age_pilot_sample - mnn_age_policy_replay_v2_drug_age_pilot_sample.csv`: `331efc4b59f2f2fa567759cb02432a41af9ab72794020d8a420c082fb32230c4`
- `mnn_age_policy_replay_v2_drug_age_pilot_sample.csv`: `ba887ded2499287874d694cc576930e117728f7ce943e7340cb0d63704f5fcf7`
- `mnn_age_policy_replay_v2_summary.md`: `d2a75bfb8bfa03385a631f92b3b731346cceaf89b1d5a229ce25bd7910f8476c`
- `mnn_non_drug_override_policy_v1_reviewed.csv`: `2a30637e73d6ddf2d5ff8096ac57f8d2ae06c692b208135dcd5c676c0b900a12`

## 2. Threshold distribution

| value | n |
|---|---|
| `0` | 0 |
| `1` | 1 |
| `2` | 1 |
| `3` | 3 |
| `6` | 2 |
| `12` | 8 |
| `14` | 0 |
| `15` | 1 |
| `16` | 1 |
| `18` | 16 |
| `unknown` | 7 |

## 3. Segment reconciliation distribution

| value | n |
|---|---|
| `дети` | 0 |
| `взрослые` | 16 |
| `универсальный` | 24 |
| `unknown` | 0 |
| `conflict` | 0 |
| `not_applicable` | 0 |

## 4. Reconciliation decisions

| value | n |
|---|---|
| `adult_only_confirmed` | 16 |
| `adolescent_plus_adult` | 10 |
| `children_plus_adult` | 7 |
| `children_only_confirmed` | 0 |
| `retain_unknown` | 0 |
| `retain_conflict` | 0 |
| `needs_threshold_confirmation` | 0 |
| `manual_label_insufficient` | 0 |
| `provisional_from_label_only` | 7 |

`provisional_from_label_only` is allowed by rule F in addition to the
§2 decision enum.

## 5. `should_be_adults` breakdown

- labelled `should_be_adults`: **26**
- truly adult-only (18+ / explicit adult-only): **16** ids=`['45', '54', '88', '486', '884', '1765', '3556', '4593', '4922', '5267', '7816', '7858', '15150', '18125', '20122', '24095']`
- actually adolescent_plus_adult (12–16): **10** ids=`['72', '1668', '3065', '9301', '9511', '11272', '16485', '16623', '19198', '24750']`
- unresolved because threshold was not written in note: **0** ids=`[]`

## 6. `should_be_universal` breakdown

- labelled `should_be_universal`: **14**
- explicit child threshold (0/1/2/3/6): **7** ids=`['4481', '4487', '9941', '10536', '21010', '21019', '26115']`
- label-only provisional: **7** ids=`['844', '2621', '5270', '10046', '11142', '20614', '24255']`
- needs_manual_threshold: **0** ids=`[]`

## 7. Product-specific examples

### Adult-only

- `45` min=`18` segment=`взрослые` label=`should_be_adults` — Взрослый с 18 лет — АКВИОН КОЖА ВОЛОСЫ НОГТИ таб. N60 ВТФ ООО | ВТФ ООО | ВТФ ООО | N60
- `54` min=`18` segment=`взрослые` label=`should_be_adults` — Взрослый с 18 лет — ГЕПАРИН 5000ЕД/мл 5мл N5 р-р для в/в и п/к введения Армавирская биологическая ф…
- `88` min=`18` segment=`взрослые` label=`should_be_adults` — Взрослый с 18 лет — ГЕСПЕРИДИН+ДИОСМИН 100мг+900мг N30 таб. покрытые пленочной оболочкой Алиум АО |…

### Adolescent + adult

- `72` min=`12` segment=`универсальный` label=`should_be_adults` — Взрослый с 12 лет — ФАРИНГАЛ таб. 650мг N10 Салута-М | Салута-М ООО | Салута-М ООО | N10
- `1668` min=`12` segment=`универсальный` label=`should_be_adults` — Взрослый с 12 лет — ЧАБРЕЦА ТРАВА Ф/П 1,5Г №20 ЗДОРОВЬЕ | Здоровье фирма ЗАО | Здоровье фирма ЗАО
- `3065` min=`16` segment=`универсальный` label=`should_be_adults` — Взрослый с 16 лет — ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО

### Child + adult

- `4481` min=`3` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей с 3 лет — ТРАНЕКСАМОВАЯ КИСЛОТА ТАБЛ. П/ПЛЕН/ОБ. 250МГ №30 МЭЗ | МОСКОВСКИЙ ЭНДОКРИННЫЙ З…
- `4487` min=`1` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей с 1 года — ТРАНЕКСАМОВАЯ КИСЛОТА Р-Р ДЛЯ В/В ВВЕД. 50МГ/МЛ АМП. 5МЛ №10 МЭЗ | МОСКОВСКИЙ Э…
- `9941` min=`6` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей с 6 лет — ПАРОДОНТОЦИД ОПОЛАСКИВАТЕЛЬ ДЛЯ ПОЛОСТИ РТА 250МЛ | МОСКОВСКАЯ ФФ | МОСКОВСКАЯ …

### Unresolved / follow-up threshold cases

- `844` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — ЭЛЬКАР Р-Р Д/ПРИЕМА ВНУТРЬ 300МГ/МЛ ФЛ. 25МЛ | ///ПИК-ФАРМА ЛЕК | ///ПИК-ФАРМА …
- `2621` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — ФУРАЦИЛИН ТАБЛ. Д/Р-РА Д/МЕСТН. И НАРУЖ. ПРИМ. 20МГ №20 ТАТХИМФАРМПРЕПАРАТЫ | Т…
- `5270` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — ТАМИФЛЮ КАПС. 75МГ №10 | ДЕЛФАРМ МИЛАНО С.Р.Л./Ф.ХОФФМАНН-ЛЯ РОШ ЛТД/СЕНЕКСИ С.…
- `10046` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — ПАПАВЕРИН ТАБЛ. 40МГ №10 ИРБИТСКИЙ ХФЗ | ИРБИТСКИЙ ХИМЗАВОД ОАО | ИРБИТСКИЙ ХИМ…
- `11142` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — НУРОФАСТ ТАБЛ. П/ПЛЕН/ОБ. 200МГ №20 | АЛИУМ АО | АЛИУМ АО
- `20614` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — ДЕКСАМЕТАЗОН-КРКА ТАБЛ. 4МГ №20 | КРКА Д.Д., НОВО МЕСТО АО/КРКА-РУС ООО | КРКА …
- `24255` min=`unknown` segment=`универсальный` label=`should_be_universal` — Подтверждено применение у детей и взрослых — БЕЛОДЕРМ КРЕМ Д/НАРУЖ. ПРИМ. 0,05% ТУБА 30Г | БЕЛУПО | БЕЛУПО

## 8. Follow-up manual threshold review

- count: **7**
- ids: `['844', '2621', '5270', '10046', '11142', '20614', '24255']`
- file: `redesign/artifacts/mnn_age_threshold_reconciliation_v1_followup.csv`

## 9. Children-only

- children-only rows: **0**

No conclusion about the prevalence of children-only products can be made from this sample if none are explicitly identified.

## Other

- replay vs reconciled segment changed: **40**
- M2 overlap in this drug pilot: **0** ids=`[]`
- `not_applicable` count: **0** (expected 0)

## Isolation

```text
offline reconciliation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```
