# M4.2 — Age threshold mapping v1

**Status:** AUDIT ONLY. Not applied. Not a routing gate. Not a DB write.
**Date:** 2026-08-19
**Policy version:** `age_threshold_reconciliation_v1`
**Depends on:** labelled Age pilot sample from M4.1.1; M4.0 Age contract.

This document separates **age threshold** from **age segment**.
Machine reconciliation: [`artifacts/mnn_age_threshold_reconciliation_v1_summary.md`](artifacts/mnn_age_threshold_reconciliation_v1_summary.md).

---

## Contract (mandatory)

```text
- Age threshold is separate from Age segment.
- 12/14/15/16+ is not adults-only by default.
- 18+ or explicit adult-only => adults.
- 0/1/2/3/6+ with adult use => universal.
- children-only needs explicit pediatric-only evidence.
- unknown is valid.
- This contract is audit-only; no DB/routing use.
```

## Fields

| Field | Role |
|---|---|
| `age_min_years` / `manual_age_min_years` | Factual minimum from instruction or reviewer note |
| `age_segment` / `manual_age_segment_reconciled` | Coarse routing/display label |

`age_min_years` 12/14/15/16 does **not** mean `взрослые` automatically.

If a product is allowed from 12+ and is used in adults:

```text
age_segment = универсальный
age_min_years = 12
```

`взрослые` applies only when:

- 18+;
- explicit adult-only;
- explicit children not allowed.

## Mapping rules

### A. Adult-only / `взрослые`

Only with explicit `с 18 лет` / `18+` / `только взрослым` / children
contraindicated phrasing, or reviewer notes that establish adult-only
without a 12–16 threshold. Bare reviewer wording `Взрослый с 12 лет`
is **not** adult-only.

### B. Adolescent + adult / `универсальный`

`с 12 / 14 / 15 / 16 лет` and no adult-only marker →
`adolescent_plus_adult`, scope `children_and_adults`.

### C. Child + adult / `универсальный`

`с 0 / рождения / 1 / 2 / 3 / 6 лет` and adult use not excluded →
`children_plus_adult`.

### D. Children-only / `дети`

Only with explicit pediatric-only evidence
(`только для детей`, `детский препарат`, adult use not claimed).
A minimum below 18 is not enough.

### E–G. Labels without a usable threshold

- `should_be_adults` without 18+/adult-only wording → segment `unknown`,
  `needs_threshold_confirmation`. Do not keep `should_be_adults` as the
  structured segment.
- `should_be_universal` without a numeric min → provisional `универсальный`,
  `needs_threshold_review=true`. Do not invent a year.
- `confirm_unknown` / `confirm_conflict` → retain those segments. No
  invented threshold.

## Isolation

```text
offline reconciliation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```
