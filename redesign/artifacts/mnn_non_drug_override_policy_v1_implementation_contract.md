# Implementation contract — mnn_non_drug_override_policy_v1 (NOT APPLIED)

**Status:** draft contract only. Do **not** execute against PostgreSQL, Sem, Norm, or n8n.

## Purpose

Consume immutable freeze `mnn_non_drug_override_policy_v1_reviewed.csv` to optionally reduce future MNN human queue for 13 reviewed non-drug products.

## Inputs (read-only)

1. `redesign/artifacts/mnn_non_drug_override_policy_v1_reviewed.csv` (sha256 `403b93b6b984a964e78eb90edcfdf03e73ad473e3b1ba92016abf5c549270f46`)
2. Original policy `redesign/artifacts/mnn_non_drug_override_policy_v1.csv`
3. Labeled review `redesign/artifacts/mnn_non_drug_override_policy_v1_human_review - mnn_non_drug_override_policy_v1_human_review.csv` (sha256 `01452fa36d7b80de1cd5ae853400db924c6a96f2d55001edb2f82456aac70bc9`)

## Eligibility for future automation (when explicitly approved)

Apply **only** rows where:

```text
final_override_status = applied
AND final_proposed_product_kind IN (bas, other)
AND final_queue_action = remove_from_future_mnn_human_queue
```

Current freeze counts: bas=12, other=1, total=13.

## Proposed future effects (NOT done now)

1. **Queue filter (offline / allowlist):** exclude these 13 `product_id` from future MNN human-review exports.
2. **Optional soft signal (log-only):** emit `proposed_product_kind` into audit/log payload without writing `product_classification.product_kind`.
3. **MNN action:** keep MNN null / not applicable for applied rows (`keep_null_not_applicable` semantics).
4. **Never auto-write in v1 contract:**
   - `product_classification.product_kind` / `product_type`
   - `attr_mnn` / `attr_rx_otc` / `attr_age_segment`
   - snapshot upserts
   - live Sem routing hard gates

## Required gates before any apply job

- Explicit human approval ticket referencing this contract + reviewed sha256.
- Dry-run report listing 13 IDs.
- Rollback plan: restore previous queue membership; no destructive deletes.
- Keep `19198` and other `not_applied_*` rows in MNN/kind human paths.

## Out of scope / forbidden in this contract version

- New SearXNG / enrichment / LLM calls
- Creating classification_runs for kind override
- Silent overwrite of Sem0 `product_kind`
- Treating herbal ambiguity rows differently than freeze (already applied only if in reviewed applied set)

## Acceptance checks for a future apply PR

- Touches only queue-export / offline filter code paths OR append-only log fields
- Asserts reviewed file sha256 unchanged
- Unit test: 13 IDs excluded; 5 retained; 19198 retained
- Docs cite journal roadmap M2 → M2.1 reviewed freeze

## Confirmation

This file is documentation only. **Not applied.**
