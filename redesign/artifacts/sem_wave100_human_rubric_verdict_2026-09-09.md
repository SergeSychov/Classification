# Wave-100 Sem human rubric — verdict

**Date:** 2026-09-09
**Artifact:** `sem_wave100_report_reviewed.csv` (Downloads) → freeze `sem_wave100_report_exec19932_reviewed_v1.*`
**Wave scope:** pre-Sem0 exec **19932** / run_id **307**

## Verdict

```text
gate = PASS
critical_error_rate = 1/171 = 0.58%
threshold = 15%
```

Единственная critical ошибка: `product_id=26346` dosage_form=`фиточай` → `incorrect` (vitamin_or_baa).

## Caveat

Размечен pre-Sem0 экспорт, не policy_v2 Sem0+Sem1 rerun. Для Wave-500 рекомендуется либо точечный spot-check policy_v2, либо явная фиксация transfer-of-gate.

## Isolation

```text
offline rubric only; no n8n/DB/attr/snapshot/prod changes.
```

