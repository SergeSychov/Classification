# 41 — B4.3b N=1 Non-empty Runtime Smoke Plan (design only)

```text
Status: Design only — N=1 runtime not authorized.
Verdict: N1_SMOKE_PLAN_PARTIAL
```

**Date:** 2026-09-12  
**Workflow:** `classification-stage2-hierarchy-dev` / `o8sugljHYuUs7IEC`  
**N=0 baseline:** `N0_SMOKE_PASS` (exec `42877`, run `474`)  
**Checklist:** `redesign/artifacts/b4_3b_n1_runtime_smoke_operator_checklist_v1.md`

---

## Why PARTIAL (not READY)

Under the **current live topology**, the non-empty branch is:

```text
Empty? [false]
→ Attach Run ID → Norm — Normalize Product → Load — Limit Batch
→ Sem0 — Build Prompt → Sem0 — LLM Prepare → Sem0 — AI Agent (+ DeepSeek)
→ … → Sem — AI Agent (+ DeepSeek)
→ Norm Sem attrs → Sem — Route
→ Dir static zone → Sem — Prepare Log → Insert Log → Barrier → Pick → Close
```

Confirmed from local post-push export:

- `Sem0 — AI Agent` / `Sem — AI Agent` are `@n8n/n8n-nodes-langchain.agent`
- models: `n8n-nodes-deepseek-v4-thinking-fix.deepSeekV4ChatModel`
- **no** existing Load/Sem bypass inject node on canvas (`Sem — Smoke Inject Bad JSON` absent)
- Load SQL is still stub `WHERE false` (allowlist settings alone do nothing)
- non-empty Close path is **only** via Insert Log → Barrier → Pick → Close  
  (Empty Fin is empty-branch only)

Therefore:

```text
N=1 cannot reach Direction static assertions + product log + single Close
without either:
  (1) live Sem0/Sem1 LLM calls, or
  (2) a new separately approved temporary pre-Sem / LLM-stub seam
     (not present today).
```

Purpose items that require Sem→Dir→Log **and** “no LLM” are **mutually exclusive** on current topology.  
This plan still defines selection modes, product contract, rollback, and approval gates.

---

## A. Scope of a future N=1 smoke

```text
Workflow: classification-stage2-hierarchy-dev
ID: o8sugljHYuUs7IEC
Max products: 1
requested_batch_size: 1
effective_batch_size: 1
One live execution: required
active: remain false unless separate activation approval
Preferred method: CLI n8n execute (Manual-equivalent), as proven by N=0
Webhook / activation: not for first N=1
```

**In scope (when authorized):**

1. Controlled non-empty branch selected correctly  
2. One product / one consistent `run_id`  
3. `effective_batch_size=1` preserved  
4–9. Sem / Direction / log **only if** the authorized smoke design explicitly includes them **and** the LLM-or-seam gate is satisfied  
10. Snapshot untouched  
11. Exactly one Close Run  
12. Final run status/counters **observed**, not assumed  
13. Temporary selection changes rolled back  

**Out of scope / not validated by N=1:**

- Direction quality, category selection, Need  
- real `categories_dict` scope  
- LLM quality  
- Wave-500 / production readiness  

---

## B. Mode comparison

### Mode A — Existing allowlist / kill-switch settings only

**Proven keys** (`pipeline_settings`, B1 / Sem smoke tooling):

```text
hierarchy_experiment_enabled   → {"value": false|true}
hierarchy_product_allowlist    → {"product_ids": [<id>, ...]}
```

N=0 DB read showed baseline: enabled=`false`, `product_ids=[]`.

| Fact | Implication |
|---|---|
| Current Load is `WHERE false` | Settings **do not** load any product |
| Historical Sem smokes always paired settings with a **temporary Load SQL patch** | Mode A alone is incomplete |
| Settings writes are DB writes (via pgAdmin or temp n8n settings workflow) | Requires rollback proof |

**Suitable alone for first N=1?** **No.**

### Mode B — Controlled local / in-workflow injection

| Fact | Implication |
|---|---|
| Would require Code-node inject + push | Workflow patch + server update |
| Can bypass real Postgres Load | Does **not** prove Empty Branch Gate / alwaysOutputData non-empty behavior |
| Historical `Sem — Smoke Inject Bad JSON` is for post-LLM bad JSON, **absent** now | Not a Load non-empty seam |
| Risk: fake items without `product_id` / shortlist fields break Norm/Sem contracts | High if used as Load substitute |

**Suitable for first N=1?** **No** as primary (does not test actual non-empty Load).  
May be considered later only for an **explicit LLM-stub seam**, separate design.

### Mode C — Temporary controlled Load change (exact ID + LIMIT 1)

Proven pattern: `scripts/sem_smoke_patch_workflow.py` → `SMOKE_LOAD_SQL` (or narrower exact-ID variant) + push + settings enable + allowlist `[id]` + run + **mandatory revert** to `WHERE false` / enabled false / `[]`.

| Guard (required) | Detail |
|---|---|
| Exact `product_id = <approved>` | Never `ORDER BY random` / bare pending drain |
| `hierarchy_experiment_enabled=true` only during window | Kill switch |
| Allowlist length = 1 | Belt-and-suspenders with SQL `ANY(product_ids)` |
| `LIMIT` tied to `batch_size` with request `1` | Cap node forces effective ≤10; request must be 1 |
| Pre/post SQL evidence | Selection returns exactly 1 row before run; 0 after rollback |
| Separate owner approval | Most invasive: Load + settings + (if full path) LLM |

**Suitable for first N=1 selection?** **Yes — recommended selection mechanism**, with LLM/seam gate still separate.

### Mode D — Existing safe test/seam already in workflow

```text
Result: NOT FOUND on current export.
- No inject node
- No fixture Load path beside WHERE false
- No LLM-free Sem stub on live edges
```

**Suitable?** **No** (does not exist).

### Comparison matrix

| Criterion | A | B | C | D |
|---|---|---|---|---|
| Requires workflow patch | No* | Yes | **Yes** (Load SQL + push) | N/A (missing) |
| Requires DB/settings write | **Yes** | Maybe | **Yes** (settings) | N/A |
| Tests actual non-empty Load | **No** (while WHERE false) | No | **Yes** | N/A |
| Can preserve Load `WHERE false` | Yes (but then N=0 only) | Yes | **No** (temporary) | N/A |
| Risk of accidental product processing | Low alone / High if Load opened poorly | Medium–High | **Controlled if exact-ID + LIMIT 1** | N/A |
| Rollback complexity | Settings only | Patch + push | **Load backup restore + settings** | N/A |
| Suitable for first N=1 | **No alone** | No primary | **Yes (selection)** | No |

\*A becomes useful **only when combined with C**.

---

## C. Non-binding recommendation

```text
Recommended selection stack for future N=1:
  Mode C (temporary exact-ID Load SQL, LIMIT 1)
  + Mode A controls (experiment_enabled + allowlist=[id])
  + CLI Manual-equivalent execute (N=0 method)
  + mandatory backup/push/revert using proven Sem-smoke tooling pattern
```

**Do not choose `product_id` in this design document.**

### Two execution tracks (owner must pick one)

| Track | What it proves | Extra approval required |
|---|---|---|
| **N1-T (topology / non-empty Load)** | Load returns 1 row; Empty?=false; Attach/Norm/Limit once; cap=1 | Still needs a **Close strategy**: today Close requires Sem→Log. Without LLM, needs **new temporary seam** (Limit→log/close or LLM stub) — **separate design + approval**. Until then N1-T cannot finish cleanly. |
| **N1-L (log-only full path)** | Sem0/Sem1 + Route + Dir static + Prepare/Insert Log + one Close | **Explicit LLM/DeepSeek approval** for Sem0+Sem1 on 1 item; Direction remains static/no dict; snapshot off |

**Recommended eventual first complete N=1 (when owner wants Dir/log evidence):** Track **N1-L** with Mode C+A, after LLM approval.  
**Recommended first no-LLM N=1:** **blocked** until a temporary pre-Sem close/stub seam is designed and approved (not Mode D — does not exist).

---

## D. Product selection contract (no ID now)

Future fixture product must:

```text
- be explicitly owner-approved by product_id;
- be a low-risk known testable item;
- have stable text available to Load
  (current smoke Load source: product_classification ⋈ classification_shortlist
   with combined_text / shortlist fields — NOT products_prepared in SMOKE_LOAD_SQL;
   products_prepared availability = TO_CONFIRM if a different Load variant is proposed);
- be available under the exact temporary Load predicate;
- not be in active production processing;
- not have a conflicting active classification run;
- not be a sensitive/ambiguous edge case;
- not be product_id=26346 for first topology/log smoke;
- preferably need no real MNN/category judgment;
- not require external retrieval;
- be safely loggable;
- be selected only by exact ID, never random pending selection.
```

### Future read-only pre-run checks (do not run now)

```text
- product exists (exactly one source row under proposed Load SQL);
- current product_classification snapshot + recent product_classification_log;
- no active run lock/conflict for that product;
- no ongoing production Stage 2 execution on host;
- safe product-kind / text availability (combined_text non-empty if Sem path included);
- dry-run of selection SQL returns exactly one row;
- pipeline_settings baseline recorded (enabled=false, allowlist=[]).
```

Evidence file (future):  
`redesign/artifacts/b4_3b_n1_runtime_smoke_plan_selection_evidence_v1.md`

---

## E. Execution constraints (future)

```text
- no concurrent live execution; no zombie >30 min;
- pre-run identity: name/id; Load mechanism verified; updatedAt noted;
- pre-run DB baseline snapshot (read-only);
- temporary Load/settings applied only after explicit approvals;
- requested_batch_size=1 → effective_batch_size=1 (Apply Batch Cap);
- one CLI execution only; no automatic retry;
- stop within 30 minutes;
- no second N=1 without new approval;
- active remains false unless separate activation decision.
```

---

## F. Runtime assertions

### Shared (any N=1 that loads a product)

```text
- exactly one selected/loaded product_id (matches approval);
- Empty Branch Gate: empty_batch=false; product_count=1;
- Load — Empty?: non-empty branch only;
- Attach Run ID once; run_id stable;
- effective_batch_size=1; Limit emits one item;
- Snapshot/Upsert dark;
- Need/Cat/Mnn/Judge/Telegram dark;
- exactly one Close Run;
- no extra products.
```

### Track N1-T (no LLM) — only if pre-Sem seam approved

```text
- Sem0/Sem1/AI Agent/DeepSeek/HTTP must remain dark;
- Dir zone dark unless seam explicitly forwards static Dir (usually no);
- Close via approved seam only;
- if seam not approved → do not run (BLOCKED).
```

### Track N1-L (LLM approved)

```text
- Sem0 + Sem1 AI Agents execute once each (expected);
- after Sem Route direction_select → Dir static once:
    candidate_scope_status=not_loaded_static
    direction_candidate=null
    selected_category_id=null
    decision_status=pending_fallback
    next_action=need_select
    stop_reason=need_not_implemented_static
- Sem — Prepare Log + Insert Log once;
- no real categories_dict load;
- prompt_version observed (Sem1 authority: prompt_semantic_v3; Sem0: prompt_sem0_v2).
```

**Blocker statement (mandatory):**  
If Sem0/Sem1 are on path, **LLM will be invoked**. There is **no** hidden no-LLM bypass in the current export.

### Database read-only assertions (future)

```text
classification_runs:
- one new run; run_id matches path;
- status/finished_at/counts recorded as observed (do not assume finished_empty).

product_classification_log:
- exact row count for run_id (expect 1 on N1-L if single stage log; observe);
- stage(s) observed; product_id/run_id consistent;
- selected_category_id null;
- Direction static fields present if Dir reached;
- workflow_version / prompt_version observed.

product_classification:
- no terminal snapshot update; no latest_run_id change under terminal-only policy;
- no final category / final source write.

classification_shortlist:
- no unexpected insert from this run.

pipeline_settings:
- after rollback: enabled=false, product_ids=[].
```

---

## G. Stop and rollback

**Stop/escalate if:**

```text
- >1 product loaded; wrong product_id;
- selection without exact-ID control;
- effective_batch_size >1;
- Sem0/Sem1 would call LLM while LLM not approved;
- LLM/HTTP starts when not approved;
- Snapshot/Upsert starts;
- Direction gets real category scope;
- category_id / final decision appears;
- >1 Close Run; run does not finish;
- unexpected DB write;
- temporary Load/settings cannot be restored/verified;
- workflow identity differs; execution >30 minutes.
```

**Rollback design:**

```text
- no automatic workflow rollback mid-flight;
- stop execution; capture evidence;
- restore Load to WHERE false from pre-N1 workflow backup (push);
- restore pipeline_settings to enabled=false, allowlist=[];
- read-only post-rollback verification;
- no repeat run without new owner approval.
```

Tooling references (not executed here):  
`scripts/sem_smoke_patch_workflow.py`, `sem_smoke_allowlist.py`, `sem_smoke_settings_via_n8n.py`, `scripts/push_workflow.py`, `scripts/pull_workflow.py`.

---

## H. Future evidence artifacts (names only)

```text
redesign/artifacts/b4_3b_n1_runtime_smoke_plan_selection_evidence_v1.md
redesign/artifacts/b4_3b_n1_runtime_smoke_run_<run_id>_v1.md
redesign/artifacts/b4_3b_n1_runtime_smoke_run_<run_id>_v1.json
redesign/artifacts/b4_3b_n1_runtime_smoke_execution_export_<execution_id>.json
redesign/artifacts/b4_3b_n1_runtime_smoke_pg_check_<run_id>.md
redesign/artifacts/b4_3b_n1_runtime_smoke_rollback_check_<timestamp>.md
```

---

## I. Exact owner approvals required before any N=1 run

All of the following (as applicable):

```text
1. Explicit N=1 runtime approval for hierarchy-dev only.
2. Explicit approved product_id (exact ID).
3. Explicit approval for temporary Load SQL change away from WHERE false
   (Mode C) + push of hierarchy-dev only.
4. Explicit approval for temporary pipeline_settings writes
   (hierarchy_experiment_enabled=true, allowlist=[id]) + rollback duty.
5. Track choice:
   - N1-L: explicit Sem0+Sem1 LLM/DeepSeek approval for N=1, OR
   - N1-T: explicit temporary pre-Sem close/stub seam design+patch approval
     (new work — not available today).
6. No webhook/activation unless separately approved.
7. Mandatory rollback verification after the run.
```

### Owner confirmation template (draft)

```text
Разрешаю один N=1 non-empty runtime smoke только workflow
classification-stage2-hierarchy-dev (o8sugljHYuUs7IEC)
для product_id=<OWNER_ID>, requested_batch_size=1.

Разрешаю временный Mode C Load (exact ID + LIMIT 1) и
pipeline_settings allowlist=[<OWNER_ID>] + experiment_enabled=true
с обязательным rollback в WHERE false / enabled=false / [].

Выбранный track: <N1-L with LLM | N1-T with approved pre-Sem seam>.

Не разрешаю: random pending drain, batch>1, real categories_dict,
Need/Cat/Mnn/Judge/Telegram, snapshot, Wave-500, production Stage 2,
activation/webhook (unless separately stated), Git push.
```

---

## J. TO_CONFIRM / blockers summary

| Item | Status |
|---|---|
| Mode A alone with current Load | **Blocked** (no effect) |
| Mode D existing no-LLM seam | **Missing** |
| Full Sem→Dir→Log without LLM | **Blocked** on current topology |
| Exact product_id | **Owner must supply** |
| `products_prepared` vs Load join | Load smoke SQL uses `product_classification`+`shortlist`; products_prepared **TO_CONFIRM** if required |
| N1-T close without Sem | Needs **new seam design** |
| N1-L | Needs **LLM approval** |

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
