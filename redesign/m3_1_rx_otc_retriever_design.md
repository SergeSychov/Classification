# M3.1 — RX/OTC Product Retrieval: standalone workflow design

**Status:** DESIGN ONLY. No workflow created. No search, LLM, n8n, or PostgreSQL actions.  
**Working name:** `rx-otc-product-retrieval-dev`  
**workflow_version:** `rx_otc_retrieval_dev_v1`  
**Future status after creation:** inactive  
**Date:** 2026-08-18  
**Depends on:** Wave-500 identity enrichment `run_id=461`, M3.0 source audit, M2 reviewed freeze.

This document is the human-readable architecture. Machine contract: [`m3_1_rx_otc_retriever_contract.json`](m3_1_rx_otc_retriever_contract.json). Query examples (not executed): [`m3_1_rx_otc_retriever_query_examples.csv`](m3_1_rx_otc_retriever_query_examples.csv). Future log/DB proposal: [`m3_1_rx_otc_retriever_data_model.md`](m3_1_rx_otc_retriever_data_model.md). M3.2 plan: [`m3_1_rx_otc_retriever_m3_2_test_plan.md`](m3_1_rx_otc_retriever_m3_2_test_plan.md).

---

## 0. Verified baseline (read-only)

Sources used in this design (no writes):

| File | Role |
|------|------|
| `Categories/stage2_workflow_plan.md` | Stage 2 / hierarchy isolation, Code-node pattern, journal п.38–39 |
| `redesign/00_PROJECT_STATUS.md` | MNN/RX/Age baseline; M2 freeze; next = M3 |
| `redesign/29_SHORT_ROADMAP.md` | M3 RX/OTC calibration not a hard gate |
| `redesign/artifacts/mnn_identity_enrichment_pass_review_metrics_v1.md` | Headline metrics run 461 |
| `redesign/artifacts/mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv` | 11 confirmed RX/OTC error rows |
| `redesign/artifacts/mnn_rx_otc_source_audit_v1_summary.md` (+ `.json`, data dictionary) | M3.0 sufficiency / source hierarchy draft |
| `scripts/mnn_rx_otc_source_audit_v1.py` | Source taxonomy, explicit-status regex, sufficiency rule |
| `scripts/mnn_identity_enrichment_pass.py` | Why skip/reuse paths produced RX without product-card evidence |
| `scripts/mnn_non_drug_override_policy_v1.py` | M2 candidate construction |
| `redesign/artifacts/mnn_identity_enrichment_pass_results.csv` | Identity fields / pass_action for error SKUs |
| `redesign/artifacts/mnn_identity_enrichment_pass_research_context.csv` | RC coverage: 7/11 error rows |
| `redesign/artifacts/mnn_non_drug_override_policy_v1_reviewed.csv` | 13 applied BAS/Other exclusions |
| `redesign/artifacts/mnn_non_drug_override_policy_v1_implementation_contract.md` | Draft, not applied |

**Note:** `mnn_rx_otc_source_audit_v1.csv` was specified as an input. At design time the row-level CSV was not present on disk; the verified summary/json + error inventory + audit script were used. Headline numbers below match `mnn_rx_otc_source_audit_v1_summary.md` and `mnn_identity_enrichment_pass_review_metrics_v1.md`.

### Headline numbers (Wave-500 / run_id=461)

```text
MNN drugish accuracy: 82/83 = 98.8%
Correct null-MNN non-drug: 17
RX/OTC accuracy: 72/83 = 86.7%
Age accuracy: 59/83 = 71.1%

M3.0:
RX/OTC confirmed error rows: 11
Existing product-specific sufficient RX/OTC evidence: 0/11
Saved GRLS product-card evidence: 0/11
Best existing source distribution:
- RLS/Vidal product card: 5
- official instruction/manufacturer: 2
- search snippet/unknown: 4
GRLS landing/regulatory URLs exist in some rows, but not product-specific records.
Explicit RX/OTC status in saved titles/excerpts: 0/11.
4 error cases lack saved RC/raw evidence because they came through skip/reuse paths.

M2:
13 approved BAS/Other candidates excluded from future drug-MNN routing
  (12 bas + 1 other=9197; queue action remove_from_future_mnn_human_queue).
19198 Зверобоя трава remains a drug / retain-in-queue special case (not in the 13).
  review_label_inconsistency=true: current final_rx_otc=otc and notes say OTC,
  yet the row is in the legacy RX/OTC error inventory. Eligible for Phase A
  source/identity audit; excluded from RX/OTC correction precision denominator
  until structured expected_rx_otc is provided. Do not rewrite historic labels.
```

### Why a new layer

MNN enrichment successfully resolves MNN. RX/OTC cannot be accepted as a side-effect of generic search-grounded MNN enrichment:

- skip/reuse paths (`skip_catalog`, `skip_strong_input_mnn`, `reuse_existing_enrichment`) can emit RX/OTC without product-card evidence;
- saved GRLS hits are landings (`grls.rosminzdrav.ru/`), not product records;
- RLS/Vidal and pharmacy cards were treated as truth and sometimes matched the wrong form;
- 0/11 error rows have explicit “по рецепту / без рецепта” in captured titles/excerpts.

**RX/OTC is not ready for routing.** This design does not authorize `attr_rx_otc` merge or hard RX-cluster gates.

---

## 1. Architecture decision (locked)

```text
RX/OTC retrieval = отдельный standalone workflow
`rx-otc-product-retrieval-dev`.

Он не является подветкой mnn-drug-enrichment
и не встраивается в current Stage 2 / hierarchy workflow.
```

### Reasons

1. RX/OTC is a property of a **registered product** (brand + form + strength + pack + market), not of an MNN alone. The same INN can be RX in one form and OTC in another (Термикон spray vs tablets; Дюспаталин tablets vs capsules).
2. Current MNN evidence policy (molecule/brand hit + aggregator card) is **insufficient** for RX/OTC. M3.0: 0/11 sufficient product-specific evidence.
3. RX/OTC needs its own source hierarchy (P1 GRLS/official instruction ≫ P2 RLS/Vidal/pharmacy ≫ P3 discovery-only).
4. Quality metrics must be separate from MNN accuracy (already 98.8% drugish vs 86.7% RX/OTC).
5. The workflow must be reusable for: missing RX/OTC, conflicting RX/OTC, suspected-wrong RX/OTC, and new drug SKUs.
6. MNN and RX/OTC must have **different acceptance contracts**. An accepted MNN must never auto-accept RX/OTC.

### Isolation from existing systems

| System | Relationship |
|--------|----------------|
| MNN catalog identity gate | Input may *read* `mnn_if_known`. No write, no shared acceptance. |
| `mnn-drug-enrichment` (`bEyKA1JJr0swuLql`) | Not a sub-branch. Do not POST to its webhook for RX/OTC. |
| Sem / Sem0 / Sem1 / Norm attrs | Sem `attr_rx_otc` is baseline provenance only. No overwrite. |
| Dir / Need / Category routing | Not connected. |
| prod `classification-stage2-dev` | Untouched. |
| `classification-stage2-hierarchy-dev` | Untouched. No Load/allowlist coupling. |
| M2 BAS/Other freeze | Read-only exclusion gate (13 IDs) → `not_applicable`. |

---

## 2. Future workflow isolation

```text
name: rx-otc-product-retrieval-dev
workflow_version: rx_otc_retrieval_dev_v1
status after creation: inactive
entrypoints:
- Manual Trigger
- dedicated Webhook
```

Proposed webhook path (not created): `POST /webhook/rx-otc-product-retrieval-dev`.

### M3.2 isolation (mandatory)

```text
- no connection to prod Stage 2;
- no connection to hierarchy-dev;
- no product_classification snapshot update;
- no attr_rx_otc update;
- no product_kind / product_type update;
- no PostgreSQL write on first skeleton smoke;
- output only webhook response + artifacts;
- future logging design allowed, but actual DB logging only after
  explicit approval and one-item smoke validation.
```

### Rollout

```text
M3.2a:
Create inactive standalone skeleton with stubbed external nodes.
No DB writes, no external calls.

M3.2b:
After explicit approval, connect retrieval/search nodes and execute
one manually selected product only.

M3.2c:
After one-item validation, controlled audit batch:
11 confirmed RX/OTC error cases + blind sample.
Still no snapshot/attr_* updates.

M3.3:
Human review and acceptance metric calculation.

M3.4:
Only if metrics pass: separately propose audit logging / proposed
RX/OTC layer. No automatic production merge.
```

Skeleton-first is non-negotiable. Do not create the workflow in this task.

---

## 3. Source hierarchy

### Locked statements

- **GRLS official product record** and **official current instruction / MAH site** are P1 primary.
- **Приказ Минздрава №100н** is **regulatory context only**. It governs dispensing rules in general; it is **not** evidence of RX/OTC for a specific SKU.
- Generic MNN / molecule pages, search snippets, and GRLS landing/search pages are **P3 discovery only**. They cannot establish RX/OTC.
- No automatic acceptance without **explicit captured status text** from the source (not from an LLM summary).
- P2 (RLS/Vidal/pharmacy) may emit `tier_2_supported_soft_signal` only. Not sufficient for hard routing or DB merge.

### P1 — primary evidence

```text
grls_official_product_record
official_instruction_product_specific
official_manufacturer_or_marketing_authorization_holder
```

P1 acceptance conditions (all required):

```text
- product-specific or brand+form-specific source;
- identity grade A or B;
- explicit RX/OTC status text in captured source:
  “по рецепту”,
  “отпускается по рецепту”,
  “рецептурный”,
  “без рецепта”,
  “безрецептурный отпуск”,
  or approved equivalent;
- exact URL is saved;
- excerpt containing status is saved;
- matched identity dimensions are saved;
- no comparable P1 conflict.
```

Host heuristics (design, not executed):

| source_type | Typical hosts / paths |
|-------------|------------------------|
| `grls_official_product_record` | `grls.rosminzdrav.ru` product/card/reg path (not `/` or `/grls` landing); official EGISZ GRLS product record |
| `official_instruction_product_specific` | Manufacturer / MAH domain instruction page that names brand+form(+strength) |
| `official_manufacturer_or_marketing_authorization_holder` | Same class when the page is the holder’s product dossier rather than a PDF instruction |

Third-party GRLS mirrors (`grls.pharm-portal.ru` and similar) are **not** official GRLS. Classify as `other` → P3 unless later explicitly promoted.

### P2 — supporting evidence

```text
rls_or_vidal_product_card
pharmacy_product_card
```

```text
- may produce tier_2_supported_soft_signal;
- only with explicit status and identity A/B;
- may set candidate_rx_otc_value = rx|otc;
- never sets final_rx_otc_value (always null on P2-only);
- not sufficient for hard routing;
- not sufficient for snapshot update or attr merge;
- not sufficient for DB merge;
- must lose to valid P1 if conflict.
```

P2 never sets a final accepted RX/OTC value and cannot be used for hard routing, snapshot update, or attr merge.

### P3 — discovery only

```text
generic_mnn_or_molecule_page
search_snippet
grls_landing_or_search_page
regulatory_context
unknown
```

```text
- cannot establish RX/OTC;
- may only expand query or trigger unresolved/retry;
- cannot produce accepted value.
```

`regulatory_context` includes Приказ №100н, Minzdrav opendata dumps, GRLS home/search without a product id.

### Source hierarchy table

| source_type | source_tier | allowed_use | may_set_rx_otc | required_identity | required_explicit_status | rejection_conditions |
|-------------|-------------|-------------|----------------|-------------------|--------------------------|----------------------|
| `grls_official_product_record` | P1 | establish RX/OTC if all P1 gates pass | **yes**, as `tier_1_product_specific` (audit-only in M3.2) | A or B; product-specific or brand+form-specific | yes, captured excerpt | landing path; identity C/D; no status text; P1/P1 conflict; foreign-market-only record |
| `official_instruction_product_specific` | P1 | same as GRLS product record | **yes**, tier_1 (audit-only in M3.2) | A or B | yes | brand-only page; wrong form/strength; generated summary; no excerpt |
| `official_manufacturer_or_marketing_authorization_holder` | P1 | same | **yes**, tier_1 (audit-only in M3.2) | A or B | yes | marketing page without status; near-brand line extension |
| `rls_or_vidal_product_card` | P2 | supporting soft signal only | **no** final value (`candidate` only; `final_rx_otc_value=null`) | A or B | yes | `/inn/` `/mnn/` molecule page (then P3); form mismatch; no status |
| `pharmacy_product_card` | P2 | supporting soft signal only | **no** final value (`candidate` only; `final_rx_otc_value=null`) | A or B | yes | wrong SKU; marketplace copy without status |
| `generic_mnn_or_molecule_page` | P3 | discovery / query expansion only | **no** | n/a | n/a | any attempt to accept |
| `search_snippet` | P3 | discovery only | **no** | n/a | n/a | any attempt to accept |
| `grls_landing_or_search_page` | P3 | discovery only (may justify Q1 retry with tighter identity) | **no** | n/a | n/a | treating landing as product card |
| `regulatory_context` | P3 | normative context only | **no** | n/a | n/a | Приказ №100н or general RX lists used as SKU proof |
| `unknown` | P3 | drop / unresolved | **no** | n/a | n/a | empty URL, unclassifiable host |

**Приказ Минздрава №100н = `regulatory_context` = P3.** It must never set RX/OTC for an SKU.

---

## 4. Product identity contract

The RX/OTC layer **temporarily deduplicates input text itself**. It must **not** mutate current `normalized_text`, Norm v1–v3 nodes, or any Sem attr.

### Input fields

| Field | Required | Notes |
|-------|----------|-------|
| `product_id` | yes | bigint |
| `normalized_text_full` | yes | current noisy Norm text; preserved verbatim |
| `brand_or_product_name` | no | if absent, parse from first `|` segment |
| `dosage_form` | no | parsed if missing |
| `strength` | no | parsed if missing |
| `pack` | no | parsed if missing |
| `manufacturer_normalized` | no | parsed; pick one canonical |
| `mnn_if_known` | no | **never** used as Q1-only query when a trade name exists |
| `country_or_market_if_known` | no | default `RU` |

Optional provenance (read-only, never overwritten): `sem_rx_otc`, `catalog_rx_otc`, `previous_enrichment_rx_otc`, `identity_enrichment_rx_otc`.

### Output identity fields

| Field | Meaning |
|-------|---------|
| `rx_otc_identity_text` | Compact canonical identity string |
| `rx_otc_identity_query` | Default quoted query core: brand + form + strength |
| `rx_otc_identity_fingerprint` | sha256 of canonical dims (brand\|form\|strength\|pack\|mfr\|market) |
| `rx_otc_brand_norm` | Trade name, not MNN |
| `rx_otc_form_norm` | Canonical dosage-form token |
| `rx_otc_strength_norm` | Canonical strength |
| `rx_otc_pack_norm` | Canonical pack |
| `rx_otc_manufacturer_norm` | Single manufacturer |

### Text normalization (deterministic)

Apply only inside this workflow’s identity builder.

1. **Preserve** `normalized_text_full` unchanged.
2. Split on `|`. Collapse adjacent duplicate segments (Wave-500: manufacturer-like dups **100/100**, pack-token dups **14/100**).
3. Unicode: `ё→е` for matching only; display may keep original brand spelling.
4. Units (spacing + aliases → canonical):
   - `мг` / `mg` → `мг`
   - `мкг` / `mcg` / `µg` → `мкг`
   - `г` / `g` (not as part of `мг`) → `г`
   - `%` unchanged
   - `мл` / `ml` → `мл`
   - `л` / `l` → `л`
   - `ЕД` / `ED` / `IU` → `ЕД`
   - insert a space between number and unit: `150МГ` → `150 мг`
5. Pack: `N30` / `№30` / `No30` / `N 30` → `N30`. Drop repeated pack tokens.
6. Dosage-form vocabulary (canonical; extend Sem form dict, do not write Sem):

| Canonical | Signals |
|-----------|---------|
| `таблетки` | табл., таб., п/о, п/плен/об. |
| `таблетки_для_раствора` | табл. д/р-ра, для приготовления раствора |
| `капсулы` | капс. |
| `раствор` | р-р, раствор (в т.ч. спиртовой) |
| `крем` | крем |
| `мазь` | мазь |
| `гель` | гель |
| `спрей` | спрей |
| `лак` | лак д/ногтей |
| `трава` | трава, сырьё растительное |
| `фильтр-пакеты` | ф/п |
| `порошок` | пор. |
| `сироп` | сироп |
| `капли` | капли |
| `суппозитории` | супп., свечи |

Unknown form → keep raw token, mark `form_confidence=low`.

7. Manufacturer: take the first non-empty manufacturer-like segment after the product head; drop legal-form noise only for fingerprint (`ООО|АО|ЗАО|ОАО` kept in display, stripped for near-dup). Choose **one** canonical manufacturer.
8. Build:
   - `rx_otc_identity_text` = `brand form strength pack manufacturer` compact
   - `rx_otc_identity_query` = `"brand" "form" "strength"` (omit empty parts; **do not** insert MNN)

### Identity grades

```text
A:
brand + form + strength/pack + manufacturer or product-record identity.

B:
brand + one reliable secondary:
form / strength / pack / manufacturer.

C:
brand only, MNN only, generic name, unclear form,
or similar variant without enough confirmation.

D:
near-brand, different form, different strength,
different market, wrong product, contradictory identity.

unknown:
insufficient source data.
```

`product-record identity` for grade A without all SKU dims: official GRLS registration number / LP card that uniquely identifies this SKU.

### Match rules (brand ≠ MNN)

| Check | Pass | Fail → typically |
|-------|------|------------------|
| **Brand match** | Trade name token (e.g. `Флуконазол-OBL`, `Дюспаталин`, `Термикон`) in source | Matching only INN `флуконазол` / `мебеверин` / `тербинафин` is **MNN match**, not brand match |
| **Near-brand** | — | Longer/other brand containing the token (`НООТРОП` vs `НООТРОПИЛ`); same family different SKU (`Термикон` tablets page for spray/cream) |
| **Form mismatch** | Canonical form equal or approved synonym | Tablets evidence for cream/spray/lacquer SKU |
| **Dosage mismatch** | Same numeric+unit (150 мг vs 150мг) | 50 мг vs 100 мг; 1% vs 250 мг tablets |
| **Pack mismatch** | Pack equal or source omits pack (pack optional for A/B if form+strength match) | Explicit other pack used as the only identity secondary |
| **Manufacturer mismatch** | Same holder / known successor | Different MAH with no record link; used as disambiguator, not as a hard reject if GRLS card matches brand+form+strength |
| **RU market / registration** | `grls.rosminzdrav.ru` product record or RU instruction | Foreign registry / `.kz` / EU SmPC as sole P1 → market mismatch (grade D for RU SKU) |

### Work with noisy Norm (until Norm v4)

Do **not** wait for Norm v4. The identity builder:

- strips duplicate `|` manufacturer tails;
- strips duplicate pack tokens;
- does not write back to `normalized_text` or Norm nodes.

---

## 5. Query strategy (ladder; not executed)

Never start with an MNN-only query when a trade name exists. Brand + form + strength outrank generic name. Manufacturer/pack are **disambiguators**, not default Q1.

### Layers

| Layer | query_kind | Source target | Max queries | Role |
|-------|------------|---------------|-------------|------|
| Q1 | `grls_primary` | GRLS product record | **3** | P1 discovery |
| Q2 | `official_instruction` | official instruction / MAH | **3** | P1 if Q1 did not accept |
| Q3 | `support_card` | RLS/Vidal product card | **2** | P2 soft signal only |

### Templates

**Q1 — GRLS primary discovery**

```text
"<brand>" "<form>" "<strength>" site:grls.rosminzdrav.ru
"<brand>" "<form>" "<strength>" ГРЛС
"<brand>" "<manufacturer>" site:grls.rosminzdrav.ru
"<brand>" site:grls.rosminzdrav.ru
```

**Q2 — official instruction / official holder**

```text
"<brand>" "<form>" "<strength>" инструкция условия отпуска
"<brand>" "<form>" "<strength>" "по рецепту"
"<brand>" "<form>" "<strength>" "без рецепта"
"<brand>" "<form>" "<strength>" официальный сайт инструкция
```

**Q3 — supporting source cards**

```text
"<brand>" "<form>" "<strength>" site:rlsnet.ru
"<brand>" "<form>" "<strength>" site:vidal.ru
```

Template catalogs may list more strings than the executed cap. Runtime executes **at most** the per-layer max (Q1=3, Q2=3, Q3=2) and **at most 8 search queries** per eligible SKU.

Each attempt stores `query_kind` and `reason`. Designed (not executed) examples: [`m3_1_rx_otc_retriever_query_examples.csv`](m3_1_rx_otc_retriever_query_examples.csv). CSV rows beyond the executed cap are template illustrations, not a license to exceed budget.

### Budgets and policies

Search query and fetch page are **different quotas**.

```text
logical_search_query_count <= 8
transport_retry_attempt_count <= 2 per logical query
fetched_page_count <= 4

max_search_queries_per_eligible_sku = 8   # alias of logical_search_query_count
Q1_GRLS_max_queries = 3
Q2_official_instruction_max_queries = 3
Q3_support_max_queries = 2

max_fetched_candidate_pages_per_eligible_sku = 4
```

Search-query budget counts **logical** ladder queries only. Transport retries of the same logical query do **not** increment `logical_search_query_count`. This cap is for M3.2b+ (HTTP); M3.2a skeleton has HTTP forbidden and is unaffected.

| Policy | Value |
|--------|--------|
| `logical_search_query_count` | **≤ 8** |
| `transport_retry_attempt_count` | **≤ 2 per logical query** |
| `fetched_page_count` | **≤ 4** |
| `max_search_queries_per_eligible_sku` | **8** (alias of logical count) |
| `Q1_GRLS_max_queries` | **3** |
| `Q2_official_instruction_max_queries` | **3** |
| `Q3_support_max_queries` | **2** |
| `max_fetched_candidate_pages_per_eligible_sku` | **4** |
| Fetch eligibility | Fetch **only** candidate URLs that passed source/domain filter |
| P3 landing/search pages | Do **not** fetch/accept as SKU evidence, except when they lead to a concrete P1 document/card |
| Source layer ordering | Q1 → Q2 → Q3; never Q3 before Q1/Q2; never MNN-only first |
| Query shortening | If 0 usable hits: drop manufacturer, then pack, then site: restriction; **never** drop brand in favour of MNN while brand exists |
| Query expansion | If GRLS landing-only or many near-brands: add form+strength if missing; then manufacturer; then pack. Expansion is still Q1/Q2, not P3-as-proof |
| Manufacturer/pack disambiguation | Only when ≥2 candidate product records or near-brand detected |
| When to stop | Tier 1 accepted; or P1/P1 conflict; or identity unusable; or search-query or fetch-page budget exhausted |
| When to unresolved | Ladder done without explicit P1/P2 status; or only P3; or identity C/D |
| When to retry | Transport/429/5xx/transient parse on the **same logical query** (≤2 transport retries); then next template in layer; then next layer. Transport retries do not consume logical query budget. |

Controlled-batch summary **must** report: `logical_search_query_count` (alias `search_query_count`), `transport_retry_attempt_count`, `fetched_page_count`, `budget_exhausted_count`.

Hard rules:

- Do not start with MNN-only query if a trade name exists.
- Brand + form + strength outrank generic name.
- Manufacturer/pack only to resolve ambiguity.
- Every query attempt has `query_kind` and `reason`.
- P3 sources cannot be accepted proof.

Worked examples (strings only, **not searched**) for `3065`, `26115`, `2621`, `18377`, `19198` are in the CSV.

---

## 6. Structured retrieval and validation contract

### Raw record (one per HTTP/search attempt)

```json
{
  "run_id": 0,
  "product_id": 0,
  "attempt_no": 1,
  "query_kind": "grls_primary|official_instruction|support_card",
  "query": "...",
  "source_url": "...",
  "source_type": "...",
  "retrieved_at": "...",
  "http_status": 200,
  "raw_artifact_path": "...",
  "latency_ms": 0
}
```

Raw body lives **only** in append-only artifact (`mnn_rx_otc_retrieval_v1_searxng_raw.jsonl` in M3.2). Not in PostgreSQL.

### Validated evidence (one per candidate URL kept)

```json
{
  "product_id": 0,
  "candidate_rx_otc_value": "rx|otc|null",
  "explicit_status_text": "...",
  "status_pattern": "po_receptu|bez_recepta|other",
  "source_url": "...",
  "source_type": "...",
  "source_tier": "P1|P2|P3",
  "identity_grade": "A|B|C|D|unknown",
  "identity_match": {
    "brand": true,
    "form": true,
    "strength": true,
    "pack": false,
    "manufacturer": false
  },
  "evidence_grade": "A|B|C|D|none",
  "conflict_status": "no_conflict|conflict|unknown",
  "validation_passed": true,
  "reject_reason": null
}
```

`rx_otc_value` on a candidate record, if present, is an alias of `candidate_rx_otc_value` only. It is **not** the product-level final value.

### Product-level result values

```text
candidate_rx_otc_value: rx|otc|null
final_rx_otc_value: rx|otc|null
outcome: accepted|supported_only|unresolved|conflict|rejected|error|not_applicable
```

Policy:

```text
P1 accepted:
candidate_rx_otc_value = rx|otc
final_rx_otc_value = same value
outcome = accepted

P2 supporting:
candidate_rx_otc_value = rx|otc
final_rx_otc_value = null
outcome = supported_only

P3 / no explicit status / identity C-D:
candidate_rx_otc_value may be null
final_rx_otc_value = null
outcome = unresolved or rejected

M2 excluded BAS/Other:
candidate_rx_otc_value = null
final_rx_otc_value = null
outcome = not_applicable
```

P2 never sets `final_rx_otc_value` and cannot be used for hard routing, snapshot update, or attr merge.

### Validation policy (mandatory)

```text
- explicit_status_text must come from captured source content;
- a generated summary is not evidence;
- no explicit status → validation_passed=false;
- source P3 → validation_passed=false;
- identity C/D → validation_passed=false;
- conflicting comparable P1 evidence → validation_passed=false;
- every accepted result stores source URL + status excerpt + identity fields.
```

Explicit-status detection (captured page/title/excerpt only; ignore query-template leakage):

| status_pattern | Positive patterns (Russian) |
|----------------|-----------------------------|
| `po_receptu` | отпускается по рецепту; по рецепту; рецептурный; рецептурный отпуск |
| `bez_recepta` | отпускается без рецепта; без рецепта; безрецептурный; безрецептурный отпуск |
| `other` | any other explicit but non-canonical phrasing → do not auto-map to rx/otc |

If both `po_receptu` and `bez_recepta` appear as a **query template** (`рецептурн* безрецептурн* грлс`) without a dispensing sentence → treat as **no** explicit status.

### Evidence grade

| Grade | Meaning |
|-------|---------|
| A | P1 + identity A + explicit status + product-specific |
| B | P1 + identity B + explicit status, or P1 identity A with brand+form-specific (pack/mfr missing) |
| C | P2 with explicit status + identity A/B (supporting only) |
| D | weak / mismatched / P3 |
| none | no usable candidate |

P2 never receives evidence grade A/B for **acceptance** purposes; its best grade for routing is “supporting / C”.

### Enums, error codes, reject reasons

See contract JSON for the full lists. Summary:

| Code | Meaning | Retryable |
|------|---------|-----------|
| `ok` | attempt completed | n/a |
| `E_TRANSPORT_TIMEOUT` | timeout | yes |
| `E_HTTP_429` | rate limit | yes |
| `E_HTTP_5XX` | upstream 5xx | yes |
| `E_PARSE_TRANSIENT` | HTML/JSON parse blip | yes |
| `E_SOURCE_NOT_FOUND` | layer miss → next layer | layer-advance, not same-query retry |
| `E_NO_EXPLICIT_STATUS` | captured text has no status phrase | no |
| `E_SOURCE_P3` | P3 used as proof | no |
| `E_IDENTITY_C` / `E_IDENTITY_D` | weak / wrong identity | no |
| `E_FORM_MISMATCH` | form conflict | no |
| `E_STRENGTH_MISMATCH` | dose conflict | no |
| `E_NEAR_BRAND` | near-brand / wrong SKU | no |
| `E_P1_CONFLICT` | P1 RX vs P1 OTC | no |
| `E_P2_CONFLICT` | P2 vs P2 contradiction | no |
| `E_LADDER_EXHAUSTED` | no explicit status after Q1–Q3 | no |
| `E_M2_NON_DRUG` | M2 approved BAS/Other | no |
| `E_INPUT_IDENTITY` | malformed/unusable input | no |
| `E_MARKET_MISMATCH` | non-RU registry as sole P1 | no |

Reject reasons (stored on evidence): `no_explicit_status`, `source_p3`, `identity_c`, `identity_d`, `form_mismatch`, `strength_mismatch`, `near_brand`, `p1_conflict`, `p2_conflict`, `regulatory_context_only`, `grls_landing_only`, `generated_summary_not_evidence`, `m2_non_drug`, `malformed_input`, `transport_failure`, `parse_failure`.

---

## 7. Acceptance and conflict matrix

### Tier 1

```text
P1
+ explicit status
+ identity A/B
+ evidence A
+ no P1 conflict
→ accepted tier_1_product_specific
→ candidate_rx_otc_value = rx|otc
→ final_rx_otc_value = same value
→ outcome = accepted
→ audit-only soft signal in M3.2
```

### Tier 2

```text
P2
+ explicit status
+ identity A/B
+ no P1 conflict
→ tier_2_supported_soft_signal
→ candidate_rx_otc_value = rx|otc
→ final_rx_otc_value = null
→ outcome = supported_only
→ audit only; not hard routing; not snapshot/attr merge; not DB merge
```

### Tier 3 / reject

```text
P3
or no explicit status
or identity C/D
or form/strength mismatch
or unresolved/near-brand
or conflict
or transport/parse failure
→ unresolved/rejected
→ no RX hard routing
→ review/retry if needed
```

### Conflict policy

```text
P1 RX vs P1 OTC → manual review.
P1 wins over P2 only when P1 has identity A/B and explicit status.
P2 vs P2 contradiction → unresolved.
Sem baseline vs future P1:
  retain both as provenance;
  no silent overwrite;
  future P1 may only become proposed preferred value after
  controlled validation/human approval.
```

| Case | Outcome | `conflict_status` |
|------|---------|-------------------|
| One valid P1 | `accepted` (M3.2: audit-only) | `no_conflict` |
| P1 RX vs P1 OTC | `conflict` | `conflict` |
| Valid P1 vs P2 opposite | P1 wins; P2 stored as losing provenance | `no_conflict` (P1 preferred) |
| P2 vs P2 opposite, no P1 | `unresolved` | `conflict` |
| Sem `rx` vs future P1 `otc` | keep both; `proposed_rx_otc` only after M3.3+ approval | provenance retained |
| Skip/reuse historical RX vs new retrieval | historical is **not** evidence; new retrieval stands alone | n/a |

M3.2 never writes `attr_rx_otc`. Sem baseline remains the live semantic value.

---

## 8. Retry / failure policy

### Retryable

```text
transport timeout
HTTP 429
HTTP 5xx
transient parser failure
primary source not found → proceed to next source layer
```

### Non-retryable

```text
clear product identity mismatch
P1/P1 conflict
completed source ladder without explicit status
BAS/Other item approved in M2
malformed/unusable input identity
```

### Limits

| Parameter | Value |
|-----------|--------|
| `logical_search_query_count` | **≤ 8** (distinct ladder queries; retries do not increment) |
| `transport_retry_attempt_count` | **≤ 2 per logical query** |
| `fetched_page_count` | **≤ 4** |
| Max attempts per query string | 3 (initial + 2 transport retries) |
| Backoff | 1s, 2s, 4s exponential + jitter ±30% |
| Query-kind progression | Q1 templates in order → Q2 → Q3 |
| Stop conditions | Tier 1 accept; P1/P1 conflict; identity D mismatch; M2 exclude; search-query or fetch-page budget exhausted; non-retryable error |
| Same `run_id` | across all attempts/fallbacks of one product in one batch |

### Future outcomes

```text
accepted          — Tier 1 (audit-only in M3.2); final_rx_otc_value = candidate
supported_only    — Tier 2 only; candidate set; final_rx_otc_value = null
unresolved        — ladder done, no acceptable status; final_rx_otc_value = null
conflict          — P1/P1 or unresolved P2/P2; final_rx_otc_value = null
rejected          — identity mismatch / malformed; final_rx_otc_value = null
error             — transport exhausted without a decision; final_rx_otc_value = null
not_applicable    — M2 BAS/Other gate; candidate and final = null
```

Unresolved is **acceptable and preferable** to an unsupported status.

---

## 9. Future n8n topology (do not create)

```text
Manual Trigger / Webhook
→ Validate Input Contract
→ Build Product Identity
→ M2 Non-drug Exclusion Gate
→ Build Q1 GRLS Query
→ Search / Fetch P1
→ Parse P1
→ Validate P1 Evidence
→ IF Tier 1 accepted
    → Build Audit Result
  ELSE
    → Build Q2 Official Instruction Query
    → Search / Fetch P1 Official
    → Parse + Validate
    → IF Tier 1 accepted
      → Build Audit Result
      ELSE
        → Build Q3 Support Query
        → Search / Fetch P2
        → Parse + Validate
        → Conflict Resolver
        → Build Audit Result
→ Write Audit Artifacts
→ Optional Future Log Payload
→ Finish Run
```

### Global Code-node rules

- Pattern: `return [{ json: { ...item.json, ...newFields }, pairedItem: { item: i } }]`.
- After every external/parser step: parse JSON → validate fields → compute decision → preserve provenance.
- **No Structured Output Parser** as a mandatory mechanism.
- One `run_id` for all M3.2 attempts/fallbacks.
- No snapshot update in M3.2.
- M2 approved BAS/Other gate stops drug-RX/OTC retrieval with audit-only `not_applicable`.
- M3.2a: Search/Fetch nodes are **stubs** (set `http_status=0`, `stubbed=true`, no HTTP).

Proposed zone prefixes (standalone workflow, not Stage 2 clone): `In —`, `Run —`, `Rx —`, `Q1 —`, `Q2 —`, `Q3 —`, `Art —`, `Fin —`.

### Code nodes

#### `Run — Init Constants`

- **Purpose:** attach versions, enums, M2 exclusion set, query budget, isolation flags.
- **Input:** trigger item (`product_id` / `normalized_text_full` or batch list).
- **Output:** `constants`, `workflow_version=rx_otc_retrieval_dev_v1`, `run_id` (M3.2a: client-supplied or ephemeral integer; **no** `classification_runs` insert), `stage=rx_otc_retrieval`, `isolation.snapshot_update=false`.
- **`...item.json`:** yes.
- **Error:** missing constants → fail the item with `E_INPUT_IDENTITY` (non-retryable).

#### `Rx — Validate Input Contract`

- **Purpose:** require `product_id` + usable text; reject empty/non-object.
- **Input:** `product_id`, `normalized_text_full` (or `normalized_text` alias).
- **Output:** `input_validation_passed`, `input_reject_reason`.
- **`...item.json`:** yes.
- **Error:** fail closed → `rejected` / `E_INPUT_IDENTITY`; still emit audit row.

#### `Rx — Build Product Identity`

- **Purpose:** deterministic identity fields (§4).
- **Input:** validated text + optional structured dims.
- **Output:** `rx_otc_identity_*`, `rx_otc_brand_norm`, form/strength/pack/mfr, `identity_build_warnings[]`.
- **`...item.json`:** yes.
- **Error:** unusable identity (`brand` empty and text &lt; 3 chars) → `rejected` / `E_INPUT_IDENTITY`. Does not modify Norm.

#### `Rx — M2 Non-drug Exclusion Gate`

- **Purpose:** stop the 13 applied M2 BAS/Other IDs.
- **Input:** `product_id`, M2 freeze list in constants.
- **Output:** `m2_gate=pass|exclude`, `outcome=not_applicable` when excluded.
- **`...item.json`:** yes.
- **Error:** never throws; exclude is a successful audit outcome.
- **IDs (applied freeze):** `56, 75, 249, 3763, 5322, 8201, 9197, 18179, 18830, 21387, 22548, 23695, 26319`.
- **Not excluded:** `19198` (drug / retain; `review_label_inconsistency=true`), `72`, `45`, `11272`, `9941`.
- `19198` remains eligible for retrieval as Drug + MNN unresolved. Include in Phase A source/identity audit. Exclude from RX/OTC correction precision/error denominator until reviewer sets structured `expected_rx_otc` ∈ {rx, otc, unknown}. Do not rewrite historic labels.

#### `Q1 — Build GRLS Query`

- **Purpose:** emit Q1 template(s) with `query_kind=grls_primary` and reason.
- **Input:** identity fields.
- **Output:** `query_plan[]` (ordered), `current_query`.
- **`...item.json`:** yes.
- **Error:** if brand missing → skip to unresolved (do not MNN-only).

#### `Q1 — Parse P1` / `Q2 — Parse Official` / `Q3 — Parse Support`

- **Purpose:** classify `source_type` / tier; extract title, excerpt, URLs; never treat LLM summary as excerpt.
- **Input:** fetch item (`source_url`, raw pointer, http_status).
- **Output:** candidate list `retrieved_candidates[]` (url, title, excerpt≤500, source_type, source_tier).
- **`...item.json`:** yes.
- **Error:** transient parse → `E_PARSE_TRANSIENT` (retryable). Empty hits → `E_SOURCE_NOT_FOUND` (advance layer).

#### `Rx — Validate P1 Evidence` / `Rx — Validate P2 Evidence`

- **Purpose:** identity grade, explicit status, `validation_passed`.
- **Input:** candidates + identity.
- **Output:** `validated_evidence[]`, `tier1_accepted`, `best_p1`, `reject_reason`.
- **`...item.json`:** yes.
- **Error:** P3 or no status → `validation_passed=false` (not a transport error).

#### `Rx — Conflict Resolver`

- **Purpose:** apply §7 matrix after Q3 (or earlier if two P1 values exist).
- **Input:** all validated evidence + Sem/enrichment provenance (read-only).
- **Output:** `outcome`, `conflict_status`, `selected_evidence` (≤10), `candidate_rx_otc_value`, `final_rx_otc_value`, `proposed_rx_otc` **unset in M3.2**. P2-only → `final_rx_otc_value=null`.
- **`...item.json`:** yes.
- **Error:** P1/P1 → `conflict` (non-retryable).

#### `Art — Build Audit Result`

- **Purpose:** stable result object for webhook + CSV.
- **Input:** identity, query_plan, validated_evidence, outcome.
- **Output:** `audit_result` with `candidate_rx_otc_value`, `final_rx_otc_value`, `outcome`, `logical_search_query_count`, `transport_retry_attempt_count`, `fetched_page_count`, `budget_exhausted` (see contract).
- **`...item.json`:** yes.
- **Error:** always produces a result; missing fields → `error` / `E_INPUT_IDENTITY`.

#### `Art — Write Audit Artifacts`

- **Purpose:** M3.2 append CSV/JSONL under `redesign/artifacts/` (runner-side or Code fs). **No Postgres.**
- **Input:** `audit_result`, raw pointers.
- **Output:** `artifact_paths`.
- **`...item.json`:** yes.
- **Error:** write fail → `error`; do not retry into snapshot.

#### `Log — Optional Future Log Payload`

- **Purpose:** build `product_classification_log_insert` **shape** only. M3.2: do not execute INSERT.
- **Input:** audit_result, run_id, attempt history.
- **Output:** `future_log_payload` (input/output as in data model).
- **`...item.json`:** yes.
- **Error:** omit payload rather than invent `run_id=null`.

#### `Fin — Finish Run`

- **Purpose:** webhook response + counts. No `classification_runs` update in M3.2a/b until approved.
- **Input:** all items.
- **Output:** `{ run_id, outcomes, isolation_confirmation, logical_search_query_count, transport_retry_attempt_count, fetched_page_count, budget_exhausted_count }`.
- **`...item.json`:** yes (`runOnceForAllItems` for finish).
- **Error:** still return isolation flags.

Search/Fetch nodes are **not** Code; in M3.2a they are stub Code `Q* — Fetch Stub` returning empty hits. Live fetch (M3.2b+) applies only to URLs that passed source/domain filter; P3 landing/search pages are not fetched/accepted as SKU evidence unless they lead to a concrete P1 document/card. Fetch quota is `max_fetched_candidate_pages_per_eligible_sku=4`, separate from the 8 search-query cap.

---

## 10. Self-check (design assertions)

This design **explicitly** asserts:

```text
- GRLS product record / official instruction = P1 primary.
- Приказ Минздрава №100н = regulatory context only, not SKU evidence.
- generic MNN / snippets / GRLS landing = P3 discovery only.
- no automatic acceptance without explicit captured status text.
- no hard routing or attr merge in M3.2.
- M2 approved BAS/Other 13 products excluded from M3.2.
- workflow independent from MNN route.
- one run_id across all future stages.
- no full raw evidence in PostgreSQL.
- no silent overwrite of Sem baseline by retriever.
- workflow will be standalone and inactive after future creation.
- M3.2a skeleton first; one-item test before controlled batch.
```

---

## 11. Confirmation (this task)

```text
design only;
no web/LLM/DB/n8n workflow actions;
no attr/snapshot/product_kind/prod/Sem changes;
no git commit/push.
```

Created files:

- `redesign/m3_1_rx_otc_retriever_design.md` (this file)
- `redesign/m3_1_rx_otc_retriever_contract.json`
- `redesign/m3_1_rx_otc_retriever_query_examples.csv`
- `redesign/m3_1_rx_otc_retriever_data_model.md`
- `redesign/m3_1_rx_otc_retriever_m3_2_test_plan.md`
