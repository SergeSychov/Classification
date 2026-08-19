# mnn_age_threshold_reconciliation_reviewed_v1 data dictionary

M4.2.1 reviewed Age mapping. Audit-only. Does not overwrite M4.2.

## Merge

- Follow-up rows with valid in-vocabulary manual labels: reviewed mapping after contract rules.
- Rows with no follow-up: preserved M4.2 deterministic result.
- Invalid/conflicting manual input: not applied; `unknown`/`conflict` + needs_manual_reconciliation.

## Reviewed fields

| field | allowed / meaning |
|---|---|
| `reviewed_age_min_years` | 0,1,2,3,6,12,14,15,16,18,unknown |
| `reviewed_age_min_years_source` | m4_2_explicit_reviewer_note, m4_2_label_only_no_threshold, manual_followup, rejected_invalid_manual, m4_2_not_available |
| `reviewed_age_population_scope` | children_only, adults_only, children_and_adults, unknown |
| `reviewed_age_segment` | дети, взрослые, универсальный, unknown, conflict, not_applicable |
| `reviewed_age_decision` | reviewed_adult_only, reviewed_child_or_adolescent_plus_adult, reviewed_children_only, reviewed_unknown, manual_segment_normalized_by_contract, manual_input_invalid, manual_input_conflict |
| `reviewed_age_reconciliation_status` | reviewed_manual_*, preserved_m4_2_deterministic, manual_input_invalid, manual_input_conflict, manual_segment_normalized_by_contract |
| `reviewed_age_needs_manual_reconciliation` | true, false |
| `reviewed_age_source` | m4_2_deterministic, manual_followup, manual_input_rejected |

Original `label_age_*_manual` values are always preserved, including invalid `10`.
Invalid mins are not copied into `reviewed_age_min_years`.

## Contract

- Age threshold and age segment are separate.
- 12/14/15/16+ is not adults-only if child+adult scope is confirmed.
- This remains manual/audit-only and is not a DB/routing update.
