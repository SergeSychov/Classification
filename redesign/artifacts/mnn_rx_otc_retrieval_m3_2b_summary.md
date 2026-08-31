# M3.2b one-item live RX/OTC retrieval

**SKU:** `3065` ФЛУКОНАЗОЛ-OBL капсулы 150 мг N4 ОБОЛЕНСКОЕ ФП АО
**run_id:** `20260818` (`ephemeral_artifact_only`) — artifacts only, no `classification_runs`
**n8n workflow:** `rx-otc-product-retrieval-dev` left **inactive** (HTTP ran in this runner)

## Result

| Field | Value |
|-------|-------|
| outcome | `supported_only` |
| candidate_rx_otc_value | `otc` |
| final_rx_otc_value | `None` |
| evidence_tier | `tier_2_supported_soft_signal` |
| conflict_status | `no_conflict` |
| error_code | `None` |
| stop_reason | `fetch_budget` |
| logical_search_query_count | 7 (cap 8) |
| transport_retry_attempt_count | 1 (cap 2/query) |
| fetched_page_count | 4 (cap 4) |
| budget_exhausted | True |

Identity: `"ФЛУКОНАЗОЛ-OBL" "капсулы" "150 мг"`

Best evidence: `https://www.vidal.ru/drugs/fluconazole-obl__37379` · `rls_or_vidal_product_card` / `P2` · identity `A`
Excerpt: ное ВОЗ Лекарственные формы Флуконазол-OBL Без рецепта Капсулы 150 мг: 1 шт. РУ: ЛП-№(001911)-(РГ-RU) от 09.03.23 - Бессрочно Дата переоформления: 24.09.24

Comparators (read-only): sem=`rx` catalog=`otc`

## Fetched pages

- `200` `pharmacy_product_card` identity `A` status=`None` passed=`False` — https://apteka.ru/product/flukonazol-obl-150-mg-1-sht-kapsuly-610a85806b773f4f59e2327e/instructions/
- `200` `pharmacy_product_card` identity `A` status=`None` passed=`False` — https://aptekamos.ru/tovary/lekarstva/flukonazol-993/flukonazol-obl-kapsuly-150mg-75502/instrukciya
- `200` `rls_or_vidal_product_card` identity `A` status=`otc` passed=`True` — https://www.vidal.ru/drugs/fluconazole-obl__37379
- `200` `pharmacy_product_card` identity `A` status=`None` passed=`False` — https://apteka.ru/product/flukonazol-obl-150-mg-1-sht-kapsuly-6915d215b54aad490ad35011/

## Notes

- SearXNG default engines were unresponsive (brave/google cse/startpage 429, DDG/Startpage CAPTCHA); the same logical queries retried with `engines=bing` (counts as transport retry, not a new logical query).
- Q1 `site:grls.rosminzdrav.ru` returned no GRLS product records (Bing does not surface `Grls_view_V2`). No P1 evidence this run — `final_rx_otc_value` stays null.
- P1 official GRLS/MAH instruction was not fetched or validated.
- P2 Vidal product card `fluconazole-obl` had explicit «Без рецепта» next to «Флуконазол-OBL» / «Капсулы 150 мг». P2 may set `candidate_rx_otc_value` only.
- `apteka.ru` fetches returned a JS shell (CSS `@keyframes`), not instruction text — correctly `no_explicit_status`.

## Isolation

- LLM: `False`
- postgres_write: `False`
- snapshot/attr/product_kind: `False` / `False` / `False`
- n8n workflow active: `False`
- HTTP: SearXNG `http://85.198.66.232:8080/search` + optional page fetch of filtered P1/P2 URLs
- Isolation block: no snapshot / `attr_*` / `product_kind` / PostgreSQL / LLM / n8n activation

## Artifacts

- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_one_item.json`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_human_review.csv`
- `redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl`

Unresolved is a valid M3.2b outcome. This run is `supported_only` (P2 candidate only). Do not merge to `attr_rx_otc`. Do not start M3.2c without explicit ask.
