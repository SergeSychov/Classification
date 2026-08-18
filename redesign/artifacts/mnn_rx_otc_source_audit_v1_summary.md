# mnn_rx_otc_source_audit_v1 summary

Offline audit of saved RX/OTC evidence for Wave-500 human-review errors.
No new web/SearXNG/LLM calls; no DB writes; no corrected RX/OTC values.

## Preflight

- error_total: **11**
- unique product_id: **11**
- research_context_missing: 4
- raw_evidence_missing: 4

## Sufficiency

- existing evidence sufficient (GRLS/official + product-specific + A/B + explicit status): **0 / 11**
- best source already official with A/B specificity (status may still be missing): 1
- root-cause in no-authoritative / landing-only / no-evidence buckets: 8
- no official/GRLS URL at all: 6
- GRLS landing-only (not product card): 4
- only soft/generic/pharmacy best source: 5

## Best source-type distribution

- `rls_or_vidal_product_card`: 5
- `search_snippet_or_unknown`: 4
- `official_instruction_or_manufacturer`: 2

## All URLs source-type distribution

- `other`: 56
- `rls_or_vidal_product_card`: 17
- `pharmacy_product_card`: 14
- `regulatory_context_not_product_specific`: 4
- `official_instruction_or_manufacturer`: 2
- `generic_mnn_or_molecule_page`: 1

## Root-cause distribution

- `manual_label_only_no_evidence`: 4
- `authoritative_source_not_product_specific`: 2
- `near_brand_or_wrong_product_risk`: 2
- `no_authoritative_source_retrieved`: 2
- `source_conflict_not_escalated`: 1

## Evidence-gap distribution

- `multiple`: 11

## Representative examples

### product_id=3065
- text: ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО
- final=rx / hint=otc
- best_type=`search_snippet_or_unknown`
- best_url: —
- specificity=`unknown` identity=`unknown` explicit=`unclear`
- sufficient=`no` gap=`multiple`
- root_cause=`manual_label_only_no_evidence`
- notes: gap_flags=raw_evidence_missing+no_grls_or_official_source+source_not_product_specific+status_not_explicit+identity_weak; no_saved_evidence_urls; no_explicit_po_receptu_status_in_saved_titles_excerpts

### product_id=4924
- text: ТЕРМИКОН КРЕМ Д/НАРУЖ. ПРИМ. 1% ТУБА 15Г | ЛЕККО ЗАО | ЛЕККО ЗАО
- final=rx / hint=otc
- best_type=`official_instruction_or_manufacturer`
- best_url: https://termikon.ru/instrukcii/
- specificity=`brand_only` identity=`C` explicit=`no`
- sufficient=`no` gap=`multiple`
- root_cause=`near_brand_or_wrong_product_risk`
- notes: gap_flags=no_grls_or_official_source+source_not_product_specific+status_not_explicit+identity_weak+source_conflict; grls_landing_only_not_product_card; near_brand_or_wrong_form_evidence_present; no_explicit_po_receptu_status_in_saved_titles_excerpts

### product_id=19370
- text: ДЮСПАТАЛИН ТАБЛ. П/О 135МГ №15 ВЕРОФАРМ | ВЕРОФАРМ АО | ВЕРОФАРМ АО
- final=rx / hint=otc
- best_type=`official_instruction_or_manufacturer`
- best_url: https://duspatalin.ru/instruktsiya/135/
- specificity=`product_specific` identity=`B` explicit=`no`
- sufficient=`no` gap=`multiple`
- root_cause=`source_conflict_not_escalated`
- notes: gap_flags=status_not_explicit+source_conflict; near_brand_or_wrong_form_evidence_present; no_explicit_po_receptu_status_in_saved_titles_excerpts

### product_id=1053
- text: ЭКЗОРОЛФИНЛАК ЛАК Д/НОГТЕЙ 5% ФЛ. 2,5МЛ | ПАУЛЬ В. БЕЙФЕРС ГМБХ | ПАУЛЬ В. БЕЙФЕРС ГМБХ
- final=rx / hint=otc
- best_type=`rls_or_vidal_product_card`
- best_url: https://www.rlsnet.ru/drugs/ekzorolfinlak-79112
- specificity=`brand_form_specific` identity=`B` explicit=`no`
- sufficient=`no` gap=`multiple`
- root_cause=`authoritative_source_not_product_specific`
- notes: gap_flags=no_grls_or_official_source+status_not_explicit; grls_landing_only_not_product_card; no_explicit_po_receptu_status_in_saved_titles_excerpts

### product_id=7275
- text: САНОВАСК ТАБЛ. П/КИШ/РАСТ/ПЛЕН/ОБ. 50МГ №30 | ИРБИТСКИЙ ХИМЗАВОД ОАО | ИРБИТСКИЙ ХИМЗАВОД…
- final=rx / hint=otc
- best_type=`rls_or_vidal_product_card`
- best_url: https://www.rlsnet.ru/drugs/sanovask-75403
- specificity=`brand_only` identity=`C` explicit=`no`
- sufficient=`no` gap=`multiple`
- root_cause=`authoritative_source_not_product_specific`
- notes: gap_flags=no_grls_or_official_source+source_not_product_specific+status_not_explicit+identity_weak; grls_landing_only_not_product_card; no_explicit_po_receptu_status_in_saved_titles_excerpts

## Main gap for future RX/OTC retriever

Saved enrichment did **not** retrieve product-specific GRLS registration cards or official manufacturer instructions with an explicit “по рецепту/без рецепта” statement. GRLS hits are landings (`grls.rosminzdrav.ru/`); truth was taken from RLS/Vidal/aggregators/pharmacy cards (sometimes wrong form), or from skip/reuse paths with no evidence at all.

## Exact requirements for future RX/OTC pass (draft)

```text
Primary source:
GRLS product-specific registration/card or official current instruction.

Acceptance:
explicit status “по рецепту” / “без рецепта”;
identity A/B;
product-specific or brand+form-specific;
no comparable-source conflict.

Fallback:
RLS/Vidal product card or pharmacy card = soft/supporting only.

Reject:
generic MNN/molecule page;
search snippet;
regulatory order 100н as SKU source;
absence of explicit status;
identity C/D;
conflict.
```

Приказ Минздрава №100н использовать как нормативный контекст, но не как evidence RX/OTC конкретного товара.

## Constraints

- no web / SearXNG / LLM / n8n
- no DB writes / new runs
- no attr_* / snapshot / product_kind / workflow changes
- input artifacts unchanged
- no new RX/OTC values proposed
- no commit/push

## Case table (compact)

| product_id | final | hint | best_type | sufficient | root_cause |
|---|---|---|---|---|---|
| 1053 | rx | otc | `rls_or_vidal_product_card` | no | `authoritative_source_not_product_specific` |
| 2621 | rx | otc | `search_snippet_or_unknown` | no | `manual_label_only_no_evidence` |
| 3065 | rx | otc | `search_snippet_or_unknown` | no | `manual_label_only_no_evidence` |
| 4922 | rx | otc | `rls_or_vidal_product_card` | no | `near_brand_or_wrong_product_risk` |
| 4924 | rx | otc | `official_instruction_or_manufacturer` | no | `near_brand_or_wrong_product_risk` |
| 7275 | rx | otc | `rls_or_vidal_product_card` | no | `authoritative_source_not_product_specific` |
| 10046 | rx | otc | `rls_or_vidal_product_card` | no | `no_authoritative_source_retrieved` |
| 18377 | rx | otc | `search_snippet_or_unknown` | no | `manual_label_only_no_evidence` |
| 19198 | otc | — | `rls_or_vidal_product_card` | no | `no_authoritative_source_retrieved` |
| 19370 | rx | otc | `official_instruction_or_manufacturer` | no | `source_conflict_not_escalated` |
| 26115 | rx | otc | `search_snippet_or_unknown` | no | `manual_label_only_no_evidence` |
