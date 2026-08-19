# M4.2.2 — Reviewed Age threshold reconciliation contract v1.1

**Status:** AUDIT / REVIEWED MAPPING ONLY. Not applied. Not a routing gate.
**Date:** 2026-08-19
**Policy version:** `age_threshold_reconciliation_reviewed_v1_1`
**Depends on:** M4.2 reconciliation + labelled follow-up. Does not overwrite v1.

```text
reviewed_age_min_years:
any integer 0..18 | unknown | null

Age threshold and age segment are separate.
12/14/15/16+ is not adults-only if child+adult scope is confirmed.
10 + children_and_adults => универсальный (not remapped to 6 or 12).
Adults only requires min=18 or explicit adult-only note.
Children-only requires explicit children-only note.
This remains manual/audit-only and is not a DB/routing update.
```

## Merge policy

1. Valid completed follow-up → reviewed manual mapping after M4.2 contract rules.
2. No follow-up requirement → keep M4.2 deterministic result.
3. Invalid vocabulary or unresolved contract conflict → do not invent;
   output `unknown` or `conflict`, `needs_manual_reconciliation=true`.

No threshold is remapped to another threshold.

## Isolation

```text
offline reviewed reconciliation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```
