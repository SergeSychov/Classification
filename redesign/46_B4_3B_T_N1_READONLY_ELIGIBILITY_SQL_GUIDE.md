# 46 — B4.3b-T.4 N1-T read-only eligibility SQL guide

```text
Status: Design / operator guide only — SQL package not executed in this task.
Package: sql/b4_3b_t_n1_readonly_eligibility_package_v1.sql
Parameters: redesign/artifacts/b4_3b_t_n1_eligibility_parameters_template_v1.json
```

**Date:** 2026-09-12  
**Workflow context:** `classification-stage2-hierarchy-dev` / `o8sugljHYuUs7IEC`  
**Current Load:** stub `WHERE false` (no product joins)

---

## 1. Scope and non-goals

**In scope**

- SELECT-only discovery and eligibility evidence in pgAdmin
- Candidate listing for owner review
- Exact-ID proof after owner names an ID
- Conflict/isolation evidence before any Mode C patch

**Non-goals**

- Choosing `product_id` in this task
- Executing Mode C Load / seam / settings / push / N1-T run / LLM
- Inventing `products_prepared` column lists without discovery

---

## 2. File to open in pgAdmin

```text
sql/b4_3b_t_n1_readonly_eligibility_package_v1.sql
```

Run **one section at a time**. Do not “execute entire file” blindly if the client stops on `:approved_product_id` placeholders.

For parameterized sections, replace `:approved_product_id` with an owner-approved **literal bigint** (pgAdmin often does not bind `:name` like app drivers).

---

## 3. Safety rules

```text
- SELECT / information_schema / pg_catalog only
- No INSERT/UPDATE/DELETE/MERGE/TRUNCATE/DDL
- No SELECT … FOR UPDATE
- No temp tables / write functions
- Do not pick a product without separate owner approval
- Successful eligibility ≠ authorization for seam/Load/settings/push/run
```

---

## 4. Required execution sequence

1. **Section 1 — Schema discovery**  
   Confirm which of `products_prepared`, `products_raw`, `classification_review_queue`, `categories_raw` exist and their columns.  
   Confirm `pipeline_settings` hierarchy keys.

2. **Section 2 — Candidate discovery**  
   Review ≤50 Sem-smoke-family candidates (and prod-isolated subset).  
   **Stop.** Owner picks at most one ID outside this agent task if desired.

3. **Owner chooses one candidate** (separate approval).

4. **Section 3 — Exact-ID proof** with that literal ID  
   Expect `product_classification` count = 1; primary_rules shortlist with text = 1.

5. **Section 5 — Conflict / isolation**  
   Running runs, recent logs, prod Stage 2 24h hits, hierarchy logs.

6. **Section 6 — Preflight evidence record**  
   Fill `b4_3b_t_n1_eligibility_parameters_template_v1.json` from results.  
   Set `candidate_eligible` only if Section 6 flag is true **and** isolation checks pass.

7. **Stop before any Mode C patch / seam / push / run.**  
   Section 4.3 and Section 7 remain blocked.

---

## 5. Acceptance / rejection criteria

**Accept (Sem-smoke family baseline)** when all hold:

```text
- product_classification row count = 1
- primary_rules shortlist with non-empty combined_text count = 1
- decision_status IN (pending, needs_human_review)
- rule_decision_status IN (needs_llm, no_match)
- product_id ≠ 26346
- prod Stage 2 log hits 24h = 0 (preferred)
- no operational conflict from live running runs / owner policy
- combined_text looks ordinary (manual eyeball; no phytotea/alias mess)
```

**Reject** if join count ≠ 1, text empty, excluded ID, hot prod activity, or owner flags sensitivity.

**Note:** ALLOWLIST_WIDE / classified rows need a **separate** Mode C design approval — not this package’s default accept path.

---

## 6. What to save

```text
- Section 1 result grids (tables/columns present)
- Section 2 shortlist of candidates considered
- Section 3/5/6 grids for the approved ID
- Filled parameters JSON copy under redesign/artifacts/ (future, after dry-run approval)
- Optional screenshots of counts = 1
```

Do not paste secrets/credentials.

---

## 7. What to bring back for review

```text
- confirmed tables present/missing vs 21a
- candidate_eligible true/false + ineligibility_reason
- approved_product_id (only if owner already approved naming it)
- prod_stage2_log_hits_24h
- global_running_runs_count
- shortlist/text evidence
- any schema adaptations required (TO_CONFIRM resolved)
```

---

## 8. Authorization boundary

```text
Successful read-only eligibility checks do not authorize:
seam patch, Load patch, settings writes, push, N1-T run, LLM, or Wave-500.
```

---

## 9. TO_CONFIRM / schema adaptation

| Item | Note |
|---|---|
| `products_prepared` / `products_raw` columns | Not in `21a_SCHEMA_DUMP.md`; discover in §1; then add exact-once counts |
| `classification_review_queue` columns | Attested in plan/SQL migrations; not in 21a dump; discover before open-queue count |
| `categories_raw` | Attested in plan inventory; not needed for Sem-smoke join |
| Live `pipeline_settings` hierarchy keys | Documented in `22_EXPERIMENT_ISOLATION.md`; verify via §1.5 |
| Future Mode C exact SQL | Must match approved Load patch text — §4.3 blocked until then |
| Normalized text | Live Sem Load uses `classification_shortlist.combined_text`, not a PC `normalized_text` column |

If discovery shows renamed/missing columns, **stop** and adapt package as `_02` — do not invent.

---

## 10. Confirmed vs TO_CONFIRM usage in package

**Confirmed (21a) and used in executable SELECTs:**

```text
product_classification.* (listed dump columns)
classification_shortlist.* (listed dump columns)
product_classification_log.* (listed dump columns)
classification_runs.* (listed dump columns)
pipeline_settings (key, value, updated_at)
```

**Discovery-first / TO_CONFIRM:**

```text
products_prepared, products_raw, classification_review_queue, categories_raw
```

---

## Explicitly not changed

- n8n workflows: not changed
- n8n runtime/executions/webhooks: not run
- PostgreSQL schema/data: not changed
- SQL: not executed (package authored only)
- production Stage 2: not changed
- hierarchy-dev runtime settings: not changed
- Load / allowlist / kill switch: not changed
- snapshot / attr_*: not changed
- Sem0/Sem1 prompts and prompt versions: not changed
- real categories_dict data: not loaded
- Need / Category / Mnn / Judge / Telegram: not added
- source and freeze evidence artifacts: not changed
- Git commit/push: not performed
