# Wave-500 Sem summary (hierarchy-dev)

- **Policy:** Sem0 `prompt_sem0_v3` + Sem1 `prompt_semantic_v4` + Norm attrs
- **Seed:** `sem_wave500_2026-08-04`
- **Allowlist:** `redesign/artifacts/sem_wave500_allowlist.json` (N=500)
- **Mode:** chunked 50×10 via `scripts/wave100_chunked_run.py` (resume after chunk 35 ECONNRESET)
- **Snapshot:** off (`upsert_snapshot_ran=false` on checked execs)
- **Prod:** untouched

## Progress

- processed **500 / 500** (100%)
- elapsed ≈ **27619 s** (~7.7 h wall)
- progress artifact: `redesign/artifacts/wave500_progress_summary.json`
- run log: `redesign/artifacts/sem_wave500_run.log`

## Kind mix

| product_kind | n |
|---|---|
| drug | 224 |
| vitamin_or_baa | 101 |
| cosmetic_hygiene | 75 |
| medical_device | 68 |
| other | 32 |

## Attr fill (non-empty)

| attr | filled |
|---|---|
| mnn | 97 |
| nosology | 300 |
| administration_route | 481 |
| dosage_form | 397 |
| age_segment | 499 |

## Artifacts

- `redesign/artifacts/sem_wave500_report.csv`
- `redesign/artifacts/sem_wave500_summary.json`
- `redesign/artifacts/wave500_progress_summary.json`
- `redesign/artifacts/sem_wave500_allowlist.json`
- `redesign/artifacts/sem_wave500_run.log`

Human labeling / gate scoring — separate step.
