# M3.2b.3 P1 feasibility mini-batch

**contract_version:** `rx_otc_evidence_contract_v2`
**runner:** `scripts/run_rx_otc_m3_2b_3_p1_feasibility.py`
**recommendation:** `DO_NOT_RUN_PHASE_A_YET`

Feasibility only. Audit-only. No n8n, DB, snapshot, `attr_*`, LLM, or Phase A/B expansion.
A P2 Vidal/RLS/pharmacy candidate does **not** count as P1 success.

## 1. Mini-batch IDs and identity check

| product_id | identity | form | m2_gate | expected_test_focus | substitution |
|------------|----------|------|---------|---------------------|--------------|
| 3065 | ФЛУКОНАЗОЛ-OBL капсулы 150 мг N4 ОБОЛЕНСКОЕ ФП АО | капсулы | pass | p1_discovery | none |
| 4922 | ТЕРМИКОН спрей 1% ФАРМСТАНДАРТ-ЛЕКСРЕДСТВА ОАО | спрей | pass | form_mismatch_guard | none |
| 4924 | ТЕРМИКОН крем 1% ЛЕККО ЗАО | крем | pass | official_instruction_feasibility | none |
| 19370 | ДЮСПАТАЛИН таблетки 135 мг N15 ВЕРОФАРМ АО | таблетки | pass | form_mismatch_guard | none |
| 26115 | АМБРОКСОЛ таблетки 30 мг N20 ВЕРТЕКС АО | таблетки | pass | skip_path_no_existing_evidence | none |

- exactly 5 unique IDs; none in M2-13
- `4922` spray ≠ `4924` cream; both remain separate records
- `used_mnn_as_primary_query=false` on all five
- no expected RX/OTC invented in the manifest

## 2. P1 feasibility by SKU

| product_id | p1_feasibility_status | best P1 | outcome | candidate | final |
|------------|----------------------|---------|---------|-----------|-------|
| 3065 | `p1_not_found` | none | `supported_only` | otc (P2 Vidal) | null |
| 4922 | `p1_found_but_identity_insufficient` | GRLS View URL fetched, identity D | `unresolved` | null | null |
| 4924 | `p1_not_found` | none; `termikon.ru` not in hits | `unresolved` | null | null |
| 19370 | `p1_not_found` | none | `supported_only` | otc (P2 Vidal tablets 135 mg) | null |
| 26115 | `p1_not_found` | none; 0 fetches | `unresolved` | null | null |

## 3. Counts

- eligible_sku_count = **5**
- p1_found_and_valid_count = **0**
- p1_found_but_not_valid_count = **1** (4922)
- p1_not_found_or_fetch_failed_count = **4**
- p2_supported_only_count = **2** (3065, 19370)
- unresolved_count = **3** (4922, 4924, 26115)

## 4. Form mismatch / near-brand

- `4922` spray: Vidal cream card `termicon__13678` and apteka.ru **tablets 250 mg** rejected as form mismatch / identity D. Guard visible.
- `4924` cream: no form_mismatch flag; cream Vidal `13678` matched form, but tablet/multi-form pages also matched `крем` as a token (guard leak on combined brand pages). Still no explicit status → no candidate.
- `19370` tablets 135 mg: Vidal capsules 200 mg (`duspatalin__1486`) rejected `form_mismatch` (RX phrase present, not usable). Vidal tablets 135 mg (`duspatalin__33504`) accepted as **P2 only**. Capsule pharmacy card 200 mg leaked identity A because the body also mentions tablets; it had no explicit status so it did not become a candidate.
- near-brand: **0**
- generic MNN-as-primary-query: **0**

## 5. Per-SKU budgets

| product_id | logical Q | transport retries | fetches | budget_exhausted | stop_reason |
|------------|-----------|-------------------|---------|------------------|-------------|
| 3065 | 7/8 | 1 | 4/4 | true | fetch_budget |
| 4922 | 7/8 | 1 | 4/4 | true | fetch_budget |
| 4924 | 7/8 | 1 | 4/4 | true | fetch_budget |
| 19370 | 7/8 | 1 | 4/4 | true | fetch_budget |
| 26115 | 8/8 | 1 | 0/4 | true | search_budget (logical cap; no eligible URL) |

No SKU exceeded logical 8 or fetch 4. Transport retries = 1 per SKU (default SearXNG engines empty/CAPTCHA → bing), ≤2 per logical query.

## 6. Contract v2

All five SKUs **PASS**:

- validated evidence only from fetched 2xx documents
- explicit status only from fetched body
- discovery hits have no candidate / no explicit_status_text
- P2 `final_rx_otc_value` always null
- P3 candidate/final null
- only P1 may set final; no valid P1 → all finals null

## 7. Acquisition blockers (why P1 failed)

Current route **can HTTP-fetch a GRLS `Grls_View_v2.aspx?routingGuid=…` URL**, but it does **not** obtain a usable product-specific P1 document.

1. **GRLS View is a JS/ASP.NET shell.** Fetched 4922 View pages return portal chrome (`Государственный реестр лекарственных средств`) plus unrelated listing fragments (`шприцы`, `По рецепту`). Brand Термикон is absent → identity D. Explicit-status regex hits leftover listing text, correctly discarded.
2. **Bing via SearXNG ignores `site:grls.rosminzdrav.ru` for most SKUs.** 3065/4924/19370/26115 Q1 hits are pharmacy/Vidal/noise, not GRLS records. 4922 Q1 did return View URLs, but they are not Termicon spray records (generic GRLS titles, no brand in snippet).
3. **Official MAH / instruction hosts never appear.** No `termikon.ru`, `obolensk.ru`, `vertex.ru`, `lekko.ru`, `duspatalin.ru` in this mini-batch’s discovery hits. Q2 therefore has nothing P1-eligible to fetch.
4. **Fetch budget is consumed by P2 after Q1/Q2 miss.** 3065/4922/4924/19370 spent remaining fetches on Vidal/RLS/pharmacy. That is allowed only after no accepted P1; it confirms the route currently lands on P2 support cards.
5. **26115 query collapse.** Quoted `АМБРОКСОЛ` + Russian operators via Bing returned bahn.de / OBS / MMD / Dutch classifieds. Zero P1/P2 URLs, zero fetches. Generic INN-as-display-brand is an acquisition dead end on this search path.
6. **GRLS product records are fetched without a brand locator.** Unrelated View GUIDs burn Q1 fetch slots. Even with a “looks like P1” URL, identity A/B + product-specific match does not hold.

**Conclusion:** the acquisition route technically reaches a GRLS View URL once, but in this mini-batch it yields only P2 support cards (or nothing). It does not currently produce valid P1 evidence.

## 8. Recommendation

`DO_NOT_RUN_PHASE_A_YET`

Zero valid P1 results (`p1_found_and_valid_count = 0`). Phase A 11-SKU batch would repeat the same acquisition failure. Do not start M3.2c.

Unblockers for a later iteration (not done here): product-specific GRLS fetch that returns the actual record body; official-instruction URL discovery that surfaces MAH hosts; do not treat GRLS View chrome as a product record; keep P2 out of the P1 success criterion.

## 9. Artifacts

- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_input_manifest.csv`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_results.csv`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_research_context.csv`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_summary.md`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_summary.json`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_human_review.csv`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_searxng_raw.jsonl`
- `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_contract_validation.json`
- runner: `scripts/run_rx_otc_m3_2b_3_p1_feasibility.py`

Original M3.2b / M3.2b.2 artifacts were not overwritten (SHA256 unchanged).

## 10. Isolation

- n8n workflow `UqssZ24Jr7Qk9ef4` / `rx-otc-product-retrieval-dev` not modified, not executed, remains inactive
- no PostgreSQL / `classification_runs` / snapshot / `attr_*` / `product_kind` / `product_type`
- no LLM / MNN enrichment
- no prod Stage 2 / hierarchy-dev changes in this task
- no git commit / push
