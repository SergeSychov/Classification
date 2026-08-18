# M3.2 — controlled validation plan (design only)

**Status:** plan only. Do not run search, n8n, LLM, or DB writes in M3.1.  
**Workflow (future):** `rx-otc-product-retrieval-dev` (`workflow_version=rx_otc_retrieval_dev_v1`), created **inactive**.  
**Canon:** [`m3_1_rx_otc_retriever_design.md`](m3_1_rx_otc_retriever_design.md).

This plan does **not** treat RX/OTC as ready for routing.

---

## 0. Safety gates (mandatory)

```text
- all M3.2 results reviewed by human;
- no DB snapshot/attrs update;
- measure RX and OTC precision separately;
- source/identity/status evidence shown in review CSV;
- compare future retrieval against current Sem/enrichment values;
- unresolved is acceptable and preferable to unsupported status.
```

Additional:

- M2 applied BAS/Other **13** products excluded (`not_applicable`); never sent through drug RX/OTC retrieval.
- Prod `classification-stage2-dev` and `classification-stage2-hierarchy-dev` untouched.
- No `attr_rx_otc` / `semantic_attrs` / `product_kind` / `product_type` writes.
- One `run_id` per M3.2 batch across Q1–Q3.
- M3.2a skeleton first; **one-item** live test before the controlled batch.

---

## 1. Rollout phases

### M3.2a — inactive skeleton

- Create workflow **inactive**.
- Manual Trigger + dedicated Webhook only.
- Search/Fetch nodes **stubbed** (no HTTP, no SearXNG, no LLM).
- No PostgreSQL writes.
- Smoke: one synthetic item through Validate → Identity → M2 gate → stub fetch → audit result → webhook.
- Pass: isolation flags in response; empty candidates; no DB row.

### M3.2b — one-item live retrieval

- Requires **explicit approval**.
- Connect retrieval/search for **one** manually chosen product.
- Recommended first live SKU (from Phase A, skip/reuse / no saved evidence): `3065` Флуконазол-OBL капс. 150 мг №4 — or another Phase A id if 3065 is blocked ops-wise.
- Still no snapshot / `attr_*`.
- Pass: raw JSONL line(s) written; identity fields populated; validation policy applied; outcome ∈ designed enum.

### M3.2c — controlled audit batch

- Only after M3.2b one-item validation.
- Phase A (11) + Phase B (30).
- Still no snapshot / `attr_*`.
- Same `run_id` for the batch (or one run_id per phase if ops split; never mix with MNN enrichment run 461).
- Summary **must** include: `logical_search_query_count` (alias `search_query_count`); `transport_retry_attempt_count`; `fetched_page_count`; `budget_exhausted_count`.
- Search vs fetch quotas: `logical_search_query_count <= 8` (Q1≤3, Q2≤3, Q3≤2); `transport_retry_attempt_count <= 2` per logical query; `fetched_page_count <= 4`. Transport retries do not increment the logical query count. Fetch only URLs that passed source/domain filter. P3 landing/search pages are not fetched/accepted as SKU evidence unless they lead to a concrete P1 document/card.

### M3.3 / M3.4

- M3.3: human labels + metrics (options below — **not pre-accepted**).
- M3.4: only if metrics pass, separately propose audit logging / `proposed_rx_otc_*`. **No automatic production merge.**

---

## 2. Phase A — known RX/OTC errors (n=11)

Source: `redesign/artifacts/mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv`.

| product_id | text (head) | current final_rx_otc | hint | pass_action | M3.0 best source | in M2-13? | review_label_inconsistency |
|------------|-------------|----------------------|------|-------------|------------------|-----------|----------------------------|
| 1053 | Экзоролфинлак лак 5% | rx | otc | new_enrichment | rls_or_vidal | no | |
| 2621 | Фурацилин таб. 20 мг №20 | rx | otc | reuse_existing_enrichment | snippet/unknown | no | |
| 3065 | Флуконазол-OBL капс. 150 мг №4 | rx | otc | skip_catalog | snippet/unknown | no | |
| 4922 | Термикон спрей 1% 30 г | rx | otc | new_enrichment | rls_or_vidal | no | |
| 4924 | Термикон крем 1% 15 г | rx | otc | new_enrichment | official instruction (brand page, no explicit status) | no | |
| 7275 | Сановаск таб. 50 мг №30 | rx | otc | new_enrichment | rls_or_vidal | no | |
| 10046 | Папаверин таб. 40 мг №10 | rx | otc | new_enrichment | rls_or_vidal | no | |
| 18377 | Йод р-р 5% 25 мл | rx | otc | reuse_existing_enrichment | snippet/unknown | no | |
| 19198 | Зверобоя трава 50 г Фитофарм | otc | (notes: OTC) | new_enrichment | rls_or_vidal | **no** (keep_drug) | **true** |
| 19370 | Дюспаталин таб. 135 мг №15 | rx | otc | new_enrichment | official instruction (no explicit status; form conflict risk vs capsules) | no | |
| 26115 | Амброксол таб. 30 мг №20 Вертекс | rx | otc | skip_strong_input_mnn | snippet/unknown | no | |

All 11 are **in** Phase A. None of the 13 M2 exclusions appear here.

### `product_id=19198` label inconsistency

```text
review_label_inconsistency = true
```

Fact (historic artifacts unchanged):

- current `final_rx_otc` = otc;
- label notes say OTC;
- row nevertheless occurs in the legacy RX/OTC error inventory.

M3.2 rule:

```text
19198 remains eligible for retrieval as Drug + MNN unresolved case.
It is included in Phase A source/identity audit.
It is excluded from RX/OTC correction precision/error denominator
until reviewer provides structured expected_rx_otc:
rx | otc | unknown.
```

Do **not** rewrite historic labels or current artifacts. Leave `expected_rx_otc_manual` / `expected_rx_otc_source` empty for future human review.

Phase A goal: can product-specific P1 retrieval recover explicit status where MNN enrichment could not? Unresolved is a valid outcome.

---

## 3. Phase B — blind validation (n=30)

```text
30 items:
10 from identity_enrichment
10 from previous_enrichment
10 from sem_baseline
```

Stratify on `final_rx_otc_method` from the human-review v2 / results join (run 461), **not** on the 11 error ids.

### Exclude

```text
- M2 approved BAS/Other 13 products;
- 11 known RX/OTC errors;
- unknown / conflict / not_applicable;
- non-drug;
- already labelled blind cases;
- items without usable identity text.
```

M2-13 (must exclude):

```text
56, 75, 249, 3763, 5322, 8201, 9197, 18179, 18830, 21387, 22548, 23695, 26319
```

Also exclude from the blind pool: `label_rx_otc=not_labeled`, `final_rx_otc` empty/unknown/conflict, `product_kind != drug` if present, text length &lt; 3 after identity build.

### Sampling procedure (future runner; not executed now)

1. Load `mnn_identity_enrichment_pass_results.csv` + human-review v2.
2. Keep rows with usable `normalized_text` and drug-like identity (not in M2-13, not in Phase A 11).
3. Split by `final_rx_otc_method` ∈ {`identity_enrichment`, `previous_enrichment`, `sem_baseline`}.
4. Drop unknown / conflict / not_applicable / non-drug / not_labeled.
5. Seeded sample 10 per stratum (`seed=rx_otc_m32_blind_v1`).
6. Freeze the 30 ids in a future allowlist JSON **at M3.2c time** (do not write it in M3.1).
7. Reviewers must not see stratum labels on the blind CSV (keep method in a hidden key file).

If a stratum has &lt;10 eligible rows after filters, do not steal from Phase A; document shortfall and sample all remaining eligible.

---

## 4. Required M3.2 outputs

```text
redesign/artifacts/mnn_rx_otc_retrieval_v1_results.csv
redesign/artifacts/mnn_rx_otc_retrieval_v1_research_context.csv
redesign/artifacts/mnn_rx_otc_retrieval_v1_human_review_errors.csv
redesign/artifacts/mnn_rx_otc_retrieval_v1_blind_review.csv
redesign/artifacts/mnn_rx_otc_retrieval_v1_summary.md
redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl
```

### Review CSV must show

- `product_id`, identity text/query, brand/form/strength/pack/mfr
- `source_url`, `source_type`, `source_tier`, `identity_grade`
- `explicit_status_text` (captured excerpt, ≤500)
- `candidate_rx_otc_value`, `final_rx_otc_value`, `outcome`, `evidence_tier`, `conflict_status`
- comparators: `sem_rx_otc`, `identity_enrichment_rx_otc` / previous
- empty labels: `label_rx_otc`, `label_identity_ok`, `label_source_ok`, `label_critical_false_rx`, `label_notes`
- empty M3.2 review fields (future human): `expected_rx_otc_manual`, `expected_rx_otc_source`, `review_label_inconsistency`

For `19198` only, pre-seed `review_label_inconsistency=true`; leave `expected_rx_otc_manual` / `expected_rx_otc_source` empty.

P2 `supported_only` rows must have `candidate_rx_otc_value=rx|otc` and `final_rx_otc_value` empty/null. P2 never counts as a final accepted RX/OTC value for hard routing, snapshot update, or attr merge.

Reviewers score **retrieval evidence**, not “was Sem lucky”.

---

## 5. Success criteria (options, **not accepted**)

Do not treat these as a passed gate. Propose only:

### Conservative option

```text
Tier 1 precision >= 98%
and 0 critical false RX classification
before using as a soft routing signal.
```

**Critical false RX:** retrieval `accepted` / `tier_1` with `final_rx_otc_value=rx` while human expected value is `otc` (or non-drug). False OTC is also counted in precision but is secondary for pharmacy-safety. `19198` is out of this denominator until `expected_rx_otc_manual` is filled.

### Exploratory option

```text
Measure Tier 1 and Tier 2 separately;
no merge/routing use before human review confirms precision.
```

Report separately:

| Metric | Denominator |
|--------|-------------|
| Tier 1 precision (RX) | human-confirmed among retrieval `accepted` + `final_rx_otc_value=rx`; **exclude 19198** until `expected_rx_otc_manual` is set |
| Tier 1 precision (OTC) | human-confirmed among retrieval `accepted` + `final_rx_otc_value=otc`; **exclude 19198** until structured expected value |
| Tier 2 precision (RX/OTC) | among `supported_only` (`candidate_rx_otc_value` only; `final_rx_otc_value` is null) |
| Coverage | share of Phase A/B with Tier 1 (not a pass threshold) |
| Unresolved rate | acceptable; not a failure |
| Critical false RX | count among Tier 1 `final_rx_otc_value=rx`; conservative option requires 0; **exclude 19198** until expected value |
| Budget | `logical_search_query_count`, `transport_retry_attempt_count`, `fetched_page_count`, `budget_exhausted_count` |

No merge/routing until M3.3 human review confirms precision. Unresolved ≫ unsupported guess.

---

## 6. Comparison protocol

For every labelled row:

1. Record retrieval `outcome` / `candidate_rx_otc_value` / `final_rx_otc_value` / `evidence_tier`.
2. Record Sem / previous enrichment / identity enrichment values (read-only).
3. Human `label_rx_otc` ∈ {`correct`, `incorrect`, `unresolved_acceptable`, `not_labeled`}.
4. Human `expected_rx_otc_manual` ∈ {`rx`, `otc`, `unknown`} when scoring precision (required for `19198` before it enters the error denominator).
5. Disagreement between Sem and retrieval is **not** auto-resolved. Both stay in the CSV.
6. Skip/reuse historical RX is **not** counted as retrieval evidence.
7. P2 `supported_only` is compared on `candidate_rx_otc_value` only; it does not contribute a final accepted value.

---

## 7. M2 gate check inside M3.2

If any of the 13 IDs is accidentally submitted:

- `m2_gate=exclude`
- `outcome=not_applicable`
- `candidate_rx_otc_value=null`
- `final_rx_otc_value=null`
- no search
- still an audit row

A smoke (M3.2a) should include **one** excluded id (e.g. `9197`) to prove the gate, plus one eligible id stub.

---

## 8. Isolation confirmation block (every M3.2 summary)

```text
design/runtime confirmation:
- no web/LLM/DB in M3.2a;
- M3.2b/c search only after explicit approval;
- no attr/snapshot/product_kind/prod/Sem changes;
- no git commit/push unless separately requested;
- workflow inactive after creation;
- one run_id across ladder;
- no full raw evidence in PostgreSQL.
```
