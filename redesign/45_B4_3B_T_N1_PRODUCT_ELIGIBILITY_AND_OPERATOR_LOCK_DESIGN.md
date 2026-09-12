# 45 — B4.3b-T.3 N1-T product eligibility + operator lock (design only)

```text
Status: Design only — no DB dry-run, no product_id, no seam/Load/settings/runtime.
Purpose: close two pre-patch blockers conceptually:
  (1) exact-ID eligibility proof contract;
  (2) operator/process lock against Mode C Load + G3=false → LLM.
```

**Date:** 2026-09-12  
**Workflow:** `classification-stage2-hierarchy-dev` / `o8sugljHYuUs7IEC`  
**Export SHA256:** `5edddf050b1bdeb06518527403a8e9d7861b520f2d45db37410400fac0b0df9e`  
**Checklist:** `redesign/artifacts/b4_3b_t_n1_product_eligibility_checklist_v1.md`  
**Manifest template:** `redesign/artifacts/b4_3b_t_n1_operator_lock_manifest_template_v1.json`  
**Canon:** `44_B4_3B_T_N1_PRESEM_CONTRACT_RESOLUTION.md` (`N1_T_STATIC_PATCH_PARTIAL`)

---

## 1. Exact Load evidence (current export)

### 1.1 SQL quoted from `Load — Select Batch`

```sql
-- B2 skeleton stub: never drain pending pool
SELECT
  NULL::bigint AS product_id,
  NULL::bigint AS product_raw_id
WHERE false;
```

| Aspect | Current export fact |
|---|---|
| Source tables | **none** (literal null columns) |
| Joins | **none** |
| Eligibility predicates | only `WHERE false` |
| `WHERE false` position | sole filter — guarantees 0 product rows |
| ORDER BY | none |
| LIMIT | none in SQL (batch limit is later: `Load — Limit Batch`) |
| `product_classification` | **not referenced** |
| `classification_shortlist` | **not referenced** |
| allowlist / `hierarchy_experiment_enabled` | **not referenced** in this node |
| `alwaysOutputData` | `true` (N=0: one empty placeholder, no `product_id`) |

### 1.2 Downstream identity of a “loaded product”

From export Code (not Load SQL):

```text
Load — Empty Branch Gate:
  products = items where product_id is non-null/non-empty
  else empty_batch=true

Load — Empty? → false branch → Load — Attach Run ID
  attaches run_id + run_meta (batch fields from Cap)

Norm — Normalize Product → Load — Limit Batch
  Limit.maxItems = $('Run — Create Run').first().json.batch_size || 5
```

**Fields required to prove exact one-item eligibility (for a future Mode C Load):**

```text
product_id (exactly one)
product_raw_id (if selected by Load)
join partner row count = 1 under shortlist rules
Create Run / Cap effective_batch_size = 1 ⇒ Limit emits ≤1
Empty Gate product_count = 1
```

### 1.3 Proposed Mode C conceptual shape

Temporary Load must **not** be unconstrained pending drain. Conceptually:

```text
existing safe eligibility conditions
AND exact product_id = :approved_product_id
AND existing allowlist/experiment controls agree with the same ID
LIMIT 1   (via Create Run batch_size=1 and/or hard LIMIT 1)
```

Reference family (repo tooling, **not** in live export):  
`scripts/sem_smoke_patch_workflow.py` → `SMOKE_LOAD_SQL`  
(`product_classification` ⋈ `classification_shortlist` + `pipeline_settings` CTE).

### 1.4 Proposed read-only dry-run query shape

```text
PROPOSED — not executed; exact SQL requires separate review/approval.
Placeholder: :approved_product_id
```

**Purpose only — illustrative shape aligned to SMOKE_LOAD_SQL family:**

```sql
-- PROPOSED read-only dry-run shape (NOT executed in this task)
WITH settings AS (
  SELECT
    COALESCE(
      (SELECT (value->>'value')::boolean
       FROM pipeline_settings
       WHERE key = 'hierarchy_experiment_enabled'),
      false
    ) AS experiment_enabled,
    COALESCE(
      (SELECT value->'product_ids'
       FROM pipeline_settings
       WHERE key = 'hierarchy_product_allowlist'),
      '[]'::jsonb
    ) AS product_ids
)
SELECT
  p.product_id,
  p.product_raw_id,
  p.decision_status,
  p.rule_decision_status,
  s.stage,
  s.combined_text,
  length(COALESCE(s.combined_text, '')) AS combined_text_len
FROM product_classification p
JOIN classification_shortlist s
  ON s.product_id = p.product_id
CROSS JOIN settings st
WHERE p.product_id = :approved_product_id
  -- PROPOSED: mirror future Mode C guards (exact text TBD at SQL review):
  -- AND st.experiment_enabled IS TRUE
  -- AND st.product_ids = '[:approved_product_id]'::jsonb   -- or ANY(allowlist) with len=1
  -- AND p.decision_status IN (...)
  -- AND p.rule_decision_status IN (...)
  -- AND (s.stage IS NULL OR s.stage = 'primary_rules')
ORDER BY p.product_id
LIMIT 2;   -- dry-run uses LIMIT 2 to detect duplicates; expect exactly 1 row
```

**Pass rule:** result row count **= 1**.  
**Fail:** 0 or ≥2 → product rejected; N1-T blocked.

Baseline settings dry-run (also PROPOSED, not executed): confirm before temporary window  
`hierarchy_experiment_enabled=false`, `hierarchy_product_allowlist.product_ids=[]`.

---

## 2. Selection criteria (no ID chosen)

Mandatory for a future candidate:

```text
- exact product_id is owner-approved;
- exists once in actual Load source/join under the approved Mode C SQL;
- joins exactly one shortlist row under those conditions;
- stable text available to Norm (`combined_text` / fields Load returns);
- non-null product_id (and product_raw_id if required by Load);
- not product_id=26346;
- not a non-standard phytotea/form edge case;
- not an unresolved manufacturer-alias case;
- not under active production Stage 2 processing;
- no active conflicting hierarchy-dev run;
- no sensitive edge case;
- no external retrieval required;
- boring structurally clean item preferred;
- not dependent on real categories_dict / MNN / Need selection.
```

**Rationale:** N1-T validates topology / G3 seam / Direction static log / single Close — **not** model quality. Prefer a dull, join-stable row.

---

## 3. Read-only future preflight proof categories

| # | Evidence category | Purpose | Must equal / condition | Fail result | Blocks N1-T? |
|---|---|---|---|---|---|
| 1 | Product source existence / identity | ID exists | one logical product identity | missing ID | **Yes** |
| 2 | Load join count for ID | Exact-ID uniqueness | count **= 1** under Mode C dry-run | 0 or >1 | **Yes** |
| 3 | Current classification state | Eligibility vs Mode C filters | matches approved predicate set | ineligible status | **Yes** |
| 4 | Latest/recent classification logs | Conflict / noise awareness | no blocking open attempt **TO_CONFIRM** policy | active conflicting log/run | **Yes** if conflict policy trips |
| 5 | No running classification/hierarchy hold | Isolation | no live exec on hierarchy-dev; no conflicting run lock | live/zombie/conflict | **Yes** |
| 6 | Shortlist relation | Join partner | exactly one required shortlist row | 0 or many | **Yes** |
| 7 | No duplicate product_raw/source | Identity hygiene | ≤1 raw linkage under dry-run columns | duplicates | **Yes** if duplicates inflate join |
| 8 | Production activity exclusion | Do not steal prod drain | not hot pending in prod Stage 2 window **TO_CONFIRM** | in prod hot set | **Yes** |
| 9 | Text quality | Norm/Dir context | non-empty usable `combined_text` / normalized path | empty/malformed | **Yes** for N1-T |
| 10 | Temporary Mode C exact-ID ⇒ 1 | End-to-end predicate | dry-run of **approved** Mode C text returns 1 | ≠1 | **Yes** |

All of the above are **future** read-only checks after owner approval of SQL package + `product_id`. **Not executed now.**

---

## 4. Operator lock design

### 4.1 Manifest

Template: `redesign/artifacts/b4_3b_t_n1_operator_lock_manifest_template_v1.json`  
All product/SHA/settings values remain `null`/`false` until a future approved fill-in.

### 4.2 Fail-closed lock conditions

**All** must be true before N1-T run; any false/missing ⇒ **N1-T MUST NOT RUN**:

```text
workflow name/id exact match (classification-stage2-hierarchy-dev / o8sugljHYuUs7IEC);
expected post-seam SHA match;
test_mode exact string n1_presem_smoke;
G3 enabled for the approved window;
G3 default false outside that window (fail-closed);
approved product_id present;
loaded product count exactly 1;
loaded ID equals approved ID;
requested_batch_size=1 AND effective_batch_size=1;
Mode C exact-ID + LIMIT 1 patch confirmed;
Mode A allowlist/experiment agree with same ID if used;
Load default was WHERE false before temporary patch;
Sem agents expected dark on true seam path;
llm_allowed=false;
Snapshot unreachable from Sem/Dir;
workflow inactive;
one CLI manual-equivalent execution only;
no active/zombie execution (>30m stopped first);
owner one-run approval exists;
rollback artifact / backup SHA pre-created.
```

### 4.3 Hazard controls — Mode C Load + G3=false → LLM

Confirmed topology (export):

```text
Limit → Sem0 — Build Prompt → … Sem0/Sem1 AI Agents (+ DeepSeek)
```

If Mode C returns a product and Gate IF is false/absent, **LLM path runs**.

| Layer | Control | Guarantee |
|---|---|---|
| **1. Static** | After future T1 patch: default stamp `enabled=false`; true branch only with full Stub checks; false → Sem0 | Prevents silent stub; does **not** alone prevent LLM if Mode C open + false |
| **2. Operator manifest** | Mode C `enabled` only when G3 `enabled=true` and `expected_gate_result=true` and product/batch locks filled; preflight sign-off | **Primary** prevention |
| **3. Real-time stop** | If Sem0 begins → stop execution; no retry | Best-effort; **cannot** guarantee zero first LLM outbound packet |

**Primary control = do not open Mode C / do not run unless Layer 2 is fully green.**

### 4.4 Approval matrix

| Action | Separate explicit owner approval? | Why |
|---|---|---|
| Product eligibility read-only DB dry-run | **Yes** | Touches live DB read path / may reveal ops data |
| Selection of exact `product_id` | **Yes** | Chooses real catalog entity |
| T1 seam static patch | **Yes** | Changes hierarchy-dev graph |
| Temporary Mode C Load patch | **Yes** | Lifts `WHERE false` |
| Mode A settings/allowlist write | **Yes** | Mutates `pipeline_settings` |
| Push of temporary workflow patch | **Yes** | Irreversible server update until rollback |
| One N1-T CLI run | **Yes** | Creates run/log; residual LLM risk if mis-armed |
| Temporary rollback (workflow + Load + settings) | **Yes** | Restores safe defaults; must be verified |
| Post-run DB read-only verification | **Yes** (can be bundled with run approval) | Reads run/log/settings |
| Any retry | **Yes** | New execution |
| N1-L / real LLM smoke | **Yes** (separate track) | Explicitly out of N1-T |

---

## 5. Recommended next boundary

```text
Next allowed action after review:
prepare a read-only product eligibility SQL/check package,
then execute it only after explicit owner approval.

Not authorized:
- product selection now;
- workflow seam patch;
- Load patch;
- settings changes;
- push;
- N1-T run;
- LLM;
- Need;
- real categories_dict;
- snapshot;
- Wave-500;
- production changes.
```

---

## Explicitly not changed

- n8n workflows: not changed
- n8n runtime/executions/webhooks: not run
- PostgreSQL schema/data: not changed
- SQL: not executed or changed
- production Stage 2: not changed
- hierarchy-dev runtime settings: not changed
- Load / allowlist / kill switch: not changed
- snapshot / attr_*: not changed
- Sem0/Sem1 prompts and prompt versions: not changed
- real categories_dict data: not loaded
- Need / Category / Mnn / Judge / Telegram: not added
- source and freeze evidence artifacts: not changed
- Git commit/push: not performed
