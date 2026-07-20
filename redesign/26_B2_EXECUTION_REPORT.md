# B2 Execution report — `classification-stage2-hierarchy-dev`

**Status:** **complete** (skeleton + Manual dry-run + webhook smoke)  
**Date/time (clone):** 2026-07-20 ~22:40 (UTC+3) / `2026-07-20T19:40:02.898Z`  
**Date/time (Manual dry-run):** 2026-07-20 ~22:44 (UTC+3) — run **`297`** `finished_empty`  
**Date/time (webhook smoke):** 2026-07-20 ~22:48 (UTC+3) — run **`298`**, execution **`7768`** `finished_empty`  
**Operator:** Cursor agent + user Manual confirm  
**Sources:** [`25_B2_WORKFLOW_PLAN.md`](25_B2_WORKFLOW_PLAN.md), [`27_B2_EXECUTION_RUNBOOK.md`](27_B2_EXECUTION_RUNBOOK.md)

---

## 0. Environment confirmation

| Param | Value | Confirmed |
|-------|-------|-----------|
| n8n URL | `https://n8n.sychovtest.ru` | ✅ |
| Source | `classification-stage2-dev` / `BaBjEPi78taRj2G5` | ✅ unchanged |
| Hierarchy | `classification-stage2-hierarchy-dev` / `o8sugljHYuUs7IEC` | ✅ |
| Credentials | Postgres / DeepSeek / Polza (same ids) | ✅ |

---

## 1. Clone summary

| Field | Value |
|-------|-------|
| Method | API `POST /api/v1/workflows` (Duplicate-equivalent) |
| New id | `o8sugljHYuUs7IEC` |
| Local files | `workflows/classification-stage2-hierarchy-dev.json` + `.id` |
| Source `updatedAt` | `2026-07-19T19:50:02.799Z` (unchanged through clone + webhook add) |

---

## 2. Triggers & zones

| Item | Status |
|------|--------|
| Cron | absent |
| `In — Manual` | kept |
| `In — Webhook` | **added after Manual dry-run** (user authorized agent webhook tests); path `classification-stage2-hierarchy-dev` |
| `In — Webhook Start` | added; passes `batch_size` |
| Workflow active | **`true`** (required for webhook registration; Load still stubbed → 0 rows) |
| P1 / 2A / 2B / Judge | on canvas, **unreachable** from In path |
| Load | stub `WHERE false` |
| Empty Fin | `Shell — Ensure Empty Fin` → `Fin — Close Run` |

**Live path:**

```text
In — Manual | In — Webhook → Webhook Start
  → Run — Create Run → Run — Init Constants
       ├─ Load — Select Batch (0) → Attach → Limit
       └─ Shell — Ensure Empty Fin → Fin — Close Run
```

**Webhook URL:** `POST https://n8n.sychovtest.ru/webhook/classification-stage2-hierarchy-dev`  
Body example: `{"batch_size": 5}`

---

## 3. Meta applied

| Field | Value |
|-------|-------|
| `run_type` | `stage2_hierarchy_v1` |
| `workflow_name` | `classification-stage2-hierarchy-dev` |
| `workflow_version` | `stage2_hierarchy_v1` |
| `prompt_version` | `prompt_hierarchy_skeleton_v0` |
| Init stages / thresholds | hierarchy contract |

---

## 4. Safety confirmations

| Check | Result |
|-------|--------|
| Prod Stage 2 untouched | ✅ |
| Load does not drain pending | ✅ stub |
| LLM not executed on smokes | ✅ (exec 7768: no P1/DeepSeek) |
| Kill switch / allowlist | not flipped (`enabled` expected false) |

---

## 5. Dry-run / smoke results

### 5.1 Manual (user)

| Field | Value |
|-------|-------|
| `classification_runs.id` | **297** |
| `run_type` | `stage2_hierarchy_v1` |
| `status` | **`finished_empty`** |
| `success_count` / `error_count` | 0 / 0 |
| `metadata` | `trigger=manual`, `skeleton=b2`, `total_count=0` |
| `started_at` → `finished_at` | `2026-07-20T19:44:45.531Z` → `…45.607Z` |

### 5.2 Webhook (agent)

| Field | Value |
|-------|-------|
| n8n execution | **7768** (`mode=webhook`, `status=success`) |
| `classification_runs.id` | **298** |
| `status` | **`finished_empty`** |
| Nodes run | Webhook → Start → Create Run → Init → Load → Ensure Empty Fin → Close Run |
| LLM nodes | not run |

---

## 6. Out of scope (still not done)

- Sem/Dir/Need/Cat/Mnn LLM (B3+)
- Flip `hierarchy_experiment_enabled` / fill allowlist
- Prod Stage 2 Load exclude patch
- Sem validation 100/500/1000

---

## 7. Sign-off

| Role | Name | Date |
|------|------|------|
| Clone + webhook setup | Cursor agent | 2026-07-20 |
| Manual dry-run confirm | User (run 297) | 2026-07-20 |

**B2 closed.** Next: B3 (Norm + Sem) on explicit request.
