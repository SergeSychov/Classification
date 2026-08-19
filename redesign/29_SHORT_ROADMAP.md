# Hierarchy redesign — short roadmap

Updated: 2026-08-19
Status board: [`00_PROJECT_STATUS.md`](00_PROJECT_STATUS.md)  
Migration design: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md)  
Journal pointer: [`../Categories/stage2_workflow_plan.md`](../Categories/stage2_workflow_plan.md) (section *Hierarchy redesign progress*; Wave-100 gate = п.28; offline MNN baseline = **п.38**; BAS/Other override = **п.39**; RX/OTC retriever design = **п.40**; M3.2a skeleton = **п.41**; M3.2a runtime smoke = **п.42**; M3.2b one-item live = **п.43**; M3 closeout = **п.44**)

## Current baseline (done)

| Item | Note |
|------|------|
| §13 | Cleared (`21a` / `21b` / `21` / `22`) |
| B1 | Applied in **dev** (`24_B1_APPLY_REPORT.md`) |
| B2 | Skeleton + empty smokes (`26_B2_EXECUTION_REPORT.md`) |
| B3 Norm | Code-only in hierarchy-dev (`28_B3_NORM_PLAN.md`); Product on live path; Dict unwired until B4/Dir |
| B3 Sem | Log-only `semantic_primary` in hierarchy-dev (`stage2_workflow_plan.md` п.26); Limit→**Sem0→Sem1→Norm attrs**→Insert Log; no snapshot; Dir not wired |
| Sem0 gate | `product_kind`/`attr_profile` before Sem1 (`п.29`–`п.30`); `prompt_sem0_v2` + `prompt_semantic_v3` |
| Sem attr Norm | Fixed dictionaries for route/form/age (`п.31`); smoke exec **29035** |
| Sem smoke S0/S1/S2 | Done (`stage2_workflow_plan.md` п.27); reversible allowlist; rollback to safe default verified |
| Hierarchy workflow | `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`) |
| Workflow status | **Active but safe (0 rows)** — Load = `WHERE false`; empty Fin intact; Sem wired but not executed without rows |
| Prod Stage 2 | Unchanged |
| Kill switch | `hierarchy_experiment_enabled=false`; allowlist empty |

Naming: **B3 = Norm + Sem** (done; Sem smoke green → Wave-100 gate open).

---

## Roadmap

| Step | Description | Gate | Checks | Artifacts |
|------|-------------|------|--------|-----------|
| **0** | Status quo / ops safety | — | Prod Stage 2 untouched; hierarchy Load returns 0; workflow **active but safe** | `00_PROJECT_STATUS`, `26_B2_EXECUTION_REPORT` |
| **1a** | **B3 Norm** (Code-only) | Explicit ask | Product + Dict Code nodes; no SQL/LLM; Load stub intact | `28_B3_NORM_PLAN` + hierarchy WF |
| **1b** | **B3 Sem** `semantic_primary` | Explicit ask | no `category_id`; log `semantic_primary`; terminal-only; Load=0 → `finished_empty` | journal п.26 + Sem nodes |
| **1c** | Sem smoke S0/S1/S2 | Explicit ask | allowlist reversible; offline+live soft-continue; rollback safe | journal п.27 + `redesign/artifacts/sem_smoke_*` |
| **2** | Sem validation wave **100** (first **LLM-on**, **snapshot-off**; gate on semantic attrs, not category) | Wave-100 executed; gate def journal п.28; `critical_error_rate` awaiting human rubric labels | Allowlist N=100; rubric on attrs; compute `critical_error_rate < 15%` on `mnn` / `dosage_form` / `administration_route` | `sem_wave100_*` export + allowlist |
| **3** | Sem validation **500 / 1000** | Wave-100 gate pass | Metrics non-worse | Wave reports |
| **4** | Dir + Need soft-to-hard | Sem V3 gate | Membership / `soft_override` | Cascade smoke notes |
| **5** | Cat hard + optional Mnn | Dir/Need smoke | Hard category shortlist; Mnn skip-empty OK | Cascade smoke notes |
| **6** | Judge + Sheets human path | Cat/Mnn smoke | Dispute → judge / review | Hierarchy judge note |
| **7** | Optional prod Load exclude | Hierarchy cascade stable | Stage 2 Load excludes allowlist | Isolation apply note |

### Offline MNN track (parallel; not live Sem)

| Step | Description | Gate | Checks | Artifacts |
|------|-------------|------|--------|-----------|
| **M1** | Catalog identity gate Wave‑500 v3 + enrichment run **461** + human-review v2 quality baseline | **done** (2026-08-17) | MNN drugish **82/83**; null-MNN non-drug **17**; RX **72/83**; Age **59/83**; no `attr_*` / snapshot writes; product-kind from enrichment = **proposed/offline only** | journal **п.38**; `mnn_identity_enrichment_pass_review_metrics_v1.*` |
| **M2** | Offline BAS/Other override policy v1 + human validation (M2.1) | **done** (2026-08-17) | Input 18 null-MNN/non-drug candidates (run 461); applied offline: BAS **12**, Other **1** (`9197`), no proposal **5**; **13** approved for future drug-MNN queue exclusion; MNN null/N/A; no DB/`product_kind`/`attr_*`/snapshot/Sem writes; contract draft **not applied** | journal **п.39**; `mnn_non_drug_override_policy_v1_reviewed.*` |
| **M3.0** | Offline RX/OTC source audit of 11 error rows | **done** (2026-08-18) | 0/11 sufficient product-specific evidence; 0 GRLS product-card; Приказ №100н = regulatory context only | `mnn_rx_otc_source_audit_v1_summary.*` |
| **M3.1** | Standalone RX/OTC Product Retrieval workflow design | **done** (2026-08-18) | Design for future inactive workflow `rx-otc-product-retrieval-dev`; not a sub-branch of MNN enrichment / Stage 2 / hierarchy; P1 GRLS/official vs P2 supporting vs P3 discovery; P2 never sets `final_rx_otc_value`; no n8n/DB/`attr_*` at design time | journal **п.40**; [`m3_1_rx_otc_retriever_design.md`](m3_1_rx_otc_retriever_design.md) |
| **M3.2a** | Inactive skeleton `rx-otc-product-retrieval-dev` + n8n runtime smoke | **done** (2026-08-18) | Created inactive (`UqssZ24Jr7Qk9ef4`); stubs; no HTTP/LLM/Postgres; CLI smokes **42679/42680/42681** pass; left inactive | journal **п.41** / **п.42**; `workflows/rx-otc-product-retrieval-dev.json`; `rx_otc_retrieval_m3_2a_*` |
| **M3.2b** | One-item live retrieval + P2 support test + contract v2 | **done / paused** (2026-08-18) | SKU `3065`; runner-side SearXNG+fetch; n8n inactive; `supported_only` / candidate `otc` / `final=null`; contract v2: discovery/fetched/validated separated | journal **п.43**; `mnn_rx_otc_retrieval_m3_2b_*` |
| **M3.2b.3–5** | P1 feasibility (SearXNG/Bing, direct GRLS, MAH instructions) | **done / paused** (2026-08-19) | SearXNG/Bing **0 valid P1/5**; direct GRLS **0 valid P1/10** (TLS/WAF/login; no bypass); MAH **2 valid P1b/10** (Termikon form-specific only). Decision: **`KEEP_RX_OTC_P2_SUPPORT_ONLY`** | journal **п.44**; `mnn_rx_otc_investigation_synthesis_v1.md` |
| **M3.2c+** | 11 errors + 30 blind; human metrics | **blocked / not scheduled** | No stable mass P1 route. Re-entry only if public GRLS without login/WAF, or approved MAH registry with coverage, or a new user-approved P2 soft-signal experiment. Do **not** proceed automatically to Phase A 11+30 | — |
| **M4** | Age contract + evidence policy | **next active offline task** (after M3 closeout) | Offline/audit-only; not used in routing until controlled review | `*_age_errors_v1.csv` |
| **M5** | Norm v4 experiment (mfr/pack dedupe) | After M4 | Offline only; no production Norm rewrite | `*_text_quality_v1.csv` |

---

## Explicitly later / not planned yet

- Telegram HITL beyond Sheets for hierarchy — **not started**
- Dedicated hierarchy **error-handling** track — **not planned in detail**
- Normalized hierarchy ID tables — post-v1
- Merge offline MNN / RX / Age into live Sem `attr_*` — **blocked** until explicit approval (п.38)

---

## Next action

1. **M4** Age contract + evidence policy — next active offline task. Audit-only; not used in routing until controlled review. Do not activate `rx-otc-product-retrieval-dev`. Still no snapshot / `attr_*`.
2. Parallel Sem track: human rubric labeling for Wave-100/500 → `critical_error_rate`. Keep hierarchy in safe default. **Dir+** after Sem V3 gate + explicit MNN merge approval.
3. Optional later: apply M2 queue-exclusion contract for 13 IDs — only with explicit approval.
4. M3.2c / RX P1 re-entry — only if journal **п.44** re-entry criteria are met. Policy remains **`KEEP_RX_OTC_P2_SUPPORT_ONLY`**.
