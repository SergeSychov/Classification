# 44 — B4.3b-T.2 N1-T read-only contract resolution

```text
Status: Read-only verification only — no patch/runtime/SQL.
Readiness: N1_T_STATIC_PATCH_PARTIAL
```

**Date:** 2026-09-12  
**Workflow export:** `workflows/classification-stage2-hierarchy-dev.json`  
**SHA256:** `5edddf050b1bdeb06518527403a8e9d7861b520f2d45db37410400fac0b0df9e`  
**Sidecar ID:** `o8sugljHYuUs7IEC`  
**Artifacts:**  
`redesign/artifacts/b4_3b_t_n1_presem_contract_matrix_v1.csv`  
`redesign/artifacts/b4_3b_t_n1_presem_toconfirm_resolution_v1.json`

---

## 1. Metadata / export identity

| Field | Value |
|---|---|
| name | `classification-stage2-hierarchy-dev` |
| nodes | 90 |
| bytes | 247517 |
| SHA256 | `5edddf050b1bdeb06518527403a8e9d7861b520f2d45db37410400fac0b0df9e` |
| N=0 evidence | exec `42877` / run `474` / Cap `effective_batch_size=5` |

---

## 2. Answers A–F

### A. Gate storage G3 vs G1 → `G3_STATIC_STAMP_FEASIBLE`

| Question | Evidence |
|---|---|
| Manual input object? | `In — Manual` type `manualTrigger`, `parameters: {}`. Emits one empty `{}` under CLI (`n8n execute` ignores pinData — N=0 proven). UI Manual can carry JSON in principle; CLI does not without inject/stamp. |
| Stamp after Cap without DB? | Cap → Create Run is Code→Postgres. A **future** Code between Cap and Create (or Cap itself temporary) can stamp fields onto `json` with `...j`. No DB required. |
| Init preserves upstream? | **Yes.** `return { json: { ...item.json, constants } }`. |
| Overwrites before Limit? | Cap sets batch fields; Create returns run row (new item shape from Postgres); Init spreads item + constants; Load replaces with SQL columns; Empty Gate spreads product rows; Attach adds `run_id`/`run_meta` via `...item.json`. Stamps placed **after Cap / in Init** survive if re-spread; stamps only on Cap item are **lost at Create Run** unless re-applied in Init/Attach. **Critical:** stamp must be re-attached in **Init** (and/or Attach) after Create Run. |
| Gate after Limit can read? | After Limit, item has Load columns + Attach `run_id`/`run_meta` + Norm Product fields + Init `constants`. `product_id` exists only **after Load** (not before). `effective_batch_size` available via `run_meta` or `$('Run — Apply Batch Cap')` / Create `batch_size`. Future `test_mode` must be stamped onto item or `constants` before Gate. |
| Where product_id appears | First real `product_id`: Load row. Empty Gate filters on `item.json.product_id`. Path before product: Manual→Cap→Create→Init→Load. |
| G3 fail-closed default? | **Yes.** Absent/`false` stamp ⇒ Gate IF false ⇒ Sem0 path. No DB keys required. |
| G1 temptation? | Existing keys `hierarchy_experiment_enabled`, `hierarchy_product_allowlist` appear in **tooling** (`sem_smoke_patch_workflow.py`) but **not** in current Load SQL (still `WHERE false`). Reusing them for Sem-bypass gate would be **ambiguous/unsafe** (Load isolation ≠ Sem bypass). New `n1_presem_*` keys = separate approval; not in export. |

**Recommendation:** Prefer **G3** (stamp in temporary Init/Attach; default false). Use Mode A keys **only** for Load isolation, not as Sem-bypass gate.

### B. Batch=1 → `BATCH_1_INPUT_CONTRACT_CONFIRMED`

| Fact | Detail |
|---|---|
| Why N=0 got 5 | Cap: `requested == null` → `DEFAULT_LIVE_LLM_BATCH = 5`. CLI Manual `{}` has no `batch_size` / `requested_batch_size`. |
| Manual can supply 1? | Cap accepts `j.batch_size` or `j.requested_batch_size` or `j.body.batch_size` (positive int). **In principle yes** if input JSON has `batch_size: 1`. |
| CLI path | `n8n execute` starts Manual as `{}` (contract + N=0). pinData ignored. **CLI alone cannot pass batch_size without a temporary stamp/inject.** |
| Cap normalize | `effective = min(requested, 10)`; writes `batch_size = effective`. |
| Limit reads | `maxItems = {{ $('Run — Create Run').first().json.batch_size \|\| 5 }}` — uses **Create Run returned `batch_size`**, which was inserted from Cap effective. |
| Reset to 5? | Create SQL: `Number($json.effective_batch_size) \|\| Number($json.batch_size) \|\| 5`. If Cap outputs 1, Create stores 1; Limit uses 1. No later reset on Sem path. |
| G3 stamp sufficient for CLI? | **Yes, if stamp ensures Cap sees `batch_size:1` before Create** (Code before Cap, or temporary Cap force when `n1_presem_smoke_enabled`). Re-stamp not needed for batch after Create if Create persisted 1. |

**Future CLI N1-T contract (proposed):** temporary G3 force so Cap/Create/`batch_size=1` regardless of Manual `{}`; operator checklist still records intended request=1.

### C. Exact-ID Load → `EXACT_ID_LOAD_CONTRACT_PARTIAL`

**Current export SQL (exact):**

```sql
-- B2 skeleton stub: never drain pending pool
SELECT
  NULL::bigint AS product_id,
  NULL::bigint AS product_raw_id
WHERE false;
```

| Aspect | Current export | Proposed (NOT applied) |
|---|---|---|
| Tables/joins | none (null columns) | PROPOSED: `product_classification` ⋈ `classification_shortlist` per `SMOKE_LOAD_SQL` |
| Allowlist / experiment in Load | **not referenced** | PROPOSED: `pipeline_settings` keys in CTE |
| LIMIT | none | PROPOSED: `LIMIT {{ batch_size \|\| 5 }}` → for N1-T force batch=1 ⇒ LIMIT 1 |
| Exact ID predicate | n/a | PROPOSED insertion: `AND p.product_id = <approved>` **and/or** `= ANY(allowlist)` with allowlist length 1 |
| Safe `WHERE false` location | entire query predicate | Rollback restores this exact stub |

**Label PARTIAL:** current Load cannot load any ID; future exact-ID text is evidenced by repo tooling but **not** in live export; eligibility filters (`decision_status`, shortlist stage) may reject a chosen ID — needs future read-only dry-run (not done here).

### D. Stub→Route → `STUB_ROUTE_CONTRACT_CONFIRMED`

| Node | Exact fields read (export) | Required for N1-T | Default / behavior | Stub can satisfy? |
|---|---|---|---|---|
| Sem — Route | `$json.next_action` only | `=== direction_select` | else fallback → Prepare Log | **Yes** |
| Dir — Candidate Builder | spreads `...j`; builds empty scope | any item | `not_loaded_static`, `direction_static=true` | **Yes** |
| Dir — Prepare Payload | `run_id`, `product_id`, `product_raw_id`, `normalized_text`, kind/family/profiles, `attr_*`, `semantic_*`, `decision_status`, `next_action`, versions | ids + text preferred; semantic optional | null-tolerant | **Yes** with preserved upstream |
| Dir — Static Post-process | `direction_candidate_scope`, optional `direction_raw_response`, `cascade_trace`, `routing_hint` | empty static scope, no mock | null candidate; `stop_reason=need_not_implemented_static`; `next_action=need_select` | **Yes** (compatible) |
| Sem — Prepare Log | many `j.*`; `isDirection` if `stage===direction_select` \|\| `direction_static` | Direction path fields; `prompt_version` optional | fallback prompt `prompt_semantic_v2` | **Yes**; use `test_stub_no_llm_v1` |
| Insert Log | `$json.product_classification_log_insert.*` only | object from Prepare Log | — | **Yes** (via Prepare Log) |
| Fin — Pick Run | `$('Run — Create Run')` `id`/`batch_size` | `batch_size=1` ⇒ close after 1 barrier hit | staticData counter | **Yes** if batch=1 |
| Fin — Close Run | Create Run id; SQL on snapshot | — | status from snapshot counts | Path reachable; status OBSERVE |

**Norm — Normalize Sem attrs:** **safe to skip** on true seam — Route does not read it; only Sem Post feeds it today; Dir tolerates null `semantic_attrs`.

**semantic_attrs vs flat attr_*:** Dir Prepare uses **both** (`semantic_attrs` object and flat `attr_mnn` / form / route). Stub may set `semantic_attrs: {}` and flat nulls.

**Test markers in DB:** Prepare Log **does not** map `test_*` fields. Confirmed survival path **without Prepare Log edit:** put markers in `routing_hint` (copied to insert) and/or `direction_evidence` / explanation. Top-level `test_mode` on item alone **will not** land in log columns.

**Log events:** Stub skips Sem Post → **proposed one Direction-stage log**, not semantic_primary. Confirmed by path (no Sem Prepare from Sem Post).

**pairedItem:** Attach uses `pairedItem: index`; Stub should preserve `pairedItem` from input item.

### E. Barrier / Pick / Close → `LOG_ONLY_CLOSE_CONTRACT_CONFIRMED`

| Topic | Evidence |
|---|---|
| Barrier inputs | Upsert → index 0; Insert Log → index 1 |
| Snapshot required? | **No** for Sem/Dir — Prepare Snapshot only from P1/2B/Judge (unreachable). Notes: `append: Upsert + Insert` |
| Append alone | Intent documented; historical Sem log-only waves closed; N=0 used Empty Fin→Close (different path) |
| Pick | Counts barrier completions vs `run.batch_size`; with **1** emits Close once |
| Insert→Close | Insert → Barrier → Pick → Close **confirmed edges** |
| Close aggregates | `product_classification` where `latest_run_id=run_id` only — **not** logs |
| N=1 log-only status | **OBSERVE_ONLY** — with no snapshot update, SQL yields `total_count=0` → likely `finished_empty` |

### F. Fail-closed false branch + LLM hazard

```text
gate=false (default / absent stamp):
  Limit → Sem0 — Build Prompt → … Agents …  (EXACT current edge restored as false branch)
  No synthetic stub.

gate=true + all Stub checks pass:
  Stub → Sem Route → Dir → Log → Close

gate=true + check fail:
  Code throw (proposed); no Sem0
```

**Operator hazard (confirmed):** If Mode C Load returns a product and Gate stamp is false/missing, **false branch invokes Sem0/Sem1 LLM**.

**Safeguards (process only — not Code auto-block of Sem0):**

```text
- no run approval without static evidence: stamp enabled=true, mode, product_id, batch=1;
- Mode C+A only after T1 seam present with enabled planned true;
- operator checklist; stop immediately if Sem0 executes;
- do not leave Mode C Load active with seam disabled.
```

---

## 3. G3/G1 decision

```text
Recommend G3_STATIC_STAMP_FEASIBLE for Sem-bypass gate.
Mode A (existing settings keys) remains Load dual-control only.
Do not overload hierarchy_experiment_enabled as Sem bypass.
```

---

## 4. Manual CLI batch_size=1 contract

```text
Cap input fields: batch_size | requested_batch_size | body.batch_size
CLI Manual {}: → effective 5 (confirmed N=0)
Future N1-T CLI: temporary G3 force batch_size=1 into Cap (or Cap override when stamp enabled)
Limit/Create follow Cap effective when Create insert uses effective_batch_size
```

---

## 5. Load SQL + proposed insertion point

Current = exact stub in §2.C.  

**PROPOSED** (not applied): replace entire `Load — Select Batch` query with narrowed `SMOKE_LOAD_SQL` family:

```text
PROPOSED insertion points:
- keep settings CTE + experiment/allowlist guards;
- keep exact ID via allowlist length 1 AND/OR AND p.product_id = <id>;
- LIMIT driven by Create Run batch_size (=1 under N1-T);
- rollback = restore WHERE false stub byte-for-byte.
```

---

## 6. Stub field mapping (summary)

```text
Set: next_action=direction_select, decision_status=pending_fallback,
     selected_category_id=null, semantic_* null/empty,
     direction_static=true, stage=direction_select,
     prompt_version=test_stub_no_llm_v1,
     routing_hint={test_mode,test_synthetic_sem,test_fixture_version,llm_called:false}
Preserve: product_id, run_id, run_meta, normalized_text, Load shortlist fields, pairedItem
Forbid: category/final/classified, real candidates, real LLM metadata
Skip: Norm — Normalize Sem attrs
```

---

## 7. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Mode C Load + Gate false ⇒ LLM | **High** | Process lock; never open Load without enabled stamp |
| Create Run drops Cap-only stamps | Medium | Re-stamp in Init/Attach |
| test_* not in Prepare Log map | Medium | Use `routing_hint` / direction evidence |
| Close says finished_empty | Low | OBSERVE_ONLY; assert log row instead |
| Load eligibility rejects ID | High for run | Future dry-run before push |
| Barrier append vs empty params | Low | Notes + historical Sem; spot-check first run |

---

## 8. Blocking vs non-blocking

| Dependency | Blocks static T1 seam authoring? | Blocks N1-T run? |
|---|---|---|
| G3 stamp design | No — FEASIBLE | No |
| Batch=1 Cap contract | No — CONFIRMED | Need temporary force for CLI |
| Exact Load in export | N/A (separate Mode C patch) | **Yes** until Mode C+dry-run |
| Product eligibility | No | **Yes** (needs DB later) |
| Stub→Route fields | No — CONFIRMED | No |
| Log/Close path | No — CONFIRMED | Status observe-only |

---

## 9. Readiness

```text
N1_T_STATIC_PATCH_PARTIAL
```

**Meaning:** T1 seam + G3 + batch=1 force contracts are **evidence-backed and patchable**. Full N1-T remains partial until Mode C exact-ID SQL is approved and a product passes dry-run eligibility (DB not queried in this task).

Not `BLOCKED`: no hard contradiction prevents preparing the local T1 static patch design/implementation next.

Not `READY`: Load exact-ID eligibility and product dry-run unresolved without DB.

---

## 10. Future approval package (before any patch)

```text
1. T1 seam static patch (Gate IF + Stub + Init/Attach stamps + Cap batch force) — hierarchy-dev only
2. Temporary Mode C Load patch (exact ID + LIMIT via batch=1)
3. Mode A settings window (experiment + allowlist=[id]) — not G1 Sem-bypass keys
4. Selected product_id (owner) + read-only dry-run evidence
5. Push approval (hierarchy-dev only)
6. One CLI execution approval
7. Mandatory rollback approval / verification
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
