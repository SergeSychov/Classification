# Hierarchy redesign — short roadmap

Updated: 2026-07-21  
Status board: [`00_PROJECT_STATUS.md`](00_PROJECT_STATUS.md)  
Migration design: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md)  
Journal pointer: [`../Categories/stage2_workflow_plan.md`](../Categories/stage2_workflow_plan.md) (section *Hierarchy redesign progress*)

## Current baseline (done)

| Item | Note |
|------|------|
| §13 | Cleared (`21a` / `21b` / `21` / `22`) |
| B1 | Applied in **dev** (`24_B1_APPLY_REPORT.md`) |
| B2 | Skeleton + empty smokes (`26_B2_EXECUTION_REPORT.md`) |
| B3 Norm | Code-only in hierarchy-dev (`28_B3_NORM_PLAN.md`); Product on live path; Dict unwired until B4/Dir |
| B3 Sem | Log-only `semantic_primary` in hierarchy-dev (`stage2_workflow_plan.md` п.26); Limit→Sem→Insert Log; no snapshot; Dir not wired |
| Hierarchy workflow | `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`) |
| Workflow status | **Active but safe (0 rows)** — Load = `WHERE false`; empty Fin intact; Sem wired but not executed without rows |
| Prod Stage 2 | Unchanged |
| Kill switch | `hierarchy_experiment_enabled=false`; allowlist empty |

Naming: **B3 = Norm + Sem** (both done in git; Sem smoke/validation pending).

---

## Roadmap

| Step | Description | Gate | Checks | Artifacts |
|------|-------------|------|--------|-----------|
| **0** | Status quo / ops safety | — | Prod Stage 2 untouched; hierarchy Load returns 0; workflow **active but safe** | `00_PROJECT_STATUS`, `26_B2_EXECUTION_REPORT` |
| **1a** | **B3 Norm** (Code-only) | Explicit ask | Product + Dict Code nodes; no SQL/LLM; Load stub intact | `28_B3_NORM_PLAN` + hierarchy WF |
| **1b** | **B3 Sem** `semantic_primary` | Explicit ask | no `category_id`; log `semantic_primary`; terminal-only; Load=0 → `finished_empty` | journal п.26 + Sem nodes |
| **2** | Sem validation wave **100** | B3 smoke green | Allowlist filled; rubric on attrs | Sheets/export + allowlist |
| **3** | Sem validation **500 / 1000** | Wave-100 gate pass | Metrics non-worse | Wave reports |
| **4** | Dir + Need soft-to-hard | Sem V3 gate | Membership / `soft_override` | Cascade smoke notes |
| **5** | Cat hard + optional Mnn | Dir/Need smoke | Hard category shortlist; Mnn skip-empty OK | Cascade smoke notes |
| **6** | Judge + Sheets human path | Cat/Mnn smoke | Dispute → judge / review | Hierarchy judge note |
| **7** | Optional prod Load exclude | Hierarchy cascade stable | Stage 2 Load excludes allowlist | Isolation apply note |

---

## Explicitly later / not planned yet

- Telegram HITL beyond Sheets for hierarchy — **not started**
- Dedicated hierarchy **error-handling** track — **not planned in detail**
- Normalized hierarchy ID tables — post-v1

---

## Next action

Optional **gated Sem smoke** / Sem validation waves — start only on explicit request. Keep Load stub / allowlist discipline until then. **Dir+** after V3 gate.
