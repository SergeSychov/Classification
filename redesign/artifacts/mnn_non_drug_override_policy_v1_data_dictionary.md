# Data dictionary — mnn_non_drug_override_policy_v1

All fields are **proposed / offline only**. They do not update snapshot or live Sem.

## Main policy CSV columns

- `product_id`
- `normalized_text`
- `pass_action`
- `identity_gate_status`
- `new_enrichment_status`
- `final_mnn_method`
- `final_candidate_mnn`
- `needs_human_review`
- `needs_human_review_any`
- `review_priority`
- `label_mnn`
- `label_notes`
- `research_summary`
- `evidence_urls`
- `research_context_available`
- `selected_evidence_count`
- `search_count`
- `observed_research_category`
- `observed_drug_conflict`
- `observed_non_drug_signal`
- `proposed_product_kind`
- `proposed_kind_decision`
- `proposed_kind_method`
- `proposed_kind_confidence`
- `proposed_kind_evidence_grade`
- `proposed_kind_identity_grade`
- `proposed_kind_auto_eligible`
- `proposed_kind_review_required`
- `proposed_queue_action`
- `proposed_mnn_action`
- `proposed_kind_reason`
- `policy_version`

## Enumerations

- `proposed_product_kind`: bas | other | (empty/null)
- `proposed_kind_decision`: propose_bas_override | propose_other_override | keep_current_no_override | insufficient_evidence | conflict_requires_review
- `proposed_kind_method`: identity_enrichment_existing_evidence | human_label_plus_existing_evidence | research_summary_only | none
- `proposed_kind_confidence`: high | medium | low | unknown
- `proposed_kind_evidence_grade` / `proposed_kind_identity_grade`: A | B | C | D | none/unknown
- `proposed_queue_action`: remove_from_future_mnn_human_queue | retain_in_human_queue | send_to_kind_review_queue | no_action
- `proposed_mnn_action`: keep_null_not_applicable | keep_null_unresolved | manual_mnn_review | no_action

## Human-review CSV

Includes auto-eligible and review-required rows. Empty labels:
- `label_kind_override`
- `label_kind_override_notes`

## Truncation

- `research_summary` ≤ 800 chars
- evidence URL list clipped; no raw SearXNG JSONL payloads
