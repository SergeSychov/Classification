# M3.1 — future run / logging / artifact data model

**Status:** DESIGN ONLY. No SQL migrations, no `classification_runs`, no INSERT/UPDATE/DELETE, no snapshot writes.

Companion: [`m3_1_rx_otc_retriever_design.md`](m3_1_rx_otc_retriever_design.md), [`m3_1_rx_otc_retriever_contract.json`](m3_1_rx_otc_retriever_contract.json).

---

## 1. Proposed run identity

```text
run_type: stage2_rx_otc_retrieval_v1
workflow_name: rx-otc-product-retrieval-v1
stage: rx_otc_retrieval
workflow_version: rx_otc_retrieval_dev_v1
```

n8n workflow display name (future): `rx-otc-product-retrieval-dev`.

All stages of one retrieval use **one `run_id`**. Query attempts, layer fallbacks, and the final decision share that id.

### M3.2

- **M3.2a/b:** do not create `classification_runs`. Use an ephemeral `run_id` in the webhook/item (manual integer or UUID stored only in artifacts).
- **After one-item smoke + explicit approval:** optional INSERT into existing `classification_runs` with `run_type=stage2_rx_otc_retrieval_v1`. Still **no** `product_classification` snapshot update.

Do not invent log events with `run_id=null`.

---

## 2. Artifact layer (M3.2 primary store)

Required future outputs (not created in M3.1):

| Path | Role |
|------|------|
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_results.csv` | One row per product: identity, outcome, selected evidence pointers |
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_research_context.csv` | Curated queries + top URLs + excerpts |
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_human_review_errors.csv` | Phase A (11) review sheet |
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_blind_review.csv` | Phase B (30) review sheet |
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_summary.md` | Counts / isolation confirmation |
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl` | Append-only raw attempts |

### JSONL raw record (append-only)

One line per HTTP/search attempt. Full upstream payload may live here. **Not** copied into PostgreSQL.

```json
{
  "run_id": 0,
  "product_id": 0,
  "attempt_no": 1,
  "query_kind": "grls_primary",
  "query": "...",
  "source_url": "...",
  "source_type": "...",
  "retrieved_at": "2026-08-18T00:00:00Z",
  "http_status": 200,
  "raw_artifact_path": "redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl",
  "latency_ms": 0,
  "raw_response": {}
}
```

Strip keys matching `api_key|authorization|password|secret|token|credential` before append (same spirit as `scripts/lib/mnn_search_evidence.py`).

---

## 3. Future `product_classification_log` payload (proposal)

Reuse existing table. No new columns required for v1 if `input_payload` / `output_payload` remain JSONB.

**Do not** store full raw search bodies in JSONB.

### Idempotency / resume

```text
(run_id, product_id, stage, attempt_no)
```

| Event class | `stage` (proposal) | `attempt_no` | Dedup rule |
|-------------|--------------------|--------------|------------|
| Query attempt | `rx_otc_retrieval` | 1..N | Unique `(run_id, product_id, stage, attempt_no)` |
| Final decision | `rx_otc_retrieval` | `0` or omit; distinguish via `output_payload.event_kind=final_decision` | At most one final decision per `(run_id, product_id, stage)` |

Resume:

- Re-run incomplete **retryable** attempts with the **same** `run_id`.
- Never insert an identical log event (`run_id, product_id, stage, attempt_no, event_kind`).
- Distinguish query attempts from the final decision in `output_payload.event_kind`: `query_attempt` | `final_decision`.
- Keep the same `run_id` across Q1→Q2→Q3.

Suggested pre-insert check (future, not executed now):

```sql
-- design only
SELECT 1
FROM product_classification_log
WHERE run_id = :run_id
  AND product_id = :product_id
  AND stage = 'rx_otc_retrieval'
  AND (output_payload->>'event_kind') = :event_kind
  AND COALESCE((output_payload->>'attempt_no')::int, 0) = :attempt_no
LIMIT 1;
```

Existing uniqueness is **not** `(run_id, product_id, stage, attempt_no)` today. Until an explicit unique index is approved, enforce idempotency in the writer (same pattern as identity enrichment `log_exists`). **No migration in M3.1.**

### `input_payload`

```json
{
  "event_kind": "final_decision",
  "product_identity": {
    "product_id": 0,
    "normalized_text_full": "...",
    "rx_otc_identity_text": "...",
    "rx_otc_identity_query": "...",
    "rx_otc_identity_fingerprint": "...",
    "rx_otc_brand_norm": "...",
    "rx_otc_form_norm": "...",
    "rx_otc_strength_norm": "...",
    "rx_otc_pack_norm": "...",
    "rx_otc_manufacturer_norm": "...",
    "mnn_if_known": null,
    "country_or_market_if_known": "RU"
  },
  "input_source_values": {
    "sem_rx_otc": null,
    "catalog_rx_otc": null,
    "previous_enrichment_rx_otc": null,
    "identity_enrichment_rx_otc": null
  },
  "policy": {
    "workflow_version": "rx_otc_retrieval_dev_v1",
    "source_hierarchy_version": "rx_otc_source_v1",
    "identity_policy_version": "rx_otc_identity_v1"
  },
  "query_plan": [
    {
      "attempt_no": 1,
      "query_kind": "grls_primary",
      "query": "...",
      "reason": "brand+form+strength GRLS primary"
    }
  ]
}
```

### `output_payload`

```json
{
  "event_kind": "final_decision",
  "attempt_no": 0,
  "query_attempts": [
    {
      "attempt_no": 1,
      "query_kind": "grls_primary",
      "query": "...",
      "http_status": 200,
      "error_code": null,
      "latency_ms": 0,
      "raw_artifact_path": "redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl"
    }
  ],
  "raw_artifact_pointers": ["redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl"],
  "selected_evidence": [
    {
      "source_url": "...",
      "source_type": "grls_official_product_record",
      "source_tier": "P1",
      "identity_grade": "A",
      "explicit_status_text": "…max 500 chars…",
      "status_pattern": "bez_recepta",
      "candidate_rx_otc_value": "otc",
      "validation_passed": true
    }
  ],
  "validated_candidates": [],
  "decision": {
    "outcome": "accepted|supported_only|unresolved|conflict|rejected|error|not_applicable",
    "candidate_rx_otc_value": "rx|otc|null",
    "final_rx_otc_value": "rx|otc|null",
    "evidence_tier": "tier_1_product_specific|tier_2_supported_soft_signal|none",
    "conflict_status": "no_conflict|conflict|unknown",
    "validation_passed": false,
    "reason": "...",
    "search_query_count": 0,
    "logical_search_query_count": 0,
    "transport_retry_attempt_count": 0,
    "fetched_page_count": 0,
    "budget_exhausted": false
  },
  "retry_history": [],
  "sem_baseline_rx_otc": null,
  "silent_overwrite": false
}
```

Limits:

```text
- no full raw response in PostgreSQL;
- max 10 selected evidence records;
- explicit status excerpt max 500 chars;
- raw source content → append-only artifact only.
```

Other log columns (existing): `actor_type=system`, `actor_name=rx-otc-product-retrieval-dev`, `workflow_version`, `prompt_version` unused or equal to workflow_version, `decision_status` mapped from outcome (`accepted`→ not `classified`; use `pending_fallback` or a free-text value already allowed — **no CHECK on stage/decision_status** per schema dump). Until a dedicated status is approved, store the canonical outcome in JSONB and set `decision_status=needs_human_review` for conflict/unresolved and `status=ok` for completed audit rows. This is a proposal only.

---

## 4. M3.2 snapshot policy

```text
No product_classification snapshot update.
No attr_rx_otc update.
No semantic_attrs update.
```

The retriever must not upsert `product_classification`. Sem baseline RX/OTC remains the live semantic value.

---

## 5. Future-only proposed snapshot fields (NOT a migration)

Do not add columns now. If a later approved proposed-layer exists, candidate names:

```text
proposed_rx_otc
proposed_rx_otc_source
proposed_rx_otc_confidence
proposed_rx_otc_evidence_tier
proposed_rx_otc_status
proposed_rx_otc_run_id
```

Semantics (future):

| Field | Values |
|-------|--------|
| `proposed_rx_otc` | `rx` \| `otc` \| null |
| `proposed_rx_otc_source` | `grls_official_product_record` \| `official_instruction_product_specific` \| … |
| `proposed_rx_otc_confidence` | `high` \| `medium` \| `low` |
| `proposed_rx_otc_evidence_tier` | `tier_1_product_specific` \| `tier_2_supported_soft_signal` |
| `proposed_rx_otc_status` | `proposed` \| `needs_review` \| `rejected` |
| `proposed_rx_otc_run_id` | FK to `classification_runs.id` |

**Never** silently copy these onto `attr_rx_otc`. P1 may become preferred only after controlled validation + human approval (M3.3+ / M3.4).

---

## 6. `classification_runs` metadata (future)

When a run row is allowed:

```json
{
  "isolation": {
    "snapshot_update": false,
    "attr_rx_otc_update": false,
    "prod_stage2_untouched": true,
    "hierarchy_dev_untouched": true
  },
  "m2_excluded_count": 0,
  "outcomes": {},
  "search_query_count": 0,
  "logical_search_query_count": 0,
  "transport_retry_attempt_count": 0,
  "fetched_page_count": 0,
  "budget_exhausted_count": 0,
  "raw_artifact_path": "redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl",
  "source_hierarchy_version": "rx_otc_source_v1"
}
```

Finish-run should not join `product_classification.latest_run_id` (that path is snapshot-coupled). Count from log/artifacts instead.

---

## 7. Results CSV columns (M3.2)

Proposed (stable, audit-only):

```text
product_id
normalized_text_full
rx_otc_identity_text
rx_otc_identity_query
rx_otc_identity_fingerprint
rx_otc_brand_norm
rx_otc_form_norm
rx_otc_strength_norm
rx_otc_pack_norm
rx_otc_manufacturer_norm
m2_gate
outcome
candidate_rx_otc_value
final_rx_otc_value
evidence_tier
identity_grade
source_type
source_tier
source_url
explicit_status_text
status_pattern
conflict_status
validation_passed
reject_reason
search_query_count
logical_search_query_count
transport_retry_attempt_count
fetched_page_count
budget_exhausted
retry_count
sem_rx_otc
previous_enrichment_rx_otc
identity_enrichment_rx_otc
expected_rx_otc_manual
expected_rx_otc_source
review_label_inconsistency
run_id
workflow_version
raw_artifact_path
```

`final_rx_otc_value` is set only for `outcome=accepted` (P1). P2 `supported_only` stores `candidate_rx_otc_value` and **must** leave `final_rx_otc_value` null. P2 never sets a final accepted RX/OTC value and cannot be used for hard routing, snapshot update, or attr merge.

Human-review CSVs add empty label columns: `label_rx_otc`, `label_identity_ok`, `label_source_ok`, `label_notes`, plus the three review fields above (empty for future human review; `19198` may pre-seed `review_label_inconsistency=true` only). Do not rewrite historic labels.

Controlled-batch summary must report `logical_search_query_count` (alias `search_query_count`), `transport_retry_attempt_count`, `fetched_page_count`, `budget_exhausted_count`. Logical search quota (`<= 8`) is separate from transport retries (`<= 2` per logical query) and from fetch quota (`fetched_page_count <= 4`).

---

## 8. What this file does not authorize

- SQL migrations
- new tables
- unique indexes
- `product_classification` columns
- live INSERT into `classification_runs` / `product_classification_log`
- merge into `attr_rx_otc`
