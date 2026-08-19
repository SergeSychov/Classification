# M4.2.1 — Reviewed Age threshold reconciliation contract v1

**Status:** AUDIT / REVIEWED MAPPING ONLY. Not applied. Not a routing gate.
**Date:** 2026-08-19
**Policy version:** `age_threshold_reconciliation_reviewed_v1`
**Depends on:** M4.2 reconciliation + labelled follow-up.

```text
Age threshold and age segment are separate.
12/14/15/16+ is not adults-only if child+adult scope is confirmed.
This remains manual/audit-only and is not a DB/routing update.
```

## Merge policy

1. Valid completed follow-up → reviewed manual mapping after M4.2 contract rules.
2. No follow-up requirement → keep M4.2 deterministic result.
3. Invalid vocabulary or unresolved contract conflict → do not invent;
   output `unknown` or `conflict`, `needs_manual_reconciliation=true`.

Values outside `{0,1,2,3,6,12,14,15,16,18,unknown}` are **not** normalized
(e.g. `10` stays invalid and is not mapped to 6 or 12).

## Isolation

```text
offline reviewed reconciliation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```
