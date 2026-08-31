# Wave-100 Sem validation — policy v2 rerun (Sem0 + Sem1)

**Seed:** `sem_wave100_2026-07-30_policy_v2`  
**N:** 100 (same product_ids as exec 19932 allowlist)  
**Mode:** chunked `10×10` (`scripts/wave100_chunked_run.py`) — single N=100 hang on Sem0/Sem1 Merge+parallel LLM  
**Executions:** `21611, 21617, 21622, 21627, 21632, 21637, 21642, 21648, 21653, 21659`  
**Prompts:** `prompt_sem0_v2` + `prompt_semantic_v3`  
**Snapshot:** off · **Prod Stage 2:** untouched · **Rollback:** Load `WHERE false`, kill switch off, allowlist `[]`

## Progress / ETA

Artifact: `redesign/artifacts/wave100_progress_summary.json`  
Tooling: `scripts/wave_progress.py` (+ chunked runner prints `processed X/N`, `%`, ETA per remaining chunks).

## Kind mix (Sem0)

| product_kind | count |
|---|---|
| drug | 44 |
| vitamin_or_baa | 19 |
| medical_device | 18 |
| cosmetic_hygiene | 13 |
| other | 6 |

## Attr coverage (model output, not human rubric)

| attr | non-null / 100 |
|---|---|
| mnn | 42 |
| nosology | 53 |
| rx_otc | 39 |
| administration_route | 73 |
| dosage_form | 73 |
| dosage | 49 |
| package_hint | 98 |

## Policy spot-checks

| product_id | kind | note |
|---|---|---|
| 254 ватные палочки | medical_device/hygiene-like | pharma attrs null; package filled |
| 1347 шприц | medical_device clinical | form/route/dosage filled; mnn/nosology null |
| 1623 Черника Форте | vitamin_or_baa | nosology=`нутрицевтики`, form/route filled; rx_otc null |
| 11225 Нордепласт | medical_device | route=`наружно`, form=`пластырь` |
| 9335 подорожник | drug | mnn/nosology/route/form/dosage filled |

## Human rubric

Gate `critical_error_rate` still needs labels in `label_*` columns.  
Rubric note updated: `redesign/artifacts/sem_wave100_report_template.rubric.txt` (BAA/device evidencing rules).

Historical pre-Sem0 CSV archived: `sem_wave100_report_exec19932_pre_sem0.csv`.
