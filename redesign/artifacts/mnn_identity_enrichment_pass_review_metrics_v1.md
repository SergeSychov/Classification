# Review metrics v1 — identity enrichment pass (run 461)

Offline quality baseline from labeled human_review_v2. **No new evidence collected.**

## 1. Preflight / coverage

- input: `redesign/artifacts/mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`
- sha256: `2b8a1314d48180b0fe21703053ce2aa1564c05da275cc90478a7140d608816e1` (unchanged after analysis)
- rows: **100**; distinct product_id: **100**; duplicates: **0**
- blank labels: `{'label_mnn': 0, 'label_rx_otc': 17, 'label_age': 17, 'label_notes': 52}`
- observed vocabulary: `{'label_mnn': {'correct': 82, 'should_be_empty': 17, 'incorrect': 1}, 'label_rx_otc': {'correct': 72, 'incorrect': 11, 'not_labeled': 17}, 'label_age': {'correct': 59, 'incorrect': 24, 'not_labeled': 17}}`
- unmapped labels: `{}`

## 2. Headline metrics

### MNN
- all reviewed relevant: **99/100 = 99.0%**
  - correct outcomes = correct + should_be_empty
  - error outcomes = incorrect + partial + missing_but_should_exist
- breakdown: correct=82, should_be_empty=17, incorrect=1, partial=0, missing_but_should_exist=0
- excluded from denominator: 0
- correct null MNN for non-drug (`should_be_empty`): **17**
- optional drugish slice (label != should_be_empty; **not authoritative drug count**): 83 rows, accuracy 82/83 = 98.8%

### RX/OTC
- accuracy: **72/83 = 86.7%**
- label counts: `{'correct': 72, 'incorrect': 11, 'not_labeled': 17}`
- not_labeled: 17
- final_rx_otc=unknown: 0; conflict: 0
- wrong RX vs wrong OTC separately: **manual expected value not structured** (heuristic hints only in error inventory)

### Age
- accuracy: **59/83 = 71.1%**
- label counts: `{'correct': 59, 'incorrect': 24, 'not_labeled': 17}`
- not_labeled: 17
- final_age=unknown: 6; conflict: 0
- age-error note keyword groups (heuristic): `{'notes_mentions_universal': 8, 'notes_mentions_adult': 16}`

## 3. Accuracy by routing

### pass_action × MNN

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| new_enrichment | 55 | 55 | 54 | 1 | 98.2 |
| reuse_existing_enrichment | 25 | 25 | 25 | 0 | 100.0 |
| skip_strong_input_mnn | 16 | 16 | 16 | 0 | 100.0 |
| skip_catalog | 4 | 4 | 4 | 0 | 100.0 |

### pass_action × RX/OTC

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| new_enrichment | 55 | 38 | 31 | 7 | 81.6 |
| reuse_existing_enrichment | 25 | 25 | 23 | 2 | 92.0 |
| skip_strong_input_mnn | 16 | 16 | 15 | 1 | 93.8 |
| skip_catalog | 4 | 4 | 3 | 1 | 75.0 |

### pass_action × Age

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| new_enrichment | 55 | 38 | 28 | 10 | 73.7 |
| reuse_existing_enrichment | 25 | 25 | 18 | 7 | 72.0 |
| skip_strong_input_mnn | 16 | 16 | 10 | 6 | 62.5 |
| skip_catalog | 4 | 4 | 3 | 1 | 75.0 |

### identity_gate_status × MNN

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| unresolved_catalog | 55 | 55 | 54 | 1 | 98.2 |
| resolved_enrichment | 25 | 25 | 25 | 0 | 100.0 |
| resolved_input_explicit | 16 | 16 | 16 | 0 | 100.0 |
| resolved_catalog | 4 | 4 | 4 | 0 | 100.0 |

### final_mnn_method × MNN

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| enrichment | 55 | 55 | 55 | 0 | 100.0 |
| unresolved_final | 18 | 18 | 17 | 1 | 94.4 |
| input_explicit_mnn | 16 | 16 | 16 | 0 | 100.0 |
| input_plus_enrichment | 7 | 7 | 7 | 0 | 100.0 |
| catalog_consensus | 4 | 4 | 4 | 0 | 100.0 |

## 4. RX/OTC provenance quality

### final_rx_otc_method

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| identity_enrichment | 37 | 37 | 31 | 6 | 83.8 |
| previous_enrichment | 25 | 25 | 23 | 2 | 92.0 |
| sem_baseline | 23 | 21 | 18 | 3 | 85.7 |
| not_applicable | 15 | 0 | 0 | 0 | n/a |

### final_rx_otc_stage

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| mnn_identity_enrichment | 52 | 37 | 31 | 6 | 83.8 |
| previous_mnn_enrichment | 25 | 25 | 23 | 2 | 92.0 |
| sem1 | 23 | 21 | 18 | 3 | 85.7 |

### final_rx_otc_source

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| mnn_identity_enrichment_pass_results | 37 | 37 | 31 | 6 | 83.8 |
| mnn_catalog_resolution_wave500_v3 | 25 | 25 | 23 | 2 | 92.0 |
| sem_wave500_mnn_v3_report | 23 | 21 | 18 | 3 | 85.7 |
| mnn_identity_enrichment_pass_searxng_raw | 15 | 0 | 0 | 0 | n/a |

## 5. Age provenance quality

### final_age_method

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| identity_enrichment | 37 | 37 | 28 | 9 | 75.7 |
| previous_enrichment | 26 | 25 | 18 | 7 | 72.0 |
| sem_baseline | 16 | 16 | 13 | 3 | 81.2 |
| not_applicable | 15 | 0 | 0 | 0 | n/a |
| not_resolved | 6 | 5 | 0 | 5 | 0.0 |

### final_age_stage

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| mnn_identity_enrichment | 52 | 37 | 28 | 9 | 75.7 |
| previous_mnn_enrichment | 26 | 25 | 18 | 7 | 72.0 |
| sem1 | 16 | 16 | 13 | 3 | 81.2 |
| none | 6 | 5 | 0 | 5 | 0.0 |

### final_age_source

| group | total | labelled | correct | error | accuracy |
|---|---:|---:|---:|---:|---:|
| mnn_identity_enrichment_pass_results | 37 | 37 | 28 | 9 | 75.7 |
| mnn_catalog_resolution_wave500_v3 | 26 | 25 | 18 | 7 | 72.0 |
| sem_wave500_mnn_v3_report | 16 | 16 | 13 | 3 | 81.2 |
| mnn_identity_enrichment_pass_searxng_raw | 15 | 0 | 0 | 0 | n/a |
| none | 6 | 5 | 0 | 5 | 0.0 |

## 6. MNN error inventory summary

- MNN error rows: **1**
- buckets: `{'missing_mnn': 1}`
- artifact: `redesign/artifacts/mnn_identity_enrichment_pass_review_mnn_errors_v1.csv`

### Special case: Зверобоя трава / Фитофарм

- **product_id**: 19198
- **normalized_text**: ЗВЕРОБОЯ ТРАВА 50Г ФИТОФАРМ | ФИТОФАРМ ООО | ФИТОФАРМ ООО
- **final_candidate_mnn**:
- **final_mnn_method**: unresolved_final
- **pass_action**: new_enrichment
- **identity_gate_status**: unresolved_catalog
- **new_enrichment_status**: ok_partial
- **retry_count**: 2
- **research_summary**: status=ok_partial | Category=Drug | RX_OTC=OTC | Age=Универсальный | Зверобоя трава является лекарственным средством (ЛС) согласно данным Государственного реестра лекарственных средств (ГРЛС) и других источников. МНН (международное непатентованное название) в предоставленных результатах поиска не указано, поэтому оно не определено. Препарат…
- **label_mnn**: incorrect
- **label_notes**: Drug (Трава зверобоя), ОТС, Взрослый
- **why_it_appears_in_error_inventory**: included because label_mnn is in error set
- **in_mnn_error_inventory**: True

## 7. Non-drug / null-MNN audit

- rows: **18**
- signals: `{'label_should_be_empty_only': 2, 'bas_from_research_summary': 13, 'other_from_research_summary': 2, 'unresolved_no_mnn': 1}`
- artifact: `redesign/artifacts/mnn_identity_enrichment_pass_review_non_drug_null_mnn_v1.csv`

## 8. Text-quality diagnostics

- length min/median/p90/max: 37 / 82.0 / 124.1 / 214
- rows with any duplicate `|` segments: **100** / 100
- rows with duplicate manufacturer-like tail segments: **100** / 100
- rows where last two `|` segments are equal: **86** / 100
- rows with duplicate pack tokens (N## / №##): **14** / 100
- examples artifact: `redesign/artifacts/mnn_identity_enrichment_pass_review_text_quality_v1.csv`

Hypothesis check: Duplicate manufacturer/pack segments are widespread in this sample (100/100 manufacturer-like tail dups; 14/100 pack dups) and can inflate enrichment queries / review load. No cleanup applied in this task.

## 9. Limitations

- Review sample may not be random.
- Manual expected RX/Age values are not always structured; note parsing is heuristic.
- Results are **not** permission for prod merge.
- No new evidence was collected in this task.
- Drug counts are not inferred beyond reviewer `should_be_empty` labels.

## 10. Next inputs for Task 2 (BAS/Other override policy)

1. `redesign/artifacts/mnn_identity_enrichment_pass_review_non_drug_null_mnn_v1.csv`
2. `redesign/artifacts/mnn_identity_enrichment_pass_review_metrics_v1.md` (non-drug/null-MNN section + headline)

## Confirmation

- no LLM / SearXNG / webhook
- no DB writes
- prod / Sem / snapshot / attr_* untouched
- input review CSV untouched (`sha256` stable)
