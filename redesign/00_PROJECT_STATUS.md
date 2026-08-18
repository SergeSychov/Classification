# Project status — classification redesign

Updated: 2026-08-18
Canonical migration design: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md)

## Architecture decision status

**Hierarchy migration plan v1 is approved** (architecture decisions locked).  
**§13 clearance is complete** (read-only schema + mapping + isolation design).  
**B1 applied (dev):** additive columns + `hierarchy_*` settings seed — see [`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md).  
**B2 skeleton clone done:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`); Manual run **297** + webhook run **298** / n8n exec **7768** → `finished_empty`. Workflow status: **active but safe (0 rows / no LLM path)** — active only for webhook registration/testing; Load stubbed (`WHERE false`); P1/2A/2B/Judge unreachable.  
**B3 Norm (Code-only) done** in hierarchy-dev: `Norm — Normalize Product` on live path; `Norm — Normalize Dict` on canvas unwired (B4/Dir).  
**B3 Sem (log-only) done** in hierarchy-dev: Limit → Sem zone → `Sem — Prepare Log` → Insert Log (no snapshot); `Sem — Route` seam for B4.  
**Sem smoke S0/S1/S2 done** (2026-07-22): reversible allowlist; rollback to `WHERE false` / kill switch off / empty allowlist verified. Dir/Need/Cat/Mnn not implemented; `hierarchy_experiment_enabled` remains `false`.

**Sem0 + Sem1 attr_profile policy v2 done** (2026-07-30): `prompt_sem0_v2` / `prompt_semantic_v3`; Wave-100 rerun chunked 10×10 (execs 21611…21659); progress tooling; snapshot-off; prod untouched; safe default restored. Journal п.30.

**Norm Sem attrs done** (2026-08-04): `Norm — Normalize Sem attrs` after Sem1 Post-process; fixed dictionaries for route/form/age; smoke exec **29035** (N=15); journal п.31.

**Offline MNN identity gate + enrichment quality baseline done** (2026-08-17): Wave‑500 v3 identity gate; enrichment **run_id=461** (104 calls / 86 accepted / 18 unresolved); human-review v2 N=100; MNN drugish **82/83**, null-MNN non-drug **17**, RX **72/83**, Age **59/83**. **Not** merged to `attr_*` / live Sem. Product-kind from enrichment = **proposed/offline only** (no snapshot `product_type`/`product_kind` change). Journal **п.38**.

**Offline BAS/Other override policy v1 + human validation done** (2026-08-17, M2/M2.1): 18 null-MNN/non-drug candidates from run 461; applied offline proposals BAS **12**, Other **1** (`9197`), no proposal **5** (`72`, `11272`, `45`, `19198`, `9941`); **13** approved for exclusion from future drug-MNN enrichment/human queue (MNN null/not_applicable). Remains **offline/audit-only** — no PostgreSQL writes, no classification run, no `product_kind`/`product_type`/snapshot/Sem/`attr_*` updates. Implementation contract draft **not applied**. Journal **п.39**; freeze `mnn_non_drug_override_policy_v1_reviewed.*`.

**M3.0 RX/OTC source audit + M3.1 standalone retriever design done** (2026-08-18): M3.0 confirmed 11 RX/OTC error rows, **0/11** product-specific sufficient evidence, **0** GRLS product-card evidence. M3.1 locked RX/OTC as a **separate standalone workflow design** for future inactive workflow `rx-otc-product-retrieval-dev` (not a sub-branch of `mnn-drug-enrichment`, not wired to Stage 2 / hierarchy). P1 GRLS/official vs P2 supporting-only (`final_rx_otc_value` stays null) vs P3 discovery; M2-13 excluded from retrieval; **19198** stays Drug / out of precision denom until `expected_rx_otc_manual`. Canon: [`m3_1_rx_otc_retriever_design.md`](m3_1_rx_otc_retriever_design.md). Journal **п.40**.

**M3.2a skeleton created, inactive** (2026-08-18): workflow `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`), `workflow_version=rx_otc_retrieval_dev_v1`, **active=false**. Stubs only — no HTTP / LLM / Postgres. Structural verification of export passed (32 nodes, required topology, no forbidden connectors). **Runtime smoke pending** due n8n 2.27 task-runner limitation (`n8n execute` broker timeout; Public API has no `/run`; production webhook 404 while inactive). Local Code-node replay of export: A/B/C pass. Journal **п.41**.

**Next planned step (MNN offline):** M3.2a **n8n runtime smoke** (blocked by task runner). Do **not** start M3.2b live retrieval until a live execute path exists. Not a hard routing gate.
**Parallel Sem:** Wave-100/500 rubric → `critical_error_rate` (п.28). Hierarchy remains snapshot-off / prod untouched.

| Track | Status |
|-------|--------|
| Current Stage 2 (`classification-stage2-dev`) | Implemented (production-like working pipeline) — **unchanged** |
| Hierarchy cascade redesign | **§13 cleared**; **B1–B2 done**; **B3 Norm+Sem done**; **Sem smoke green**; Dir+ pending Wave-100+ |
| Sem validation 100/500/1000 | Wave-100 **executed** (exec 19932); gate awaiting human rubric labeling for `critical_error_rate` |
| Short roadmap | [`29_SHORT_ROADMAP.md`](29_SHORT_ROADMAP.md) |

---

## §13 clearance artifacts

| Item | Artifact | Result |
|------|----------|--------|
| Schema dump + CHECK/INDEX | [`21a_SCHEMA_DUMP.md`](21a_SCHEMA_DUMP.md) | Pre-B1 baseline: no CHECK on `stage`/`decision_status`; UNIQUE `(product_id, stage)` present |
| Mapping stats + verdicts | [`21b_MAPPING_STATS.md`](21b_MAPPING_STATS.md) | need=`need_nosology`, mnn=`mnn_cluster` — **Confirmed with caveats** |
| Dirty/ambiguous samples | [`21_HIERARCHY_MAPPING_SAMPLES.md`](21_HIERARCHY_MAPPING_SAMPLES.md) | ≥20 examples |
| Experiment isolation design | [`22_EXPERIMENT_ISOLATION.md`](22_EXPERIMENT_ISOLATION.md) | Allowlist mode; keys frozen in design |
| B1 additive apply (dev) | [`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md) | 18 columns + 4 `hierarchy_*` keys; enabled=false |
| B2 hierarchy skeleton clone | [`26_B2_EXECUTION_REPORT.md`](26_B2_EXECUTION_REPORT.md) | `o8sugljHYuUs7IEC`; **active but safe**; Load=0 stub; runs 297/298 |
| Short roadmap | [`29_SHORT_ROADMAP.md`](29_SHORT_ROADMAP.md) | B3 Norm done → Sem → validation → cascade |
| B3 Norm plan | [`28_B3_NORM_PLAN.md`](28_B3_NORM_PLAN.md) | Dict/product `norm_*` + dirty flags |

---

## Already implemented (current Stage 2)

Do not treat these as hierarchy-cascade deliverables.

- Orchestration: n8n + PostgreSQL; scripts pull/push workflow
- Stage 1 rule shortlist → `classification_shortlist` (`primary_rules`)
- Stage 2 workflow: primary LLM → fallback 2A → fallback 2B → judge
- Run entity: `classification_runs`, one `run_id` per run
- Snapshot: `product_classification.latest_run_id`
- Event log: `product_classification_log.run_id`
- Code pattern: `...item.json` + post-process after each LLM stage
- Versions pattern: `workflow_version` / `prompt_version` (stage-level; P1 historically incomplete)
- Human ops path in use: Sheets batch acceptance
- Telegram HITL workflows: present in repo, inactive

Known architectural weakness of current Stage 2: early final `category_id` in primary LLM / shortlist-first.

---

## Approved but not implemented (hierarchy migration design v1)

Source of truth: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md).

Target (design only): clone `classification-stage2-hierarchy-dev` with  
Norm → semantic_primary → direction → need → category → optional mnn → judge → human_review.

### Locked decisions (v1)

| Decision | Locked value |
|----------|--------------|
| Migration style | **Workflow clone only** — do not modify prod `classification-stage2-dev` |
| Hierarchy mapping | Via **`categories_dict` text axes** — live-confirmed: direction / **need_nosology** / id / **mnn_cluster** (with caveats in samples) |
| Intermediate `decision_status` | Historical **`pending_fallback`** (= pending next hierarchy stage); precise hop in `next_action` |
| Snapshot policy | **Terminal-only**; log after every stage |
| Human review v1 | **Sheets batch acceptance** primary; **Telegram inactive** until a later stage |
| Experiment isolation | **Allowlist** via `pipeline_settings` — keys **seeded in dev** ([`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md)); `hierarchy_experiment_enabled=false` |
| Implementation gate | **§13 cleared**; **B1 done (dev)**; **B2 skeleton done** ([`26_B2_EXECUTION_REPORT.md`](26_B2_EXECUTION_REPORT.md)) |

### Explicitly not claimed

- Hierarchy cascade **Dir / Need / Cat / Mnn / Judge** LLM stages not implemented
- Sem validation 500/1000 not started (Wave-100 executed; gate evaluation awaits human rubric labels for `critical_error_rate`)
- Prod Stage 2 Load SQL not patched; experiment kill switch remains off; hierarchy Load stubbed (`WHERE false`)
- Telegram/HITL beyond Sheets for hierarchy — not started
- Dedicated hierarchy error-handling track — not planned in detail yet

### B1 apply (dev) — 2026-07-20

- Script: `sql/2026-07-20_stage2_hierarchy_additive.sql` via pgAdmin → `COMMIT` in 506 msec
- Report: [`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md)
- 18 columns on `product_classification`; 4 `hierarchy_*` keys in `pipeline_settings`
- No CHECK on `stage`/`decision_status`; PK/FK set unchanged

### B2 skeleton clone — 2026-07-20

- Workflow: `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`)
- Report: [`26_B2_EXECUTION_REPORT.md`](26_B2_EXECUTION_REPORT.md)
- Manual run **297** + webhook run **298** / n8n exec **7768** → `finished_empty`
- Workflow status: **active but safe (0 rows / no LLM path)** — webhook path `POST /webhook/classification-stage2-hierarchy-dev`; Load stub `WHERE false`
- P1/2A/2B/Judge unreachable; prod Stage 2 unchanged

### B3 Sem (log-only) — 2026-07-22

- Sources: `scripts/hierarchy_nodes/sem_*.js`; patcher `scripts/_b3_patch_sem.js`
- Live: Limit → Sem zone → Prepare Log → Insert Log → Fin Barrier (no Upsert Snapshot)
- `Sem — Route` future-safe; v1 both outs → Prepare Log (`next_action=direction_select`)
- Load stub / Dict Norm unwired / empty Fin unchanged; prod Stage 2 unchanged
- Journal: `Categories/stage2_workflow_plan.md` п.26

### Sem smoke S0/S1/S2 — 2026-07-22

- Reversible allowlist Load + kill switch; offline fixtures + live inject; full rollback to safe default
- S0 exec 9880 / run 299; S1 exec 9929 / run 300 (N=15); S2 live exec 9935 / run 302
- Artifacts: `redesign/artifacts/sem_smoke_*`; journal п.27
- Wave-100 executed (exec 19932): LLM-on, snapshot-off, prod untouched; export ready; rollback verified.

---

## Next gate

Short roadmap: [`29_SHORT_ROADMAP.md`](29_SHORT_ROADMAP.md).

**Next:** Human rubric labeling for **Wave-100** (compute `critical_error_rate` from `label_*` columns and decide Gate for Wave-500/1000). Until gate computed, hierarchy workflow stays in safe default.  
Gate: journal п.28 (`critical_error_rate < 15%` on `mnn` / `dosage_form` / `administration_route`; Sem contract; rollback).  
**Dir+** remains gated by Sem user validation 100→500→1000.
