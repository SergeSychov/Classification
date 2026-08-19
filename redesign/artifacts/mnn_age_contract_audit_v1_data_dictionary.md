# mnn_age_contract_audit_v1 data dictionary

Offline Age-segment audit of Wave-500 human-review Age errors (M4.0).
Does **not** correct Age values and does **not** write `attr_age_segment`.

`manual_expected_age_hint` is a **parsed reviewer-note heuristic**, not canonical
human ground truth. Do not load it into PostgreSQL as Age truth.

## Inputs (read-only)

- `mnn_identity_enrichment_pass_review_age_errors_v1.csv`
- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`
- `mnn_identity_enrichment_pass_results.csv`
- `mnn_identity_enrichment_pass_research_context.csv`
- `mnn_identity_enrichment_pass_review_metrics_v1.md`
- `mnn_identity_enrichment_pass_searxng_raw.jsonl` (Age-error product_id only; selected_evidence URLs/titles/excerpts; no full raw copy)

## Outputs

- `mnn_age_contract_audit_v1.csv` — one row per Age error
- `mnn_age_contract_audit_v1_human_review.csv` — same rows; `label_age_contract` / `label_age_contract_notes` empty
- `mnn_age_contract_audit_v1_summary.md`
- `mnn_age_contract_audit_v1_summary.json`
- `mnn_age_contract_audit_v1_data_dictionary.md`
- `scripts/mnn_age_contract_audit_v1.py`

Related design (not DB migrations):

- `redesign/m4_age_segment_contract_v1.md`
- `redesign/m4_age_evidence_model_v1.json`
- `redesign/m4_age_future_validation_plan.md`

## Main audit CSV fields

| field | meaning |
|---|---|
| `current_age*` | copy of pipeline `final_age*` (not accepted) |
| `sem_age` / `catalog_age` / `previous_enrichment_age` / `identity_enrichment_age` | provenance copies |
| `manual_expected_age_hint` | heuristic from `label_notes` via strict patterns |
| `manual_expected_age_hint_strength` | `explicit_label_note` / `ambiguous_label_note` / `not_available` |
| `age_error_bucket` | one primary taxonomy bucket |
| `age_source_type_guess` | best saved URL class (design enum) |
| `age_source_tier_guess` | P1 / P2 / P3 guess |
| `age_identity_grade_guess` | A/B/C/D/unknown from brand/form/dose vs SKU text |
| `age_evidence_grade_guess` | A/B/C/D/none; `none` if no explicit Age phrase in titles/excerpts |
| `age_conflict_status` | candidate disagreement, not a winner |
| `proposed_age_decision` | audit action; never accepts current Age |
| `proposed_age_value` | `null` for this inventory except M2 `not_applicable` |
| `proposed_age_acceptance_tier` | always `not_accepted_audit_only` here |
| `policy_version` | `age_contract_v1` |

## Hint patterns (strict)

- `универсальн` → `универсальный`
- `взросл` → `взрослые`
- `детск` → `дети`
- `unknown` / `неизвест` → `unknown`
- one class → `explicit_label_note`
- contradictory markers → empty hint + `ambiguous_label_note`
- no marker → empty hint + `not_available`

## Primary bucket policy

One bucket per row. Overlap flags (generic MNN URL, Latin MNN, wrong-form URL)
are counted in the summary even when not primary.

Conflict between Sem baseline and enrichment is primary when both values exist
and differ. Unknown current Age is primary `unknown_should_be_resolved` when a
hint exists. Overbroad buckets apply when a resolved segment was emitted without
product-specific Age evidence and without a comparable-source conflict.

## Hard rules

- Do not treat current Age as accepted.
- Do not invent medical facts.
- Do not use `not_applicable` for a drug with missing Age evidence.
- `unknown` is a valid safe outcome, not an error by itself.
