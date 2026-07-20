# B2 Execution runbook — clone `classification-stage2-hierarchy-dev`

Date: 2026-07-20  
Status: **runbook for ops** — do not execute until environment row below is confirmed  
Companion report template: [`26_B2_EXECUTION_REPORT.md`](26_B2_EXECUTION_REPORT.md)  
Design: [`25_B2_WORKFLOW_PLAN.md`](25_B2_WORKFLOW_PLAN.md)

---

## A. Confirm with operator before any write

Reply with yes/corrected values:

| # | Question | Assumed |
|---|----------|---------|
| A1 | n8n instance URL | `https://n8n.sychovtest.ru` |
| A2 | Source workflow **name** | `classification-stage2-dev` |
| A3 | Source workflow **id** | `BaBjEPi78taRj2G5` (from `workflows/classification-stage2-dev.id`) |
| A4 | Is source currently **Active**? | (check UI; do not change) |
| A5 | Credentials still named | Postgres `Postgres account`, DeepSeek `DeepSeek account`, Polza `Polza account` |
| A6 | Clone method preference | **UI Duplicate** (safest) vs export/import vs API create |
| A7 | May we Manual-execute empty dry-run after clone? | yes/no (no LLM if Load=0) |

**Stop** if A2/A3 do not match live n8n.

---

## B. Hard constraints (restate)

1. Never edit / push / save `classification-stage2-dev`.
2. New workflow stays **Inactive**.
3. No Cron; remove or leave Webhook **unusable** (prefer delete Webhook nodes).
4. Do not patch prod Load SQL in the source workflow or in DB.
5. Do not implement Sem/Dir/Need/Cat/Mnn prompts (B3+).
6. Load must return **0 rows** with current settings (`hierarchy_experiment_enabled=false`, empty allowlist) **or** use stub `WHERE false`.

---

## C. Preferred method: UI Duplicate (recommended)

### C1. Capture baseline (source untouched)

1. Open `https://n8n.sychovtest.ru` → Workflows.
2. Open `classification-stage2-dev`.
3. Note URL id = expect `BaBjEPi78taRj2G5`.
4. Record `updatedAt` / last saved time (for after-check).
5. Optional repo sync (read-only to disk; does not change n8n):

```bash
cd /Users/serge/Developer/categories
python3 scripts/pull_workflow.py classification-stage2-dev
# confirm workflows/classification-stage2-dev.id still BaBjEPi78taRj2G5
```

### C2. Duplicate in UI

1. On `classification-stage2-dev` canvas: **⋯ → Duplicate** (or Workflows list → Duplicate).
2. Immediately rename duplicate to: **`classification-stage2-hierarchy-dev`**.
3. Confirm new URL has a **different** workflow id (not `BaBjEPi78taRj2G5`).
4. Ensure toggle is **Inactive** (do not Activate / Publish).
5. Write new id into report and create:

```text
workflows/classification-stage2-hierarchy-dev.id   # new id only
```

6. Optional: Download JSON from UI → save as `workflows/classification-stage2-hierarchy-dev.json`.

### C3. Neutralize triggers (hierarchy only)

On **hierarchy** canvas only:

| Node | Action |
|------|--------|
| `In — Manual` | **Keep** |
| `In — Webhook` | **Delete** (or disconnect both outputs; delete preferred) |
| `In — Webhook Start` | **Delete** if present |
| Schedule / Cron | Must **not** exist; delete if any appeared |

Connections after cleanup: only `In — Manual` → `Run — Create Run`.

### C4. Break P1/2A/2B/Judge main path

Current source wiring: `Load — Limit Batch` → `P1 — Build Prompt`.

On hierarchy canvas:

1. **Disconnect** `Load — Limit Batch` → `P1 — Build Prompt`.
2. Do **not** delete P1/2A/2B/Judge nodes yet (optional sticky “RETIRED — do not reconnect”); they must be **unreachable**.
3. Add skeleton empty path (required for safe Close Run):

```text
Load — Limit Batch
  → Shell — Empty Gate (IF / Code)
       ├─ has products → (future Norm/Sem; B3+)  [leave unwired in B2]
       └─ no products  → Fin — Pick Run Item → Fin — Close Run
```

Minimal B2 variant without IF node:

- Insert Code node `Shell — Bypass Cascade` after `Load — Limit Batch`:

```javascript
// B2 skeleton: never enter P1/2A/2B. Pass through empty or non-empty.
// Non-empty items must NOT go to LLM until B3 — force empty processing for safety.
const run = $('Run — Create Run').first().json;
if (!items.length) {
  return [];
}
// Safety: drop any loaded products in B2 until allowlist Load + Norm exist.
return [];
```

Then wire: `Load — Limit Batch` → `Shell — Bypass Cascade` → need Fin barrier.

**Problem:** Fin today expects Upsert+Insert barrier. For 0 items, Create Run runs but Fin may never fire → `classification_runs.status='running'`.

**B2 required fix (hierarchy only):** after `Run — Create Run`, add parallel or post-Load empty closer:

Option **E (recommended):** Code after Load that always emits one synthetic fin item when `items.length===0`, then `Fin — Pick Run Item` → `Fin — Close Run` (reuse existing Close SQL; it already sets `finished_empty` when no snapshot rows).

Example `Shell — Ensure Empty Fin`:

```javascript
const run = $('Run — Create Run').first().json;
const runId = Number(run.id);
// Always close once for B2 skeleton when cascade is bypassed.
return [{ json: { id: runId, skeleton_empty: true } }];
```

Wire: `Load — Select Batch` → `Load — Attach Run ID` → `Load — Limit Batch` → `Shell — Bypass Cascade` (returns []) **and** separately from Limit Batch (or from Select Batch) a NoOp that triggers `Shell — Ensure Empty Fin` → `Fin — Close Run`.

Simplest reliable B2 topology:

```text
In — Manual → Run — Create Run → Run — Init Constants
  → Load — Select Batch (stub/0 rows)
  → Load — Attach Run ID
  → Load — Limit Batch
  → Shell — Ensure Empty Fin   // runOnceForAllItems; ignore products; emit {id}
  → Fin — Close Run            // existing SQL (finished_empty)
```

Skip Attach/Limit if preferred; Create Run → stub Load → Ensure Empty Fin → Close Run is enough for B2 shell smoke.

### C5. Stub or gate Load (hierarchy only — never edit source)

**Preferred for B2:** replace query in `Load — Select Batch` **on hierarchy workflow only** with hard empty stub:

```sql
-- B2 skeleton stub: never drain pending pool
SELECT
  NULL::bigint AS product_id,
  NULL::bigint AS product_raw_id
WHERE false;
```

**Alternative (closer to final design):** allowlist + kill-switch (still 0 rows while `hierarchy_experiment_enabled=false` or empty allowlist) — see [`22_EXPERIMENT_ISOLATION.md`](22_EXPERIMENT_ISOLATION.md). Either is OK for B2; stub is simpler and safer.

Do **not** change the SELECT inside `classification-stage2-dev`.

### C6. Update Create Run meta (hierarchy only)

Edit `Run — Create Run` SQL values:

| Column | Old (source) | New (hierarchy) |
|--------|--------------|-----------------|
| `run_type` | `stage2_primary_llm` | `stage2_hierarchy_v1` |
| `workflow_name` | `Pharmacy Stage 2 LLM` | `classification-stage2-hierarchy-dev` |
| `workflow_version` | `v1` | `stage2_hierarchy_v1` |
| `prompt_version` | `deepseek_shortlist_v1` | `prompt_hierarchy_skeleton_v0` (placeholder until B3) |

Keep `status='running'`, `batch_size` expression, `RETURNING` shape.

### C7. Update `Run — Init Constants` (hierarchy only)

Replace `constants.stage` / `next_action` / thresholds to hierarchy contract (keep decision_status / actor_type / log_status).

**stage keys to add/replace:**

```javascript
stage: {
  normalize: 'normalize',
  semantic_primary: 'semantic_primary',
  direction_candidates: 'direction_candidates',
  direction_select: 'direction_select',
  need_shortlist: 'need_shortlist',
  need_select: 'need_select',
  category_shortlist: 'category_shortlist',
  category_select: 'category_select',
  mnn_shortlist: 'mnn_shortlist',
  mnn_select: 'mnn_select',
  judge: 'judge',
  human_review: 'human_review'
},
next_action: {
  none: 'none',
  direction_select: 'direction_select',
  need_shortlist: 'need_shortlist',
  need_select: 'need_select',
  category_shortlist: 'category_shortlist',
  category_select: 'category_select',
  mnn_shortlist: 'mnn_shortlist',
  mnn_select: 'mnn_select',
  judge: 'judge',
  human_review: 'human_review'
},
thresholds: {
  min_soft_ok: 0.50,
  min_category_ok: 0.60,
  min_judge_ok: 0.60,
  borderline_low: 0.40,
  direction_soft_top_n: 8,
  need_hard_top_n: 12,
  category_hard_top_n: 10,
  mnn_soft_top_n: 8
},
final_source: {
  // keep system/human/judge; add:
  hierarchy_cascade: 'hierarchy_cascade',
  system: 'system',
  human: 'human',
  judge: 'judge'
},
model: {
  primary_actor_name: 'deepseek-chat',
  cascade_actor_name: 'deepseek-chat',
  judge_actor_name: 'qwen/qwen3.5-flash-02-23'
}
```

Legacy `primary_llm` / `fallback_2a` / `fallback_2b` keys: may remain for retired nodes but must not be on the live path.

### C8. DB Prepare Snapshot / Upsert — hierarchy column map (optional in B2, recommended)

If B2 shell never upserts products, this can wait until first terminal write (B3+). If you touch Prepare Snapshot now, add null-safe mappings for B1 columns (do not remove existing llm_/fallback_ columns — leave unused):

**New snapshot fields (from item / null):**  
`semantic_raw_json`, `semantic_attrs`, `semantic_confidence`, `semantic_explanation`, `semantic_validation_passed`, `semantic_reject_reason`, `selected_direction`, `direction_confidence`, `direction_raw_json`, `selected_need`, `need_confidence`, `need_raw_json`, `category_confidence`, `category_raw_json`, `selected_mnn`, `mnn_confidence`, `mnn_raw_json`, `cascade_trace`.

Upsert SQL (`DB — Upsert Snapshot`): add matching columns to INSERT/UPDATE lists. Log Prepare already stores extras in `output_payload` — no DDL.

**Finish Run:** leave SQL identical to source (contract unchanged).

### C9. Credentials

After Duplicate, nodes should still reference:

| Type | Name | Id (from local JSON) |
|------|------|----------------------|
| postgres | Postgres account | `rcmpgUWgwB2BRYlW` |
| deepSeekApi | DeepSeek account | `xyaJwQg88odvtCfC` |
| openAiApi | Polza account | `YFMznqpi3SeJdYod` |

Verify in UI; do not create new credentials. DeepSeek/Polza nodes may remain on canvas for B3 but **must not execute** (unreachable).

### C10. Save & export

1. Save hierarchy workflow (still Inactive).
2. Download JSON → `workflows/classification-stage2-hierarchy-dev.json`.
3. Write `workflows/classification-stage2-hierarchy-dev.id` with new id.
4. **Do not** run `push_workflow.py classification-stage2-dev`.
5. `push_workflow.py` only updates by existing `.id` — for hierarchy, either UI-only edits or extend tooling later with create; do not point hierarchy `.id` at prod id.

---

## D. Alternate method: export / import

1. UI: Export `classification-stage2-dev` (JSON).
2. Locally copy → rename `name` to `classification-stage2-hierarchy-dev`; **remove** top-level `id` / `active` if present so import creates new.
3. Import as new workflow; set Inactive.
4. Apply C3–C9 same as above.

## E. Alternate method: API (advanced)

```bash
# GET source (read-only)
# POST /api/v1/workflows with sanitized body {name, nodes, connections, settings}
# Never PUT to BaBjEPi78taRj2G5 for hierarchy content
```

Repo `push_workflow.py` is **update-only** (PUT by `.id`). Creating new workflow via API requires POST (not currently in `push_workflow.py`). Prefer UI Duplicate unless you add a create script.

---

## F. Post-clone checks (no LLM)

### F1. UI

- [ ] Workflow named `classification-stage2-hierarchy-dev`
- [ ] Id ≠ `BaBjEPi78taRj2G5`
- [ ] Inactive
- [ ] Only Manual trigger; no Cron; Webhook deleted/disconnected
- [ ] Load not connected to `P1 — Build Prompt`
- [ ] Source `classification-stage2-dev` still present; `updatedAt` unchanged

### F2. Settings SQL

```sql
SELECT key, value FROM pipeline_settings WHERE key LIKE 'hierarchy_%';
```

Expect: `hierarchy_experiment_enabled` = `{"value": false}`, allowlist `[]`.

### F3. Optional Manual dry-run (only if A7=yes)

1. Open hierarchy workflow → **Execute workflow** (Manual).
2. Expect: `Run — Create Run` inserts `run_type='stage2_hierarchy_v1'`.
3. Load returns 0 rows.
4. `Fin — Close Run` → `status='finished_empty'`.
5. No new rows in `product_classification` / `product_classification_log` for this run (except possibly none).
6. Confirm **no** DeepSeek/Polza node executed.

If Close Run did not fire: manually mark run finished and fix empty path before any further work:

```sql
UPDATE classification_runs
SET status = 'finished_empty', finished_at = now()
WHERE id = :<run_id> AND status = 'running';
```

### F4. Fill report

Complete [`26_B2_EXECUTION_REPORT.md`](26_B2_EXECUTION_REPORT.md).

---

## G. Out of scope reminder

Not in this runbook’s success criteria: Sem LLM, Dir+, allowlist fill, enabling experiment flag, prod Load exclude patch, activating hierarchy workflow.
