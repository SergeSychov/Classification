# M3.2b.2 evidence contract validation

**Mode:** offline replay (`network_disabled=true`). No SearXNG / HTTP / LLM / n8n / DB.
**contract_version:** `rx_otc_evidence_contract_v2`
**SKU:** 3065

## Old vs v2 counts

| Layer | Old `validated_evidence` | v2 |
|-------|--------------------------:|----:|
| mixed validated_evidence | 24 | 4 (fetched only) |
| from_fetch=true / fetched_documents | 4 | 4 |
| from_fetch=false / discovery_hits | 20 | 20 |
| non-fetched removed from validated_evidence | — | 20 |

v2 evidence by tier: P1=0 P2=4 P3=0.
Explicit status in validated: 1. validation_passed: 1.

## Candidate / final / outcome

| Field | Old | v2 |
|-------|-----|----|
| outcome | `supported_only` | `supported_only` |
| candidate_rx_otc_value | `otc` | `otc` |
| final_rx_otc_value | `None` | `None` |
| evidence_tier | `tier_2_supported_soft_signal` | `tier_2_supported_soft_signal` |
| conflict_status | `no_conflict` | `no_conflict` |

Policy result unchanged: P2 candidate `otc`, final null, `supported_only`.

## Invariants

| Invariant | Value | Result |
|-----------|-------|--------|
| `all_validated_from_fetch` | `True` | PASS |
| `all_validated_http_2xx` | `True` | PASS |
| `all_status_text_from_fetched_content` | `True` | PASS |
| `discovery_candidate_count_zero` | `True` | PASS |
| `p2_final_value_null` | `True` | PASS |
| `p3_candidate_count_zero` | `True` | PASS |
| `network_disabled` | `True` | PASS |
| `replay_mode` | `True` | PASS |
| `original_sha256_unchanged` | `True` | PASS |
| `outcome_supported_only` | `True` | PASS |
| `candidate_otc` | `True` | PASS |
| `final_null` | `True` | PASS |

**invariants_pass:** `True`

## Fixture tests

| Case | Result |
|------|--------|
| A non-fetched snippet | PASS |
| B fetched Vidal P2 | PASS |
| C fetched P1 synthetic | PASS |
| D fetched P3 | PASS |

## SHA256 before / after

| File | before | after | |
|------|--------|-------|-|
| `scripts/run_rx_otc_m3_2b_one_item.py` | `7086223c1b70a45ff096b73a4b6bf6e0cb6e20c064072dbe4cfa8c4de25227bb` | `9f3abd07b4aad3d570e8118adb63518a26744dd8ab37bd5c72dee81c660100fc` | changed (runner patch) |
| `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_one_item.json` | `779731282bcae3928946d4c87f22b5b2ffe02efd077e28ad6567b1f67dadd714` | `779731282bcae3928946d4c87f22b5b2ffe02efd077e28ad6567b1f67dadd714` | unchanged |
| `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_human_review.csv` | `28e2cd2752dc0b215707840488d7fb10ed61371277354a2b9d41298edad26271` | `28e2cd2752dc0b215707840488d7fb10ed61371277354a2b9d41298edad26271` | unchanged |
| `redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl` | `f1facc7ba608fedfd882208d9dec3f23cd31904409d0a34422f17b8f88f2af74` | `f1facc7ba608fedfd882208d9dec3f23cd31904409d0a34422f17b8f88f2af74` | unchanged |
| `redesign/m3_1_rx_otc_retriever_contract.json` | `f5d87f4252040af233d1203fad57f64d662b6c7c4fab6715a60d62852477d93a` | `f5d87f4252040af233d1203fad57f64d662b6c7c4fab6715a60d62852477d93a` | unchanged |
| `redesign/m3_1_rx_otc_retriever_design.md` | `2cd9136985d9b676477950e2e53e779f777dd0030cbcce9db0271d49d56cd12b` | `2cd9136985d9b676477950e2e53e779f777dd0030cbcce9db0271d49d56cd12b` | unchanged |

Original M3.2b JSON / CSV / JSONL and M3.1 design/contract files are byte-identical.

## Isolation

- no HTTP / SearXNG / LLM / web calls
- no n8n workflow change or execution
- no DB / classification_runs / snapshot / attr_* / product_kind
- no git commit / push
