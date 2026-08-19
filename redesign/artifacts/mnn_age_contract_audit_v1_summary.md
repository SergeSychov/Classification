# mnn_age_contract_audit_v1 summary

M4.0 offline Age-segment audit. Design/analysis only.
No web / LLM / DB / n8n. Current Age values are **not** accepted.
`manual_expected_age_hint` is a parsed reviewer-note heuristic, not canonical human ground truth.

## Preflight

- expected Age error rows: **24**
- actual Age error rows: **24**
- unique product_id: **24**
- count mismatch vs 24: **False**
- all error rows present in review v2: **True**
- all error rows present in results: **True**
- error labels in {incorrect, partial, missing_but_should_exist}: **True**
- observed error label vocabulary: `{'incorrect': 24}`
- review v2 Age label coverage: `{'correct': 59, 'incorrect': 24, 'not_labeled': 17}`
- required columns present: **True**
- M2 overlap count: **0** ids=[]

### Input SHA256 (unchanged by this script)

- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`: `ec167da556040e71e458c6bc74ba832b9f5cc60372d4e6e3de346f1373f93f5b`
- `mnn_identity_enrichment_pass_research_context.csv`: `7fe535fd4bf4dc9c22df995e61f3c542fd84be84275e5becd23a863d12a45146`
- `mnn_identity_enrichment_pass_results.csv`: `be3e8c74ec63c303261ae2aa3d7a79fbf545e2b7df60f4b9e5c485d276f94736`
- `mnn_identity_enrichment_pass_review_age_errors_v1.csv`: `a3822ffd5adf07d99a11ae6974dcf258200122237cb0ac38a7821069dc7bb3d8`
- `mnn_identity_enrichment_pass_review_metrics_v1.md`: `14f42733965e740e2eddebc29a296625070121df70a7630be07c6e9809937ca0`
- `mnn_identity_enrichment_pass_searxng_raw.jsonl`: `99491b88b534ba76c2a8f675c33926af461e7ac5d5ae5ff2281565195ebdee1a`

Metrics v1 recorded a historical SHA for the labeled review CSV; this audit hashes the current required Sheets-export filename as-is and does not modify it.

## Age error bucket distribution (primary)

- `source_conflict_not_escalated`: 11
- `overbroad_adult_without_evidence`: 5
- `unknown_should_be_resolved`: 5
- `overbroad_universal_without_evidence`: 3

## Manual expected Age hint (heuristic)

- `взрослые`: 16
- `универсальный`: 8

## Hint strength

- `explicit_label_note`: 24

## Current Age value

- `универсальный`: 14
- `unknown`: 5
- `взрослые`: 5

## Current Age method

- `identity_enrichment`: 9
- `previous_enrichment`: 7
- `not_resolved`: 5
- `sem_baseline`: 3

## Current Age stage

- `mnn_identity_enrichment`: 9
- `previous_mnn_enrichment`: 7
- `none`: 5
- `sem1`: 3

## Current Age source

- `mnn_identity_enrichment_pass_results`: 9
- `mnn_catalog_resolution_wave500_v3`: 7
- `none`: 5
- `sem_wave500_mnn_v3_report`: 3

## pass_action

- `new_enrichment`: 10
- `reuse_existing_enrichment`: 7
- `skip_strong_input_mnn`: 6
- `skip_catalog`: 1

## identity_gate_status

- `unresolved_catalog`: 10
- `resolved_enrichment`: 7
- `resolved_input_explicit`: 6
- `resolved_catalog`: 1

## final_mnn_method

- `enrichment`: 15
- `input_explicit_mnn`: 6
- `catalog_consensus`: 1
- `input_plus_enrichment`: 1
- `unresolved_final`: 1

## Source / provenance questions

1. Method group with most Age errors: **`identity_enrichment`**.
2. `unknown_should_be_resolved`: **5**.
3. Overbroad universal (primary): **3**.
4. Overbroad adult (primary): **5**.
5. Conflict baseline vs enrichment (flag): **11**; primary `source_conflict_not_escalated`: **11**.
6. Generic MNN URL rows: **5**; weak-identity signal: **2**; wrong-form URL signal: **1**; union: **7**.
7. Assigned segment without product-specific Age evidence: **19/24** (normalization/policy issue). Missing-evidence primary buckets: **5**. No source winner is declared.

## Main conclusion

### Normalization policy failure

19/24 rows emitted взрослые or универсальный with evidence_grade=none (no explicit Age phrase in saved titles/excerpts). Primary overbroad buckets: 3 universal + 5 adult = 8/24. Sem defaults and enrichment 'универсальный' are not an Age evidence contract.

### Missing / weak evidence

5/24 primary unknown_should_be_resolved. 14/24 have no saved URLs (skip/reuse). 24/24 have no explicit Age phrase in saved titles/excerpts. Saved GRLS hits in this inventory are landings, not product records. This is an evidence-capture gap; it is not permission to retrieve yet.

### Conflict / identity

11/24 primary source_conflict_not_escalated; 11/24 carry baseline_vs_enrichment_conflict (typically Sem=взрослые vs enrichment=универсальный). 7/24 have generic-MNN and/or weak identity and/or wrong-form URL signals. No source winner is declared.

Absence of Age data is **not** `универсальный`. Absence of a child warning is **not** `универсальный`. Sem `взрослые` is **not** adult-only evidence. `unknown` is a valid safe outcome.

## M2 non-drug overlap

- checked against 13 M2 approved IDs
- overlap in Age error inventory: **0**
- non-M2 rows are **not** treated as BAS/Other automatically

## Canonical Age contract (proposed, not applied)

Final semantic values only: `дети` | `взрослые` | `универсальный` | `unknown` | `not_applicable` | `conflict`.
See `redesign/m4_age_segment_contract_v1.md`.

## Case table

| product_id | current | method | hint | bucket | conflict | decision |
|---|---|---|---|---|---|---|
| 54 | универсальный | `previous_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 88 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 486 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 1668 | универсальный | `previous_enrichment` | взрослые | `overbroad_universal_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 1765 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 2023 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 3027 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 3065 | unknown | `not_resolved` | универсальный | `unknown_should_be_resolved` | `unknown` | `require_product_specific_evidence` |
| 4133 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 4924 | универсальный | `identity_enrichment` | взрослые | `overbroad_universal_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 7275 | универсальный | `identity_enrichment` | взрослые | `overbroad_universal_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 9301 | универсальный | `previous_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 10536 | взрослые | `sem_baseline` | универсальный | `overbroad_adult_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 13616 | взрослые | `previous_enrichment` | универсальный | `overbroad_adult_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 15150 | unknown | `not_resolved` | взрослые | `unknown_should_be_resolved` | `unknown` | `require_product_specific_evidence` |
| 16623 | универсальный | `identity_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 18125 | универсальный | `previous_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 19198 | unknown | `not_resolved` | взрослые | `unknown_should_be_resolved` | `no_conflict` | `require_manual_review` |
| 20122 | взрослые | `sem_baseline` | универсальный | `overbroad_adult_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 20614 | unknown | `not_resolved` | универсальный | `unknown_should_be_resolved` | `unknown` | `require_product_specific_evidence` |
| 21010 | unknown | `not_resolved` | универсальный | `unknown_should_be_resolved` | `unknown` | `require_product_specific_evidence` |
| 24750 | взрослые | `previous_enrichment` | универсальный | `overbroad_adult_without_evidence` | `no_conflict` | `require_product_specific_evidence` |
| 25982 | универсальный | `previous_enrichment` | взрослые | `source_conflict_not_escalated` | `baseline_vs_enrichment_conflict` | `require_manual_review` |
| 26115 | взрослые | `sem_baseline` | универсальный | `overbroad_adult_without_evidence` | `no_conflict` | `require_product_specific_evidence` |

## Constraints

- offline/design only
- no web / SearXNG / HTTP / LLM / n8n
- no DB / attr_* / snapshot / product_kind / prod / Sem writes
- input artifacts unchanged
- no commit/push
- M3 RX/OTC remains `KEEP_RX_OTC_P2_SUPPORT_ONLY` / `DO_NOT_RUN_PHASE_A_YET`
