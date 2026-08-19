# mnn_age_policy_replay_v1 data dictionary

Offline Age policy replay (M4.1). Proposal/display layer only.
Does **not** write `attr_age_segment` or change current Age in source artifacts.

## Inputs (read-only)

- `mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv`
- `mnn_identity_enrichment_pass_results.csv`
- `mnn_identity_enrichment_pass_research_context.csv`
- `mnn_age_contract_audit_v1.csv`
- `mnn_age_contract_audit_v1_summary.md`
- `m4_age_segment_contract_v1.md`
- `m4_age_evidence_model_v1.json`
- `mnn_non_drug_override_policy_v1_reviewed.csv`

## Outputs

- `mnn_age_policy_replay_v1.csv` — one row per reviewed product
- `mnn_age_policy_replay_v1_human_review.csv` — review queue; new labels empty
- `mnn_age_policy_replay_v1_summary.md`
- `mnn_age_policy_replay_v1_summary.json`
- `mnn_age_policy_replay_v1_data_dictionary.md`

## Replay fields

| field | meaning |
|---|---|
| `age_replay_current_*` | copy of pipeline Age provenance (unchanged) |
| `age_replay_value` | display proposal under Age contract v1 |
| `age_replay_decision` | why that display value was chosen |
| `age_replay_evidence_status` | existing saved-evidence class only |
| `age_replay_identity_status` | A/B/C/D/unknown/not_applicable from URL vs SKU text |
| `age_replay_conflict_status` | Sem vs enrichment / previous vs identity |
| `age_replay_requires_review` | `true`/`false` |
| `age_replay_queue_action` | review routing, not a DB action |
| `m2_non_drug_gate` | `approved` or `not_m2` |
| `manual_expected_age_hint` | heuristic from `label_notes`; not truth |

## Decision order

1. M2 approved BAS/Other → `not_applicable` (proposal-only)
2. Else retain current only if P1 + identity A/B + explicit Age phrase + no conflict
3. Else comparable-source conflict → `conflict`
4. Else unsupported `взрослые`/`универсальный` → `unknown`
5. Else current `unknown` → retain safe `unknown`
6. Else do not assign `дети` / non-M2 `not_applicable`

## Human-review membership

Include if `requires_review=true` OR value=`conflict` OR decision in
`downgrade_unsupported_to_unknown`, `m2_not_applicable_candidate`.
New label columns stay empty.
