# Wave-100 v2 human rubric analysis

Source: `sem_wave100_report_markt.csv` (N=100, read-only).  
Policy reference: journal п.29–30 (Sem0/Sem1 policy v2).  
**No workflow/prompt changes in this task.**

## How CSV was read

- Attr values: `attr_*` columns.
- Labels: `label_*` including `label_product_kind`.
- No free-text `note` column; expectations often encoded as `incorrect / <expected>` (e.g. `incorrect / Метформин`).
- Typo `incorrcet` normalized to `incorrect`.
- **`missing_should_exist` almost unused** (0 in practice) — treated as part of incorrect when annotator put expected after `/`.

Kind mix (Sem0): drug 44 · vitamin_or_baa 19 · medical_device 18 · cosmetic_hygiene 13 · other 6.

## Overall metrics

| field | correct | incorrect | unknown_acceptable | missing_should_exist | c% | i% |
|---|---:|---:|---:|---:|---:|---:|
| product_kind | 94 | 6 | 0 | 0 | 94.0 | 6.0 |
| mnn | 39 | 10 | 51 | 0 | 39.0 | 10.0 |
| brand | 90 | 7 | 3 | 0 | 90.0 | 7.0 |
| rx_otc | 35 | 8 | 57 | 0 | 35.0 | 8.0 |
| nosology | 49 | 10 | 40 | 0 | 49.0 | 10.0 |
| administration_route | 73 | 8 | 19 | 0 | 73.0 | 8.0 |
| dosage_form | 70 | 5 | 25 | 0 | 70.0 | 5.0 |
| dosage | 48 | 2 | 50 | 0 | 48.0 | 2.0 |
| age_segment | 30 | 17 | 53 | 0 | 30.0 | **17.0** |
| package_hint | 92 | 5 | 1 | 0 | 92.0 | 5.0 |
| combination_hint | 19 | 2 | 79 | 0 | 19.0 | 2.0 |

## By product_kind (selected)

| field | product_kind | n | correct | incorrect | unknown | c% | i% |
|---|---|---:|---:|---:|---:|---:|---:|
| product_kind | drug | 44 | 40 | 4 | 0 | 90.9 | 9.1 |
| product_kind | vitamin_or_baa | 19 | 19 | 0 | 0 | 100 | 0 |
| product_kind | medical_device | 18 | 17 | 1 | 0 | 94.4 | 5.6 |
| product_kind | cosmetic_hygiene | 13 | 13 | 0 | 0 | 100 | 0 |
| product_kind | other | 6 | 5 | 1 | 0 | 83.3 | 16.7 |
| mnn | drug | 44 | 30 | 8 | 6 | 68.2 | **18.2** |
| mnn | vitamin_or_baa | 19 | 9 | 0 | 10 | 47.4 | 0 |
| nosology | drug | 44 | 32 | 7 | 4 | 72.7 | 15.9 |
| nosology | vitamin_or_baa | 19 | 17 | 2 | 0 | 89.5 | 10.5 |
| rx_otc | drug | 44 | 35 | 7 | 2 | 79.5 | 15.9 |
| rx_otc | vitamin_or_baa | 19 | 0 | 0 | 19 | 0 | 0 |
| administration_route | drug | 44 | 44 | 0 | 0 | **100** | 0 |
| administration_route | vitamin_or_baa | 19 | 19 | 0 | 0 | **100** | 0 |
| administration_route | medical_device | 18 | 10 | 0 | 8 | 55.6 | 0 |
| administration_route | cosmetic_hygiene | 13 | 0 | 7 | 6 | 0 | **53.8** |
| dosage_form | drug | 44 | 43 | 1 | 0 | 97.7 | 2.3 |
| dosage_form | vitamin_or_baa | 19 | 19 | 0 | 0 | **100** | 0 |
| package_hint | vitamin_or_baa | 19 | 19 | 0 | 0 | **100** | 0 |
| age_segment | drug | 44 | 18 | 11 | 15 | 40.9 | **25.0** |

## product_kind errors (6)

| id | Sem0 | expected (from label) | text (short) | group |
|---|---|---|---|---|
| 3763 | drug | ? | Настойка 5 трав 250мл | herbal tincture |
| 9307 | drug | ? | Полисорб плюс 25г | enterosorbent |
| 13321 | medical_device | **drug** | Метортрит шприц 10мг/мл | drug in syringe |
| 16137 | drug | **other** | Лайснер педикулицид | biocide |
| 22428 | other | **baf / vitamin_or_baa** | Визлея капс. 810мг | BAA as other |
| 23155 | drug | **vitamin_or_baa** | Брусники листья ф/п | herbal leaf |

**Recommendations (Sem0):** syringe+mg/ml → drug; pediculicide/repellent → other; leaf/herb filter-packs without INN → vitamin_or_baa; multi-herb tinctures — do not default drug.

## Stable zones

- drug / vitamin_or_baa: **administration_route 100%**
- vitamin_or_baa: **dosage_form, package_hint, product_kind 100%**
- cosmetic_hygiene: **product_kind 100%**
- drug: **dosage_form 97.7%**
- overall: **package_hint 92%, brand 90%, product_kind 94%**
- BAA: `rx_otc` all `unknown_acceptable` (policy null OK)

## Systemic problems

1. **drug.mnn** — wrong/empty INN (18% incorrect).
2. **age_segment** — invent adults vs missing adults (policy conflict with annotator).
3. **cosmetic route/form** — annotator wants наружное/крем; policy v2 hard-nulls.
4. **vitamin nosology** — nutrient string in nosology instead of taxonomy class.
5. **drug.rx_otc / nosology** — secondary noise after mnn.

## Next steps (analysis only)

1. Sem0 kind rules for syringe-drugs / herbals / biocides.
2. Sem1 brand→INN few-shot; null if unsure.
3. Sem1 vitamin nosology enum; nutrient → mnn.
4. Align age_segment rubric with annotator.
5. Cosmetic topical: relax policy or exclude from gate.
6. Gate focus: drug mnn + kind borderlines before Wave-500.
7. HITL spot-check those two zones only.

Interactive canvas: `wave100-markt-analysis.canvas.tsx`  
Machine dump: `redesign/artifacts/sem_wave100_markt_analysis.json`
