# 42 — B4.3b-T N=1 pre-Sem seam/stub design (design only)

```text
Status: Design only — seam not implemented; N=1 not authorized.
Verdict: N1_T_PLAN_READY
Workflow: classification-stage2-hierarchy-dev
ID: o8sugljHYuUs7IEC
```

**Date:** 2026-09-12  
**Depends on:** `redesign/41_B4_3B_N1_NONEMPTY_RUNTIME_SMOKE_PLAN.md` (`N1_SMOKE_PLAN_PARTIAL`)  
**N=0 proof:** exec `42877` / run `474` / `N0_SMOKE_PASS`  
**Prompt authority:** Option A (`prompt_sem0_v2` / `prompt_semantic_v3`) — unchanged; stub uses **test** `prompt_version` only

---

## 1. Metadata and boundaries

| Field | Value |
|---|---|
| Document type | Design only |
| Implementation | **not** authorized |
| Runtime | **not** authorized |
| Allowed now | this Markdown file only |
| Forbidden now | workflow/nodes/Load/settings/DB/SQL/LLM/push/pull/Git |

---

## 2. Why N=1 plan is PARTIAL

Confirmed live non-empty path (post-push export):

```text
Empty? [false]
→ Attach → Norm Product → Limit
→ Sem0 Build → Sem0 LLM Prepare → Sem0 AI Agent (+ DeepSeek)
→ Sem Build → Sem LLM Prepare → Sem AI Agent (+ DeepSeek)
→ Norm Sem attrs → Sem Route
  [direction_select] → Dir Candidate → Dir Prepare → Dir Static Post
  → Sem Prepare Log → DB Insert Log → Fin Merge Barrier → Pick → Close
  [fallback] → Sem Prepare Log → …
```

Facts:

- Sem0/Sem1 **AI Agents are on the live edge** after Limit.
- Non-empty Close is **only** via Insert Log → Barrier → Pick → Close (Empty Fin is empty-only).
- No pre-Sem inject/seam exists (`Sem — Smoke Inject Bad JSON` **absent**).
- Load is still `WHERE false`; Mode A settings alone cannot load a product.

Therefore full N=1 → Direction → Log → Fin **requires either LLM (N1-L) or a new gated pre-Sem seam (N1-T)**.

---

## 3. Goals / non-goals

### Goals (future N1-T smoke, once implemented + approved)

```text
exactly one selected item
→ non-empty branch
→ run_id preserved
→ effective_batch_size=1 preserved
→ Norm Product path included (safe, already Code-only)
→ Sem0/Sem1 Agents bypassed only under explicit N1-T gate
→ synthetic Sem-compatible output clearly marked test-only
→ Sem Route with next_action=direction_select
→ Direction static zone once
→ no real candidate scope / no category_id
→ one Direction-shaped log event
→ no snapshot write
→ one terminal Close Run
→ final run status/metrics captured as observed
→ temporary Load/settings/seam rolled back and verified
```

### Non-goals

```text
- Sem LLM quality / real Sem attrs
- real categories_dict / Direction selection quality
- Need / Category / Mnn / Judge / Telegram
- N1-L authorization
- Wave-500 / production Stage 2
- permanent Sem bypass for normal hierarchy-dev runs
```

---

## 4. Existing confirmed topology (relevant)

| Element | Confirmed |
|---|---|
| `Sem — Route` | Switch on `$json.next_action == direction_select` → Dir; fallback → Prepare Log |
| Dir zone | Code-only; `candidate_scope_status=not_loaded_static`; no LLM; no `category_id` |
| Prepare Log | Direction-aware when `stage=direction_select` / `direction_static` |
| Insert Log | → `Fin — Merge Barrier` (input index 1) |
| Upsert Snapshot | Still wired into Barrier input 0 from **unreachable** Prepare Snapshot (P1/2B/Judge routes dark from Sem path) |
| Barrier hang risk | Historical Sem log-only waves completed with Snapshot dark → Barrier **appears** to accept Insert-only in practice; **exact Merge v3.2 mode = TO_CONFIRM** before N1-T runtime |
| `Fin — Pick Run` | Closes when barrier completions ≥ `batch_size`; with effective `1` → one Close |
| Cap | `Run — Apply Batch Cap`, `MAX_LIVE_LLM_BATCH=10`; N1-T requires request/effective **1** |

---

## 5. Proposed N1-T gate contract (fail-closed)

### Proposed controls

```text
proposed — requires separate settings/schema approval.
Do not assert these keys exist today.

n1_presem_smoke_enabled      boolean   default false
n1_presem_smoke_product_id   bigint    exact approved ID
n1_presem_smoke_mode         text      must equal "n1_presem_smoke"
```

**Storage locus (proposed alternatives — pick one in implementation approval):**

| Locus | Pros | Cons |
|---|---|---|
| `pipeline_settings` (like allowlist) | Auditable; matches Mode A tooling | Extra DB write window |
| Temporary Init Constants patch in workflow backup | Local to hierarchy-dev export | Requires workflow patch discipline |
| Hard-coded only in seam Code with settings mirror | Fast | Weaker ops visibility |

**Recommendation (proposed):** store the three keys in `pipeline_settings` **or** pass them via temporary Init Constants for the smoke window only — final choice = **TO_CONFIRM** at implementation approval. Gate logic is identical.

### Fail-closed conjunction (all must be true)

```text
1. workflow identity = classification-stage2-hierarchy-dev / o8sugljHYuUs7IEC
2. n1_presem_smoke_enabled === true
3. requested_batch_size == 1 AND effective_batch_size == 1
4. loaded product_id === n1_presem_smoke_product_id (approved)
5. n1_presem_smoke_mode === "n1_presem_smoke"
6. non-empty Load result count === 1
7. not production workflow (slug/id check)
8. no LLM mode flag enabled (explicit n1_presem implies llm_called=false;
   Sem Agents must be off-path)
```

### Mismatch behavior

```text
Any gate false on the N1-T branch:
→ do NOT emit synthetic Sem payload;
→ do NOT proceed to Direction;
→ do NOT call LLM;
→ preferred stop: throw Error in Code node
   (existing pattern in Empty Branch Gate / Ensure Empty Fin)
   with message including gate failure reason + run_id/product_id.

Whether a softer “Prepare Log system error then Close” path exists
without Snapshot/LLM = TO_CONFIRM.
Do not invent a new Fin edge in this design beyond throw-or-existing-contract.
```

**Critical:** when `n1_presem_smoke_enabled=false`, topology must route **only** to the normal Sem0 path (or remain Load-stub empty). The seam must **never** silently synthesize Sem output for ordinary runs.

---

## 6. Synthetic Sem-compatible payload contract

Minimal test-only fields sufficient for `Sem — Route` + Dir static + Prepare Log, and impossible to confuse with real Sem:

```json
{
  "test_mode": "n1_presem_smoke",
  "test_synthetic_sem": true,
  "test_fixture_version": "n1_presem_stub_v1",
  "llm_called": false,
  "semantic_validation_passed": true,
  "semantic_reject_reason": null,
  "semantic_confidence": null,
  "semantic_explanation": "n1_presem_stub_no_llm",
  "semantic_attrs": {
    "attr_mnn": null,
    "attr_dosage_form": null,
    "attr_administration_route": null
  },
  "decision_status": "pending_fallback",
  "next_action": "direction_select",
  "selected_category_id": null,
  "stage": "direction_select",
  "direction_static": true,
  "workflow_version": "hierarchy_n1_presem_smoke_v1",
  "prompt_version": "test_stub_no_llm_v1"
}
```

### Rules

```text
- spread ...item.json first; then overlay test fields (test markers win);
- preserve product_id, run_id / id, combined_text / source text fields present on item;
- preserve requested_batch_size, effective_batch_size, batch_cap_version;
- no guessed MNN / form / route / direction / need / category;
- never set category_id, final_category_id, final_source, classified;
- never claim real Sem0/Sem1 output;
- log payload must carry:
    test_synthetic_sem=true,
    test_mode=n1_presem_smoke,
    llm_called=false,
    candidate_scope_status=not_loaded_static
  (last via Dir Candidate Builder on path).
```

`prompt_version=test_stub_no_llm_v1` is **intentionally non-canonical** so logs cannot be mistaken for Option A live Sem evidence.

### Inject locus options

| # | Locus | LLM avoided? | Notes |
|---|---|---|---|
| 1 | Inject **immediately before** `Sem — Route` (after Norm Sem attrs) | **No** — Sem0/Sem1 still run | Reject for N1-T |
| 2 | **Branch before Sem0**, emit synthetic, converge to `Sem — Route` | **Yes** | Preferred |

**Safer: option 2.** Option 1 fails the no-LLM goal. Optional pass through `Norm — Normalize Sem attrs` after stub is **not** required for Route (`next_action` alone switches); skipping Norm Sem attrs reduces side-effect surface for N1-T (**proposed**).

---

## 7. Exact-ID dual-control Load design

N1-T is useless without one real product on the non-empty branch.

```text
REQUIRED conjunction (not either/or):

Mode C — temporary Load SQL:
  exact product_id predicate
  AND hard LIMIT 1
  (pattern family: scripts/sem_smoke_patch_workflow.py SMOKE_LOAD_SQL,
   narrowed to single ID — implementation detail under separate approval)

Mode A — temporary settings:
  hierarchy_experiment_enabled = true
  hierarchy_product_allowlist = { product_ids: [<same id>] }
```

### Selection invariant

```text
Loaded row count must equal exactly 1.
Loaded product_id must equal approved product_id.
Any 0 or >1 → block (no stub, no LLM, stop).
```

### Product criteria (no ID chosen here)

```text
- available under actual temporary Load join
  (confirmed smoke SQL family: product_classification ⋈ classification_shortlist;
   products_prepared = TO_CONFIRM if a different Load variant is proposed);
- stable ordinary product card / text;
- not in active production processing;
- no competing active classification run;
- not product_id=26346 for first N1-T;
- no external retrieval / MNN judgment required;
- safe for hierarchy-dev log-only.
```

### Conceptual read-only preflight checks (do not execute now)

```text
- identity: workflow name/id/active=false;
- baseline settings: experiment false, allowlist [];
- dry-run selection under proposed Load returns exactly 1 row for approved ID;
- product_classification + recent logs for that ID (conflict scan);
- no live hierarchy-dev / prod Stage 2 execution;
- after window: same checks for rollback proof.
```

Executable SQL text is **not** pasted here when the exact Load variant is still approval-scoped; use the proven Sem-smoke Load family as the reference implementation source.

---

## 8. Topology comparison and recommendation

| Option | Description | Safety | Fidelity | Rollback | Recommendation |
|---|---|---|---|---|---|
| **T1** | After Limit: IF N1-T gate → Stub Code → Sem Route; else → Sem0… | High if fail-closed + enabled default false | High for Dir/Log/Close; Sem LLM skipped by design | Remove IF/Stub edges; restore backup | **Proposed preferred** |
| **T2** | Let Sem run, replace output after Route | **Unsafe** for no-LLM; LLM already called | Misleading | Harder | **Reject** for N1-T |
| **T3** | Temporarily disconnect Sem Agent nodes | High risk of leaving bypass enabled; easy to forget reconnect | Opaque | Fragile | **Reject** |

**Non-binding recommendation (proposed): T1**

```text
Load (exact-ID+LIMIT1) → Empty Gate → Empty? [false]
→ Attach → Norm Product → Limit
→ IF N1-T all-gates
     [true]  → N1-T Stub Emit → Sem Route → Dir… → Prepare/Insert Log → Barrier → Pick → Close
     [false] → Sem0… (normal; must not be used while smoke enabled with mismatched ID —
               Stub/IF false with enabled=true and bad ID should not reach Sem0:
               use Stub/Code throw on enabled∧¬match rather than falling through to LLM)
```

**Refinement (proposed, mandatory for safety):**

```text
When n1_presem_smoke_enabled=true:
  - matching ID → Stub → Route → Dir → Log → Close
  - mismatch / count≠1 / batch≠1 → Code throw (no Sem0)
When n1_presem_smoke_enabled=false:
  - IF sends to Sem0 path (normal hierarchy-dev Sem behavior)
  - with Load WHERE false, this remains empty-safe (N=0 proven)
```

Never leave Agent nodes disconnected as the primary bypass mechanism.

**Runtime ops (proposed):** `active=false`; Manual-equivalent CLI (`n8n execute` as N=0); no webhook/activation.

---

## 9. Future change bundles (separated)

### Workflow (hierarchy-dev only, temporary)

```text
- add IF + Stub Code (names proposed, e.g. N1-T — Gate IF, N1-T — Stub Emit);
- rewire Limit outputs per T1;
- do NOT disconnect Sem Agents permanently;
- do NOT touch production Stage 2;
- backup JSON before patch; push only under approval; revert from backup after.
```

### Database / settings

```text
- temporary hierarchy_experiment_enabled=true;
- temporary allowlist=[approved_id];
- proposed N1-T keys enabled/product_id/mode (if locus=pipeline_settings);
- no new business columns required for MVP if Init Constants carries gate
  (TO_CONFIRM locus);
- no snapshot/attr_* writes expected.
```

### Load query

```text
- temporary Mode C exact-ID + LIMIT 1 replacing WHERE false;
- revert to WHERE false mandatory.
```

### Test data

```text
- one owner-approved product_id;
- selection evidence artifact before run.
```

### Runtime operation

```text
- one CLI execute; batch request=1;
- capture execution export + PG read-only checks;
- rollback Load+settings+workflow seam;
- verify safe defaults.
```

---

## 10. Preflight checklist (future)

```text
- approved product ID;
- fresh pull + intended seam SHA recorded;
- workflow remains inactive;
- Load temporary exact-ID+LIMIT1 applied only after approval;
- settings gate true only for one run window;
- allowlist exactly one approved ID;
- N1-T mode/product keys consistent (if used);
- effective batch=1;
- no live execution/zombie >30 min;
- no production workflow selected;
- prompt authority Option A remains documented (live Sem prompts untouched);
- backup + rollback artifacts ready;
- Barrier single-input behavior TO_CONFIRM reviewed against last Sem log-only evidence.
```

---

## 11. N1-T runtime assertions (future)

### Nodes

```text
- non-empty branch only; Empty Fin dark;
- Attach / Norm Product / Limit once;
- Sem0/Sem1 AI Agent + DeepSeek dark;
- N1-T Stub once; Sem Route once (direction_select);
- Dir Candidate / Prepare / Static Post once;
- Prepare Log + Insert Log once;
- Snapshot/Upsert dark;
- Pick + Close once;
- no Need/Cat/Mnn/Judge/Telegram;
- no LLM/HTTP.
```

### DB (read-only)

```text
- one new classification_runs row; run_id consistent;
- one product on path;
- one expected log event for designed stage (observe count);
- Direction/test markers: test_mode, test_synthetic_sem, llm_called=false,
  candidate_scope_status=not_loaded_static;
- selected_category_id null;
- no snapshot / latest_run_id / final_* updates;
- no unexpected classification_shortlist insert;
- status/counters recorded as observed;
- after rollback: Load WHERE false; experiment false; allowlist [];
  N1-T keys false/cleared; seam absent.
```

---

## 12. Stop / rollback conditions

**Stop/escalate if:**

```text
- wrong / 0 / >1 item;
- Sem Agent / LLM / HTTP executes;
- synthetic gate false but test path continues;
- Direction gets real candidates;
- category/final fields appear;
- Snapshot executes;
- >1 Close Run;
- log missing run_id / test markers;
- run does not finish;
- settings/Load/seam rollback cannot be proven;
- execution >30 minutes.
```

**Rollback:**

```text
- stop hung execution if needed;
- capture evidence;
- restore workflow from pre-seam backup (push);
- restore Load WHERE false;
- restore settings defaults;
- read-only verify;
- no automatic mid-flight graph rewrite;
- no repeat without new approval.
```

`N1_T_PASS` does **not** authorize N1-L or Wave-500.

---

## 13. Evidence artifacts (after future run — names only)

```text
redesign/artifacts/b4_3b_n1_runtime_smoke_plan_selection_evidence_v1.md
redesign/artifacts/b4_3b_n1_t_runtime_smoke_run_<run_id>_v1.md
redesign/artifacts/b4_3b_n1_t_runtime_smoke_run_<run_id>_v1.json
redesign/artifacts/b4_3b_n1_t_runtime_smoke_execution_export_<execution_id>.json
redesign/artifacts/b4_3b_n1_t_runtime_smoke_pg_check_<run_id>.md
redesign/artifacts/b4_3b_n1_t_runtime_smoke_rollback_check_<timestamp>.md
```

---

## 14. Pass/fail criteria (this design document)

```text
N1_T_PLAN_READY
```

Design is complete enough for **implementation authorization review**: recommended T1 topology, fail-closed gate, synthetic payload, dual Load control, rollback, and explicit LLM avoidance. Remaining items are labeled TO_CONFIRM, not silent assumptions.

```text
N1_T_PLAN_PARTIAL — would apply if gate fail-stop or Barrier behavior were left unspecified.
N1_T_PLAN_BLOCKED — would apply if no safe topology existed without Agent disconnect.
```

---

## 15. Exact next authorization boundary

Before any code/node change:

```text
1. Approve this N1-T design (T1) for hierarchy-dev only.
2. Approve gate storage locus (pipeline_settings vs Init Constants).
3. Approve temporary workflow seam patch + push + mandatory revert.
4. Approve Mode C Load + Mode A settings window for one product_id.
5. Approve exact product_id.
6. Approve one CLI N1-T run (still a separate message after patch is live).
```

N1-L (real Sem LLM) remains a **separate** track and is **not** unlocked by this document.

---

## 16. TO_CONFIRM

| Item | Note |
|---|---|
| Gate key storage locus | `pipeline_settings` vs Init Constants |
| Exact Merge Barrier v3.2 behavior with Snapshot silent | Historically OK on Sem log-only; re-verify |
| Softer-than-throw gate-fail Close path | Prefer throw; alternate = TO_CONFIRM |
| Exact temporary Load SQL text | Derive from `sem_smoke_patch_workflow.py` under approval |
| Whether Stub should pass `Norm — Normalize Sem attrs` | Proposed: skip |
| Node naming / sticky note | Implementation detail |
| `products_prepared` | Not in current smoke Load family |

---

## 17. Explicitly not changed

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

---

## This document does not authorize

```text
- seam implementation;
- Load patch;
- settings/allowlist write;
- N=1 run;
- LLM;
- activation/webhook;
- Need;
- real categories_dict;
- snapshot;
- Wave-500;
- production changes.
```
