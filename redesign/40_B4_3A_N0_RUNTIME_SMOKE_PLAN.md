# 40 — B4.3a N=0 Runtime Smoke Plan (design only)

```text
Status: Design only — runtime NOT executed.
Plan readiness: READY_FOR_OWNER_N0_RUNTIME_APPROVAL
Preferred method: Manual Trigger (n8n editor Execute)
```

**Date:** 2026-09-11  
**Post-push baseline:** `POST_PUSH_STATIC_ACCEPT_PASS` / `LIVE_ALIGNED`  
(`redesign/artifacts/b4_2_4_post_push_accept_v1.md`)  
**Operator checklist:** `redesign/artifacts/b4_3a_n0_runtime_smoke_operator_checklist_v1.md`  
**Authority:** Sem prompts Option A approved; this smoke does **not** observe Sem/Direction logs.

---

## A. Exact scope

One future execution only:

```text
Workflow:
classification-stage2-hierarchy-dev
ID:
o8sugljHYuUs7IEC

Mode:
N=0 empty-path runtime smoke only

Product Load:
must remain WHERE false

Expected loaded products:
0

Expected LLM calls:
0

Expected real Direction candidates:
0

Expected product logs:
0

Expected snapshot writes:
0
```

**What this smoke tests**

- real empty Load behavior with `alwaysOutputData`
- `Load — Empty Branch Gate` empty marker
- mutually exclusive Empty IF branch
- single `Fin — Close Run` on empty path
- `classification_runs.status = finished_empty`

**What this smoke does not test**

- classification quality
- Sem / Direction output correctness
- candidate selection / real `categories_dict` scope
- Need / Category / Mnn / Judge
- N>0 product log-only path
- Close Run snapshot-based stats for products
- Wave-500 / production Stage 2

---

## B. Preconditions (block if unmet)

Verified before any click:

```text
- no active execution for this workflow;
- no zombie execution older than 30 minutes
  (stop via scripts/n8n_executions.py / API stop if found — separate ops,
  not part of smoke “success”);
- workflow active status verified (record only; do not toggle);
- current live workflow identity/updatedAt checked
  (name/id; post-push updatedAt baseline 2026-09-11T18:33:10.999Z
  or later only if an approved push intervened — else TO_CONFIRM drift);
- post-push fresh pull remains accepted
  (canonical equal to Safety+Direction source);
- Load query inspected and still:
  SELECT … WHERE false;  (no product_id IN / allowlist SQL);
- allowlist empty — satisfied by Load WHERE false and absence of
  allowlist inject nodes in export (no hierarchy_experiment /
  product_ids fields in current Init — treat extra smoke-settings
  flags as TO_CONFIRM if reintroduced later);
- hierarchy_experiment_enabled=false — TO_CONFIRM if such a setting
  exists outside this export; current local export has no such key;
  Load WHERE false is the hard product gate;
- no temporary inject/mock node;
- no active webhook client/run;
- no previous N=0 smoke currently running;
- operator has access to n8n execution history and pgAdmin read-only queries;
- no production workflow selected
  (must not open classification-stage2-dev).
```

Any failed check → verdict `N0_SMOKE_BLOCKED`; do not execute.

---

## C. Exact execution method (do not execute in this task)

### Preferred: Manual Trigger

```text
Method: Manual Trigger in n8n editor
         (Test/Execute workflow on classification-stage2-hierarchy-dev only)
```

**Why (project tooling / history)**

- B2 / Sem S0 empty path historically used Manual (e.g. B2 Manual run; S0 `finished_empty` with Sem Agent not called).
- Avoids `scripts/run_hierarchy_workflow.py` which can call `ensure_active` (activation change not in scope).
- Avoids webhook HTTP clients and concurrent webhook races.
- Avoids `n8n execute` CLI broker-port hazards (`N8N_RUNNERS_BROKER_PORT` collision noted in `Categories/n8n_execution_contract.md`).
- Empty `{}` Manual input needs no product ID / allowlist / batch>0 product set.
- Editor runData is best for Empty Branch Gate / IF / single Close assertions.

**Not preferred for this N=0**

| Method | Reason not preferred |
|---|---|
| Controlled webhook (`run_hierarchy_workflow.py`) | Sem-smoke oriented; may activate workflow; external HTTP |
| `n8n execute` CLI | Broker port / pinData caveats; harder empty-path inspection |

### Allowed input

```text
batch_size = 1 or omitted
```

Manual Trigger typically sends empty JSON → `Run — Apply Batch Cap` defaults
`effective_batch_size` to 5 when omitted; **Load still `WHERE false`**, so
**N=0 is guaranteed** regardless of batch_size (as long as Load SQL is unchanged).

Do **not** pass product IDs, allowlist payloads, or `batch_size > 10`.

### Idle rule (canon)

Before Manual click: workflow must be idle per
`Categories/n8n_execution_contract.md` (one live execution; stop >30 min zombies).

---

## D. Expected topology / node behavior

```text
In — Manual
→ Run — Apply Batch Cap
→ Run — Create Run          (INSERT classification_runs status=running)
→ Run — Init Constants
→ Load — Select Batch       (0 rows; alwaysOutputData placeholder)
→ Load — Empty Branch Gate  (empty_batch=true, product_count=0, run_id set)
→ Load — Empty?             (true / empty output only)
→ Shell — Ensure Empty Fin  (once)
→ Fin — Close Run           (once → finished_empty)
```

Empty Fin connects **directly** to `Fin — Close Run` (not via Merge Barrier).
Non-empty Close path (`Insert Log → Barrier → Pick → Close`) must stay dark.

### Must not execute

```text
Attach Run ID for products
Norm product
Limit for products
Sem0
Sem1
Normalize Sem attrs
Sem Route
Dir Candidate Builder
Dir Prepare Payload
Dir Static Post-process
Prepare Log / Insert Log for products
Prepare/Upsert Snapshot
LLM/AI Agent/HTTP
Need/Cat/Mnn/Judge/Telegram
```

---

## E. Runtime assertions

### n8n execution-level

```text
- one workflow execution;
- status success;
- no retry loop;
- no hung execution;
- duration within expected safe range (typical: seconds–low minutes;
  hard fail if >30 minutes);
- no node error;
- exactly one Close Run invocation;
- no LLM/HTTP activity.
```

### Node-level

```text
- Load result = 0 product rows (no product_id);
- Empty Branch Gate result has expected marker:
  empty_batch=true, skeleton_empty=true, product_count=0, run_id set;
- Load — Empty? takes empty output only (true branch);
- Empty Fin executes once;
- Fin — Close Run executes once;
- non-empty branch is not executed
  (Attach / Norm / Limit / Sem / Dir / Prepare Log dark);
- no Sem/Direction node executes;
- no snapshot node executes.
```

### PostgreSQL read-only verification

**No write SQL.** Read-only checks for the latest run created by this smoke:

Confirmed table/field names (from Close Run / Create Run / contract):

```text
classification_runs
  - id (= run_id)
  - status            expect: finished_empty
  - finished_at       expect: NOT NULL
  - success_count     expect: 0
  - error_count       expect: 0
  - workflow_name     expect: classification-stage2-hierarchy-dev
  - batch_size        informational (cap metadata; not product count)

product_classification
  - latest_run_id     expect: no rows with latest_run_id = run_id

product_classification_log
  - expect: no rows for this run_id
    (column name for run link: TO_CONFIRM exact column —
     historically run_id / metadata; verify in pgAdmin before assert)

classification_shortlist
  - expect: no rows for this run_id, if table is queried
    (applicable for Stage2 shortlist stages; hierarchy N=0 should not write)
```

Also confirm:

```text
- exactly one newly created classification_runs row for this smoke window;
- its id matches execution context (Create Run / Close Run runData).
```

Example **read-only** shape (operator adapts; do not execute in this design task):

```sql
-- illustrative only
SELECT id, status, finished_at, success_count, error_count, batch_size, metadata
FROM classification_runs
WHERE id = :<run_id>;

SELECT count(*) FROM product_classification WHERE latest_run_id = :<run_id>;
```

---

## F. Stop conditions

Abort / escalate (do not “fix in place”) if:

```text
- Load returns any product;
- Allowlist is nonempty / Load SQL no longer WHERE false;
- hierarchy_experiment_enabled=true (if such setting is present);
- any Sem/Direction/LLM/HTTP node begins execution;
- any snapshot node executes;
- more than one Close Run invocation appears;
- run fails to close;
- workflow attempts a product log on N=0;
- workflow execution lasts >30 minutes;
- unexpected DB write beyond classification_runs create/finish occurs;
- workflow identity/Load SQL differs from expected;
- production workflow was selected.
```

**No automatic rollback** via workflow push/pull/manipulation.

On failure:

```text
1. Stop execution if still running (zombie stop only).
2. Capture execution export + DB read-only evidence.
3. Do not rerun.
4. Do not push.
5. Do not open Load / allowlist.
6. Rollback of workflow graph only under a new explicit owner approval
   (restore from live_pre_push / post_push backups — separate task).
```

---

## G. Evidence artifacts after future run

Propose (create only after a real smoke; **not now**):

```text
redesign/artifacts/b4_3a_n0_runtime_smoke_run_<run_id>_v1.md
redesign/artifacts/b4_3a_n0_runtime_smoke_run_<run_id>_v1.json
redesign/artifacts/b4_3a_n0_runtime_smoke_execution_export_<execution_id>.json
redesign/artifacts/b4_3a_n0_runtime_smoke_pg_check_<run_id>.md
```

Capture execution export and DB evidence **before** any second run.

---

## H. Verdict

```text
N0_SMOKE_PASS
N0_SMOKE_FAIL
N0_SMOKE_BLOCKED
```

`N0_SMOKE_PASS` requires all empty-path and single-close assertions plus
`finished_empty` DB proof.  
It does **not** authorize N=1 automatically.

---

## I. Exact next boundary

```text
N0_SMOKE_PASS may permit preparing an N=1 runtime-smoke plan only.
It does not authorize N=1 execution, allowlist opening, LLM, real
categories_dict loading, Need, snapshot, Wave-500 or production changes.
```

---

## J. Owner confirmation template (required before run)

```text
Разрешаю один N=0 runtime smoke только workflow
classification-stage2-hierarchy-dev (o8sugljHYuUs7IEC)
при сохранённом Load WHERE false.

Разрешаю запуск только для проверки Empty Branch Gate,
взаимоисключающего Empty/Non-empty маршрута и одного Close Run.

Не разрешаю загрузку товаров, LLM/HTTP, Direction с реальными candidates,
allowlist, изменение Load/settings/prompts, snapshot, DB/schema,
Need/Cat/Mnn/Judge/Telegram, Wave-500, production workflow или Git push.

После запуска — только capture execution evidence и read-only DB checks;
никаких повторных запусков без нового approval.
```

---

## Known unresolved (out of this smoke)

```text
- Close Run snapshot-based stats for future N>0 log-only path;
- post-push Sem/Direction execution/log behavior;
- real categories_dict scope;
- Need;
- Wave-500.
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
