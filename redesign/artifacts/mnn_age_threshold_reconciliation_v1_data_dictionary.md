# mnn_age_threshold_reconciliation_v1 data dictionary

M4.2 structured Age fields. Audit-only. Not a DB schema.

## Source

Manually labelled `mnn_age_policy_replay_v2_drug_age_pilot_sample*.csv`
with filled `label_age_pilot` / `label_age_pilot_notes`.
The unlabelled generated pilot is not used as the labelled input.

## Retained columns

All §5 identity / replay / pilot label columns from the labelled sample.

## New structured fields

| field | allowed | meaning |
|---|---|---|
| `manual_age_min_years` | 0,1,2,3,6,12,14,15,16,18,unknown,null | Lowest age from the reviewer note. Empty CSV cell = null. |
| `manual_age_min_years_source` | explicit_reviewer_note, label_only_no_threshold, not_available | Why the min is set. |
| `manual_age_max_years` | null, unknown | Never invented from absence of a max. This v1 leaves null. |
| `manual_age_population_scope` | children_only, adults_only, children_and_adults, unknown | Population coverage, separate from display segment. |
| `manual_age_segment_reconciled` | дети, взрослые, универсальный, unknown, conflict, not_applicable | Coarse routing/display label. |
| `manual_age_segment_decision` | adult_only_confirmed, adolescent_plus_adult, children_plus_adult, children_only_confirmed, retain_unknown, retain_conflict, needs_threshold_confirmation, manual_label_insufficient, provisional_from_label_only | Mapping rule used. |
| `manual_age_reconciliation_status` | resolved_from_explicit_threshold, resolved_from_explicit_adult_only, provisional_from_label_only, needs_manual_threshold, not_resolved | Resolution status. |
| `manual_age_reconciliation_reason` | text | Human-readable why. |
| `manual_age_threshold_confidence` | high, medium, low, unknown | Confidence in the min age, not in medical truth. |
| `manual_age_needs_threshold_review` | true, false | Follow-up queue flag. |
| `age_segment_changed_from_replay` | true, false | `age_replay_value` vs `manual_age_segment_reconciled`. Analysis only. |
| `age_threshold_extract_raw` | text | Matched phrase(s) from the note. |
| `age_reconciliation_warning` | text | Label override / ambiguity warnings. |

## Mandatory mapping

- Age threshold is separate from Age segment.
- 12/14/15/16+ is not adults-only by default.
- 18+ or explicit adult-only => взрослые.
- 0/1/2/3/6+ with adult use => универсальный.
- children-only needs explicit pediatric-only evidence.
- unknown is valid.
- This contract is audit-only; no DB/routing use.

## Follow-up CSV

Rows with `manual_age_needs_threshold_review=true` or ambiguous
extraction. Last four label columns are empty for the next reviewer.
