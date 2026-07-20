# Project status — classification redesign

Updated: 2026-07-20  
Canonical migration design: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md)

## Architecture decision status

**Hierarchy migration plan v1 is approved** (architecture decisions locked).  
**§13 clearance is complete** (read-only schema + mapping + isolation design).  
**Not implemented:** no hierarchy workflow clone, no cascade SQL ALTER applied, no Sem/Dir/Need/Cat/Mnn nodes shipped under this plan.

| Track | Status |
|-------|--------|
| Current Stage 2 (`classification-stage2-dev`) | Implemented (production-like working pipeline) |
| Hierarchy cascade redesign | Approved design; **§13 cleared** — B1/B2 *unblocked*, not started |
| Sem validation 100/500/1000 | Not started (gates Dir+ / B5+) |

---

## §13 clearance artifacts

| Item | Artifact | Result |
|------|----------|--------|
| Schema dump + CHECK/INDEX | [`21a_SCHEMA_DUMP.md`](21a_SCHEMA_DUMP.md) | No CHECK on `stage`/`decision_status`; UNIQUE `(product_id, stage)` present; no semantic/cascade columns yet |
| Mapping stats + verdicts | [`21b_MAPPING_STATS.md`](21b_MAPPING_STATS.md) | need=`need_nosology`, mnn=`mnn_cluster` — **Confirmed with caveats** |
| Dirty/ambiguous samples | [`21_HIERARCHY_MAPPING_SAMPLES.md`](21_HIERARCHY_MAPPING_SAMPLES.md) | ≥20 examples |
| Experiment isolation design | [`22_EXPERIMENT_ISOLATION.md`](22_EXPERIMENT_ISOLATION.md) | Allowlist mode; keys frozen; no DB INSERT yet |

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
| Experiment isolation | **Allowlist** via `pipeline_settings` (design in [`22_EXPERIMENT_ISOLATION.md`](22_EXPERIMENT_ISOLATION.md); keys not inserted yet) |
| Implementation gate | **§13 cleared** — B1 (additive SQL) / B2 (clone skeleton) may start on explicit request only |

### Explicitly not claimed

- Hierarchy workflow does not exist in n8n yet
- Additive cascade/semantic columns are designed, **not applied**
- Sem validation 100/500/1000 not started
- `pipeline_settings` hierarchy keys not inserted; prod Load SQL not patched

---

## Next gate

**B1 / B2** may start only after an explicit implementation request (still no silent start).  
**B5+** (Dir+ cascade) remains gated by Sem user validation 100→500→1000 after Norm+Sem exist.
