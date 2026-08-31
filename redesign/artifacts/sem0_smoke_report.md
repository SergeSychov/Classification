# Sem0 smoke report (2026-07-30)

**Execution:** n8n `21504`  
**Seed / wave:** `sem0_smoke_2026-07-30`  
**N:** 9  
**Sem0+Sem1:** both agents ran; `upsert_snapshot_ran=false`  
**Rollback:** Load `WHERE false`; kill switch off; allowlist `[]`; prod Stage 2 untouched

## Product IDs

`254, 1347, 1623, 5597, 6117, 6168, 9249, 9335, 11225`

## Results (Sem1 after attr_profile / non-drug enforce)

| product_id | product_kind | product_family | pharma attrs | brand / package |
|---|---|---|---|---|
| 254 ватные палочки | cosmetic_hygiene | null | all null | Я САМАЯ / 200 шт в стакане |
| 1347 шприц | medical_device | Приборы и средства для инъекций | all null | VOGT MEDICAL |
| 1623 Черника Форте | vitamin_or_baa | Зрение | all null (non-drug enforce) | Черника Форте… / 45 капсул |
| 5597 кислородная вода | other | null | all null | Стэлмас / 0.6 л ПЭТ |
| 6117 соль для ванн | cosmetic_hygiene | null | all null | package 1 кг |
| 6168 ватные диски | cosmetic_hygiene | null | all null | Солнце и Луна Eco / 40 шт |
| 9249 поильник | other | null | all null | ПОМА / 180 мл |
| 9335 подорожник | drug | Травы | rx_otc/route/form/dosage filled; mnn null | Фито-Бот / 20 ф/п |
| 11225 Нордепласт | medical_device | Пластыри | all null (non-drug hard rule) | НОРДЕПЛАСТ / 50x70 мм №2 |

Pharma keys forced null when `product_kind != drug`:  
`mnn`, `rx_otc`, `nosology`, `administration_route`, `dosage_form`, `dosage`, `combination_hint`.

## Artifacts

- `redesign/artifacts/sem0_smoke_report.csv`
- `redesign/artifacts/sem0_smoke_report.summary.json`
- `redesign/artifacts/sem0_smoke_analysis.json`
- `redesign/artifacts/sem_smoke_sem0_smoke_allowlist.json`
- `redesign/artifacts/sem_chain_nodes_current.json`
