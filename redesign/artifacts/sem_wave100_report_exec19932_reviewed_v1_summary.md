# Wave-100 Sem human rubric — exec19932 freeze v1

**Date:** 2026-09-09
**Source wave:** pre-Sem0 exec **19932** / hierarchy `run_id=307` (NOT policy_v2 `sem_wave100_report.csv`)
**Gate:** `PASS`
**critical_error_rate:** 1/171 = **0.58%** (threshold < 15%)

## Scope note

Labeled file matches `sem_wave100_report_exec19932_pre_sem0.csv` on critical attrs / text / run_id.
It does **not** label the later Sem0+policy_v2 rerun (`sem_wave100_report.csv`, runs 317–326).
`product_kind` / `medical_device_profile` joined from policy_v2 export by `product_id` for non-critical route/form filter only.

## Metrics

```text
critical_errors = incorrect + missing_should_exist = 1
evidenced_key_attr_cases = correct + incorrect + missing_should_exist = 171
critical_error_rate = 0.0058
skipped non-critical route/form cells = 40
```

| attr | errors | evidenced | rate | labels |
|------|-------:|----------:|-----:|--------|
| mnn | 0 | 35 | 0.00% | {'correct': 35, 'not_applicable': 50, 'unknown_acceptable': 15} |
| dosage_form | 1 | 69 | 1.45% | {'correct': 68, 'not_applicable': 10, 'unknown_acceptable': 1, 'incorrect': 1} |
| administration_route | 0 | 67 | 0.00% | {'correct': 67, 'not_applicable': 12, 'unknown_acceptable': 1} |

## Critical error rows

- `26346` dosage_form=`incorrect` value=`фиточай` kind=`vitamin_or_baa` — АЛТАЙ №7 ЗДОРОВЫЕ СОСУДЫ С МЕЛИССОЙ ФИТОЧАЙ Ф/П 2Г №20 | АЛТАЙСКИЙ КЕДР ООО | АЛТАЙСКИЙ КЕДР ООО

## Hygiene

- Mapped `unknown` → `unknown_acceptable` on critical labels: **18** cells.
- Restored baseline body from pre-Sem0 (`True`/`true` casing).
- Did **not** overwrite `sem_wave100_report.csv` or `sem_wave100_report_exec19932_pre_sem0.csv`.

## Gate checklist

- critical_error_rate < 15%: **yes** (0.58%)
- Sem contract category/direction/need absent: **yes** (`selected_category_id` empty; next_action=direction_select)
- snapshot-off / prod untouched: **yes** (historical)
- rollback verified: **yes** (historical п.28)

## Artifacts

| File | Role |
|------|------|
| `sem_wave100_report_exec19932_pre_sem0.csv` | Baseline unlabeled export |
| `sem_wave100_report_exec19932_human_review_labeled_2026-09-09.csv` | As-received labels |
| `sem_wave100_report_exec19932_reviewed_v1.csv` | Freeze + kind enrich |
| `sem_wave100_report_exec19932_reviewed_v1_summary.md` | This summary |

## Next

- Treat Wave-100 gate as **PASS** for exec19932 scope.
- Before Wave-500: optional spot-check / re-label on policy_v2 export, or accept transfer with explicit note.
- B4 Direction+Need soft design may proceed after explicit ask.

