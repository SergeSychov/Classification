# mnn_age_policy_replay_v1 summary

M4.1 offline Age policy replay on the Wave-500 human-review sample.
Proposal/display only. **No new evidence.** Current Age is not written to DB.
`manual_expected_age_hint` is a reviewer-note heuristic, not ground truth.

## Preflight

- reviewed row count: **100** (expected 100)
- unique product_id: **100**
- duplicate product_id: **0**
- required provenance columns: **True**
- M2 approved BAS/Other count: **13**
- M2 approved IDs in review sample: **13**
- no new evidence: **true**

### Input SHA256 (unchanged by this script)

- `m4_age_evidence_model_v1.json`: `df51b20e09948d49c018bd616ff474ead859519d0078c8a18a864030cec8a9e9`
- `m4_age_segment_contract_v1.md`: `ba0927931f8bf732ab293e528d3456e9429b44374f25374483bd3495402eea40`
- `mnn_age_contract_audit_v1.csv`: `473630f6646bd2e0597fa047c14069c2e16760ec1e8369281e7b73daf202b080`
- `mnn_age_contract_audit_v1_summary.md`: `dd81653af04f69551621eb7cf19e2c08b690a124d31f9892864643f365487f5a`
- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`: `ec167da556040e71e458c6bc74ba832b9f5cc60372d4e6e3de346f1373f93f5b`
- `mnn_identity_enrichment_pass_research_context.csv`: `7fe535fd4bf4dc9c22df995e61f3c542fd84be84275e5becd23a863d12a45146`
- `mnn_identity_enrichment_pass_results.csv`: `be3e8c74ec63c303261ae2aa3d7a79fbf545e2b7df60f4b9e5c485d276f94736`
- `mnn_non_drug_override_policy_v1_reviewed.csv`: `2a30637e73d6ddf2d5ff8096ac57f8d2ae06c692b208135dcd5c676c0b900a12`

## Current vs replay Age

### Current Age

- `взрослые`: 43
- `универсальный`: 36
- `not_applicable`: 15
- `unknown`: 6

### Replay Age

- `unknown`: 63
- `conflict`: 24
- `not_applicable`: 13

### Replay decision

- `downgrade_unsupported_to_unknown`: 57
- `conflict_requires_evidence`: 24
- `m2_not_applicable_candidate`: 13
- `retain_safe_unknown`: 6

### Conflict status

- `no_conflict`: 59
- `baseline_vs_enrichment_conflict`: 23
- `not_applicable`: 13
- `unknown`: 4
- `multiple_source_conflict`: 1

### Queue action

- `send_to_age_contract_review`: 81
- `not_applicable_no_drug_age_review`: 13
- `require_product_specific_evidence`: 6

### Evidence status

- `no_saved_evidence`: 39
- `conflict`: 24
- `product_specific_but_no_explicit_age`: 23
- `not_applicable`: 13
- `product_specific_explicit`: 1

## Safety changes

- adults → unknown: **43**
- universal → unknown: **14**
- current values → conflict: **24**
- current unknown retained: **6**
- M2 → not_applicable candidate: **13**
- retained_as_audit_only: **0**

## Per-method outcomes (no hidden source winner)

| method | current rows | downgraded → unknown | conflict display | retained audit-only |
|---|---:|---:|---:|---:|
| `identity_enrichment` | 37 | 22 | 15 | 0 |
| `previous_enrichment` | 26 | 19 | 7 | 0 |
| `sem_baseline` | 16 | 16 | 0 | 0 |

Identity/previous/Sem outputs are not treated as Age winners. Conflict stays `conflict`. Unsupported adults/universal become `unknown`.

## Human-review queue

- rows: **100**

Filter is not “all reviewed rows blindly”: include iff `requires_review=true` OR value=`conflict` OR decision is `downgrade_unsupported_to_unknown` / `m2_not_applicable_candidate`. This sample has **0** `retain_as_audit_only`, so the filter currently matches every reviewed row.

### Reason / decision distribution

- `downgrade_unsupported_to_unknown`: 57
- `conflict_requires_evidence`: 24
- `m2_not_applicable_candidate`: 13
- `retain_safe_unknown`: 6

### Examples

#### Downgrade adults/universal → unknown

- `8` current=`взрослые` method=`sem_baseline` → `unknown` (`downgrade_unsupported_to_unknown`); ХАЙЛЕФЛОКС 500мг N5 таб. покрытые пленочной оболочкой Хайгланс Лабораториз Пвт.Лтд. | Хайг
- `28` current=`взрослые` method=`sem_baseline` → `unknown` (`downgrade_unsupported_to_unknown`); МЕРИФАТИН МВ 750мг N60 таб. с пролонгированным высвобождением Фармасинтез-Тюмень ООО | Фар
- `34` current=`взрослые` method=`identity_enrichment` → `unknown` (`downgrade_unsupported_to_unknown`); МЕЛАДАПТ 3мг N10 таб. покрытые пленочной оболочкой Озон ООО | Озон ООО | Озон ООО | N10
- `68` current=`взрослые` method=`sem_baseline` → `unknown` (`downgrade_unsupported_to_unknown`); ЭПЛЕРЕНОН-ТЕВА 25мг N30 таб. покрытые пленочной оболочкой Тева фармасьютикал воркс прайвэт
- `70` current=`взрослые` method=`sem_baseline` → `unknown` (`downgrade_unsupported_to_unknown`); РОЗУВАСТАТИН-ТЕВА 20мг N90 таб. покрытые пленочной оболочкой Р-Фарм Новосёлки | Р-Фарм нов

#### Conflict

- `45` current=`not_applicable` method=`not_applicable` → `conflict` (`conflict_requires_evidence`); АКВИОН КОЖА ВОЛОСЫ НОГТИ таб. N60 ВТФ ООО | ВТФ ООО | ВТФ ООО | N60
- `54` current=`универсальный` method=`previous_enrichment` → `conflict` (`conflict_requires_evidence`); ГЕПАРИН 5000ЕД/мл 5мл N5 р-р для в/в и п/к введения Армавирская биологическая фабрика фгуп
- `73` current=`универсальный` method=`identity_enrichment` → `conflict` (`conflict_requires_evidence`); ГАСТРАСАН ЭКСПРЕСС 680мг+80мг N12 таб. жевательные Апельсин ЮжФарм ООО | ЮжФарм ООО | ЮжФа
- `88` current=`универсальный` method=`identity_enrichment` → `conflict` (`conflict_requires_evidence`); ГЕСПЕРИДИН+ДИОСМИН 100мг+900мг N30 таб. покрытые пленочной оболочкой Алиум АО | Алиум АО |
- `486` current=`универсальный` method=`identity_enrichment` → `conflict` (`conflict_requires_evidence`); ЭСЦИТАЛОПРАМ КАНОН ТАБЛ. П/ПЛЕН/ОБ. 20МГ №28 | КАНОНФАРМА ПРОДАКШН ЗАО | КАНОНФАРМА ПРОДАК

#### M2 not_applicable

- `56` current=`not_applicable` method=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); РИТОФЛЕКС МСМ таб. N60 Фармацевтическая Фабрика ООО | Фармацевтическая фабрика ООО | Фарма
- `75` current=`not_applicable` method=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); САМБУКУС БУЗИНА ИММУНИТЕТ таб. массой 700мг N30 Грин сайд ООО | Грин Сайд ООО | Грин Сайд 
- `249` current=`not_applicable` method=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); ОСТЕОМЕД таб. N60 Парафарм | Парафарм ООО | Парафарм ООО | N60
- `3763` current=`not_applicable` method=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); ФАРМГРУПП НАСТОЙКА 5 ТРАВ УСПОКОИТЕЛЬНАЯ ФЛ. 250МЛ | ФАРМГРУПП ООО | ФАРМГРУПП ООО
- `5322` current=`not_applicable` method=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); ТАВОЛГА ВЯЗОЛИСТНАЯ (ЛАБАЗНИК) ТРАВА Ф/П 1,5Г №20 ХЕРБЕС | ХЕРБЕС ООО | ХЕРБЕС ООО

#### Current unknown retained

- `3065` current=`unknown` method=`not_resolved` → `unknown` (`retain_safe_unknown`); ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО
- `9941` current=`unknown` method=`not_resolved` → `unknown` (`retain_safe_unknown`); ПАРОДОНТОЦИД ОПОЛАСКИВАТЕЛЬ ДЛЯ ПОЛОСТИ РТА 250МЛ | МОСКОВСКАЯ ФФ | МОСКОВСКАЯ ФФ
- `15150` current=`unknown` method=`not_resolved` → `unknown` (`retain_safe_unknown`); ЛИДОКАИН БУФУС Р-Р Д/ИН. 100МГ/МЛ АМП. 2МЛ №10 ОБНОВЛЕНИЕ | ОБНОВЛЕНИЕ ПФК АО | ОБНОВЛЕНИЕ
- `19198` current=`unknown` method=`not_resolved` → `unknown` (`retain_safe_unknown`); ЗВЕРОБОЯ ТРАВА 50Г ФИТОФАРМ | ФИТОФАРМ ООО | ФИТОФАРМ ООО
- `20614` current=`unknown` method=`not_resolved` → `unknown` (`retain_safe_unknown`); ДЕКСАМЕТАЗОН-КРКА ТАБЛ. 4МГ №20 | КРКА Д.Д., НОВО МЕСТО АО/КРКА-РУС ООО | КРКА Д.Д., НОВО 

## Limitations

- Replay uses **no new evidence**.
- `unknown` does not prove adult / child / universal.
- Human-note hints are not canonical truth.
- M2 `not_applicable` is proposal-only; product_kind is unchanged.
- Policy replay is not a DB write and does not merge `attr_age_segment`.
- This 100-row review sample is not the full catalog population.
- `retain_as_audit_only` is not an acceptance into snapshot.

## Explicit non-actions

- no DB / classification_runs / snapshot / attr_* / product_kind
- no n8n workflow create/edit/execute
- no web / SearXNG / HTTP / LLM
- no git commit/push
- M4.0 contract and source review v2 unchanged
