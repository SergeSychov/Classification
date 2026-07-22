# Project status — classification redesign

Updated: 2026-07-21  
Canonical migration design: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md)

## Architecture decision status

**Hierarchy migration plan v1 is approved** (architecture decisions locked).  
**§13 clearance is complete** (read-only schema + mapping + isolation design).  
**B1 applied (dev):** additive columns + `hierarchy_*` settings seed — see [`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md).  
**B2 skeleton clone done:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`); Manual run **297** + webhook run **298** / n8n exec **7768** → `finished_empty`. Workflow status: **active but safe (0 rows / no LLM path)** — active only for webhook registration/testing; Load stubbed (`WHERE false`); P1/2A/2B/Judge unreachable.  
**B3 Norm (Code-only) done** in hierarchy-dev: `Norm — Normalize Product` on live path; `Norm — Normalize Dict` on canvas unwired (B4/Dir).  
**B3 Sem (log-only) done** in hierarchy-dev git: Limit → Sem zone → `Sem — Prepare Log` → Insert Log (no snapshot); `Sem — Route` seam for B4; Load still `WHERE false`. Dir/Need/Cat/Mnn not implemented; `hierarchy_experiment_enabled` remains `false`.

| Track | Status |
|-------|--------|
| Current Stage 2 (`classification-stage2-dev`) | Implemented (production-like working pipeline) — **unchanged** |
| Hierarchy cascade redesign | **§13 cleared**; **B1–B2 done**; **B3 Norm done**; **B3 Sem done (git, log-only)**; Dir+ pending validation |
| Sem validation 100/500/1000 | Not started (gates Dir+) |
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
- Sem validation 100/500/1000 not started; gated Sem smoke 10 optional
- Prod Stage 2 Load SQL not patched; experiment kill switch remains off; hierarchy Load still stubbed (no pending drain)
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

---

## Next gate

Short roadmap: [`29_SHORT_ROADMAP.md`](29_SHORT_ROADMAP.md).

**Next:** optional gated Sem smoke / Sem validation waves — only on **explicit request**.  
Keep Load stub / allowlist discipline until then.  
**Dir+** remains gated by Sem user validation 100→500→1000.
