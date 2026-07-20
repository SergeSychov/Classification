# Experiment isolation design — §13.3 (S4)

Date: 2026-07-20  
Status: **design only** — no `INSERT` into `pipeline_settings`, no workflow Load edits, no DDL.  
Related: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md) §2 / §13.3, [`21a_SCHEMA_DUMP.md`](21a_SCHEMA_DUMP.md), [`00_PROJECT_STATUS.md`](00_PROJECT_STATUS.md).

---

## Problem

Prod Stage 2 (`classification-stage2-dev`) loads:

```sql
-- conceptual (current Load — Select Batch)
FROM product_classification p
JOIN classification_shortlist s ON s.product_id = p.product_id
WHERE p.decision_status = 'pending'
  AND p.rule_decision_status IN ('needs_llm', 'no_match')
  AND (s.stage IS NULL OR s.stage = 'primary_rules')
ORDER BY random()
LIMIT :batch_size;
```

A future hierarchy clone (`classification-stage2-hierarchy-dev`) that uses the same predicate will race on:

- `product_classification` snapshot / `latest_run_id` (terminal upsert)
- shared `pending` pool eligibility
- ops interpretation of which run “owns” a product

Isolation must make hierarchy batches **opt-in** and, when prod Load is later patched, **excluded from prod**.

---

## Locked v1 mode: allowlist

| Decision | Value |
|----------|--------|
| Mode | **`allowlist`** |
| Storage | Existing `pipeline_settings` (`key text PK`, `value jsonb`) — confirmed in schema dump |
| Tag column on `product_classification` | **Not in v1** (needs DDL → defer) |
| Percent hash split | **Not default** (overlap risk) |

---

## Proposed `pipeline_settings` keys (not inserted yet)

| key | value JSON (draft) | Purpose |
|-----|--------------------|---------|
| `hierarchy_experiment_enabled` | `{"value": false}` | Global kill switch for hierarchy Load |
| `hierarchy_load_mode` | `{"mode": "allowlist"}` | Frozen mode string; only `allowlist` supported in v1 |
| `hierarchy_product_allowlist` | `{"product_ids": []}` | Explicit bigint IDs for Sem waves 100/500/1000 and cascade smokes |
| `hierarchy_exclude_from_prod_stage2` | `{"value": true}` | Intent flag: when true, **future** prod Stage 2 Load must exclude allowlist IDs |

**Defaults when keys missing:** treat as `enabled=false`, `mode=allowlist`, `product_ids=[]`, `exclude_from_prod=true` (safe: hierarchy loads nothing; prod unchanged until patched).

---

## Load predicates (design)

### Hierarchy workflow Load (future clone)

```sql
-- only when hierarchy_experiment_enabled.value = true
-- and hierarchy_load_mode.mode = 'allowlist'
-- and allowlist non-empty

WHERE p.decision_status = 'pending'
  AND p.rule_decision_status IN ('needs_llm', 'no_match')
  AND (s.stage IS NULL OR s.stage = 'primary_rules')
  AND p.product_id = ANY (
    SELECT jsonb_array_elements_text(value->'product_ids')::bigint
    FROM pipeline_settings
    WHERE key = 'hierarchy_product_allowlist'
  )
ORDER BY random()  -- or preserve allowlist order if preferred later
LIMIT :batch_size;
```

If `hierarchy_experiment_enabled` is false **or** allowlist empty → Load returns 0 rows (finish empty run safely).

### Prod Stage 2 Load (future patch — not §13 work)

When `hierarchy_exclude_from_prod_stage2.value = true` **and** allowlist non-empty:

```sql
-- append to existing WHERE
AND p.product_id <> ALL (
  SELECT jsonb_array_elements_text(value->'product_ids')::bigint
  FROM pipeline_settings
  WHERE key = 'hierarchy_product_allowlist'
)
```

Until that patch exists, prod Load is unchanged.

---

## Interim ops rule (until prod Load is patched)

**Operational constraint:** do not run hierarchy batches on `product_id`s that are concurrently eligible for a live prod Stage 2 drain, unless those IDs are allowlisted **and** prod processing of the same IDs is paused / already terminal.

Practical Sem validation waves:

1. Build allowlist of N random eligible `product_id`s (seeded).
2. Optionally set those rows aside from overnight drain (ops pause) **or** choose IDs already not in the hot pending queue.
3. Run hierarchy only with `hierarchy_experiment_enabled=true` and that allowlist.
4. Do not enable hierarchy on full `pending` pool.

This interim rule is enough to clear §13.3 “agree isolation design” without touching prod workflow yet.

---

## Allowlist lifecycle (Sem 100 / 500 / 1000)

| Wave | N | How allowlist is filled (later, not now) |
|------|---|------------------------------------------|
| V1 | 100 | Random eligible IDs → write `product_ids` array |
| V2 | 500 | New or extended list; store wave id in run `metadata` |
| V3 | 1000 | Same |

Store wave seed + `run_id` in `classification_runs.metadata` when hierarchy runs exist. Keep allowlist in `pipeline_settings` as the Load source of truth.

---

## Rejected / deferred alternatives

| Mode | Why not v1 |
|------|------------|
| `tag` column / flag on snapshot | Requires ALTER (B1 territory); heavier than settings |
| `percent` hash | Silent overlap with prod; hard to audit which IDs ran |
| Separate DB schema / table copy | Overkill for experiment |
| Exclude-only without allowlist | Hierarchy could still grab “everything not tagged” incorrectly |

---

## What §13 does **not** do

- No `INSERT`/`UPDATE` of the four keys into live `pipeline_settings`
- No change to `classification-stage2-dev` Load SQL
- No creation of hierarchy workflow
- No claim that isolation is “active in production”

Activation = separate explicit task after B2 clone exists.

---

## Sign-off checklist (§13.3)

- [x] Mode locked: **allowlist**
- [x] Key names frozen (table above)
- [x] Hierarchy Load predicate drafted
- [x] Prod exclude predicate drafted (future)
- [x] Interim ops rule documented
- [ ] Keys inserted in DB — **deferred** (not required to clear design agreement)
- [ ] Prod Load patched — **deferred**

**S4 complete** when this file is accepted as the isolation contract.
