# mnn_age_policy_replay_v2 summary

M4.1.1 Age policy replay v2. Patches false conflict on historical `not_applicable` without M2 approval. Splits drug vs M2 review queues. Proposal/display only. No new evidence.

## Preflight

- reviewed rows: **100**
- M2 approved: **13**
- product 45 in M2 approved: **False**
- historical not_applicable without M2: **2** ids=['11272', '45']

### Input SHA256 (unchanged)

- `m4_age_evidence_model_v1.json`: `df51b20e09948d49c018bd616ff474ead859519d0078c8a18a864030cec8a9e9`
- `m4_age_segment_contract_v1.md`: `ba0927931f8bf732ab293e528d3456e9429b44374f25374483bd3495402eea40`
- `mnn_age_policy_replay_v1.csv`: `7eaa8f9c320c45fb3999400b1a9fabab76b3fe2b3433ebe8896c93d7fb230530`
- `mnn_age_policy_replay_v1.py`: `a7cbbe9355a107b956c91de1c2225427697bd7ab2d854e2298070e2521f565c9`
- `mnn_age_policy_replay_v1_human_review.csv`: `35094c8630807f5b472ba6e81fc55a9b0e1a63b3d18747a2a175a09fd09cb436`
- `mnn_age_policy_replay_v1_summary.md`: `64c1b9d55506a619afbec2a7712ce4164987f3d3a2533312d15507f082e4ef84`
- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`: `ec167da556040e71e458c6bc74ba832b9f5cc60372d4e6e3de346f1373f93f5b`
- `mnn_identity_enrichment_pass_research_context.csv`: `7fe535fd4bf4dc9c22df995e61f3c542fd84be84275e5becd23a863d12a45146`
- `mnn_identity_enrichment_pass_results.csv`: `be3e8c74ec63c303261ae2aa3d7a79fbf545e2b7df60f4b9e5c485d276f94736`
- `mnn_non_drug_override_policy_v1_reviewed.csv`: `2a30637e73d6ddf2d5ff8096ac57f8d2ae06c692b208135dcd5c676c0b900a12`

## A. v1 → v2 diff

- total rows: **100** (unchanged count: True)
- historical not_applicable without M2 gate: **2** `['45', '11272']`
- changed rows: **2**
- v1 conflict → v2 unknown: **2** ids=`['45', '11272']`
- includes product 45: **True**
- M2 not_applicable retained: **13**

Changed rows:

- `45`: v1 `conflict`/`conflict_requires_evidence` → v2 `unknown`/`insufficient_existing_evidence`
- `11272`: v1 `conflict`/`conflict_requires_evidence` → v2 `unknown`/`insufficient_existing_evidence`

## B. v2 distributions

### Current Age

- `взрослые`: 43
- `универсальный`: 36
- `not_applicable`: 15
- `unknown`: 6

### Replay Age

- `unknown`: 65
- `conflict`: 22
- `not_applicable`: 13

### Decision

- `downgrade_unsupported_to_unknown`: 57
- `conflict_requires_evidence`: 22
- `m2_not_applicable_candidate`: 13
- `retain_safe_unknown`: 6
- `insufficient_existing_evidence`: 2

### Conflict status

- `no_conflict`: 59
- `baseline_vs_enrichment_conflict`: 22
- `not_applicable`: 13
- `unknown`: 6

### Queue action

- `send_to_age_contract_review`: 79
- `not_applicable_no_drug_age_review`: 13
- `require_product_specific_evidence`: 8

## C. Queue separation

- drug Age review: **87**
- M2 non-drug review: **13**
- drug Age pilot sample: **40**
- queue overlap: **empty**

### Pilot strata

- `conflict_requires_evidence`: 15 (target 15)
- `downgrade_unsupported_to_unknown`: 15 (target 15)
- `special_identity_product`: 5 (target 5)
- `unknown_or_insufficient`: 5 (target 5)

- product 45 in pilot: **True** stratum=`special_identity_product`
- shortfall after fill/redistribute: `{'conflict_requires_evidence': 0, 'downgrade_unsupported_to_unknown': 0, 'unknown_or_insufficient': 0, 'special_identity_product': 0}`
- redistributed: **0**

## D. Safety checks

- all M2 approved → not_applicable: **True**
- no non-M2 → not_applicable: **True**
- historical NA without M2 → unknown: **True**
- those rows not conflict: **True**
- product 45 unknown / insufficient_existing_evidence: **True**
- conflict only with two incompatible comparable non-null Age values
- no source winner declared
- no current Age accepted into DB
- no evidence added

## E. Examples

### Corrected 45

- `45` current=`not_applicable` → `unknown` (`insufficient_existing_evidence`); АКВИОН КОЖА ВОЛОСЫ НОГТИ таб. N60 ВТФ ООО | ВТФ ООО | ВТФ ООО | N60

### Conflict

- `54` current=`универсальный` → `conflict` (`conflict_requires_evidence`); ГЕПАРИН 5000ЕД/мл 5мл N5 р-р для в/в и п/к введения Армавирская биологическая фабрика фгуп
- `73` current=`универсальный` → `conflict` (`conflict_requires_evidence`); ГАСТРАСАН ЭКСПРЕСС 680мг+80мг N12 таб. жевательные Апельсин ЮжФарм ООО | ЮжФарм ООО | ЮжФа

### Downgrade adult/universal

- `8` current=`взрослые` → `unknown` (`downgrade_unsupported_to_unknown`); ХАЙЛЕФЛОКС 500мг N5 таб. покрытые пленочной оболочкой Хайгланс Лабораториз Пвт.Лтд. | Хайг
- `28` current=`взрослые` → `unknown` (`downgrade_unsupported_to_unknown`); МЕРИФАТИН МВ 750мг N60 таб. с пролонгированным высвобождением Фармасинтез-Тюмень ООО | Фар

### Retained unknown

- `3065` current=`unknown` → `unknown` (`retain_safe_unknown`); ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО
- `9941` current=`unknown` → `unknown` (`retain_safe_unknown`); ПАРОДОНТОЦИД ОПОЛАСКИВАТЕЛЬ ДЛЯ ПОЛОСТИ РТА 250МЛ | МОСКОВСКАЯ ФФ | МОСКОВСКАЯ ФФ

### M2 not_applicable

- `56` current=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); РИТОФЛЕКС МСМ таб. N60 Фармацевтическая Фабрика ООО | Фармацевтическая фабрика ООО | Фарма
- `75` current=`not_applicable` → `not_applicable` (`m2_not_applicable_candidate`); САМБУКУС БУЗИНА ИММУНИТЕТ таб. массой 700мг N30 Грин сайд ООО | Грин Сайд ООО | Грин Сайд 

## Constraints

- offline replay only; v1 artifacts not overwritten
- no web / LLM / DB / n8n
- no attr / snapshot / product_kind / prod / Sem changes
- no git commit/push
