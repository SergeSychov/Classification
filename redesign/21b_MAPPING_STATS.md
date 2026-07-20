# Mapping stats — §13.2 (read-only)

Date: 2026-07-20  
DB: `pharmacy_ai` @ docker `pharmacypostgres` (via `vps-dokploy`)  
Source table: `categories_dict` (`is_active = true` for all 1278 rows)  
Depends on: [`21a_SCHEMA_DUMP.md`](21a_SCHEMA_DUMP.md) (columns confirmed)

Mode: **SELECT only**. Draft verdicts for cascade v1 — final dirty samples in S3 (`21_HIERARCHY_MAPPING_SAMPLES.md`).

---

## Draft verdicts

| Mapping | Assumed column | Draft verdict | Rationale |
|---------|----------------|---------------|-----------|
| Потребность | `need_nosology` | **Confirmed with caveats** | Usable cascade key. Empty=0. No cross-direction collisions. For `Лекарственные средства` / `Медицинские изделия` labels read as clear потребности. Caveat: in `БАДы и витамины` (and some other dirs) need ≈ near-category granularity (85 needs / 88 cats). |
| МНН | `mnn_cluster` | **Confirmed with caveats** | Usable **optional** leaf under category. 92.6% non-null; many drug rows look like real MNN. Caveats: 24% multi-separator cells; 230 rows where `mnn_cluster = category_name`; med-device rows often size/SKU/form text, not chemical MNN. |

Neither mapping is **Rejected**. Proceed to S3 samples with caveats documented for cascade builders.

---

## Aggregate stats

### Directions

| metric | value |
|--------|------:|
| rows (all / is_active) | 1278 / 1278 |
| distinct `direction` | 10 |
| empty direction | 0 |

### Need (`need_nosology`)

| metric | value |
|--------|------:|
| empty need | **0** |
| distinct needs (trim) | **205** |
| needs with `[,;/\|]` | 65 |
| needs length > 80 | 26 |
| same need under multiple directions | **0** |
| avg categories per (direction, need) | 6.2 |
| max categories per (direction, need) | 91 |

### Needs per direction

| direction | n_cats | n_needs | need_empty |
|-----------|-------:|--------:|-----------:|
| Лекарственные средства | 713 | 15 | 0 |
| Медицинские изделия | 229 | 10 | 0 |
| Инъекционные препараты системного действия | 125 | 19 | 0 |
| БАДы и витамины | 88 | 85 | 0 |
| Инфузионная терапия, электролиты и парентеральное питание | 57 | 10 | 0 |
| Лекарственные травы и фитопрепараты | 18 | 18 | 0 |
| Косметика и гигиена | 17 | 17 | 0 |
| Бактериофаги | 12 | 12 | 0 |
| Товары для мам и детей | 12 | 12 | 0 |
| Гомеопатия | 7 | 7 | 0 |

**Shape note:** LS (713→15→…) and MI (229→10→…) are ideal soft-to-hard cascades. BADы / herbs / cosmetics are nearly flat need≈category — still valid keys, but need shortlist will often be large/singleton-ish.

### MNN (`mnn_cluster`)

| metric | value |
|--------|------:|
| empty mnn | 94 |
| distinct mnn (trim) | 1044 |
| pct non-null | **92.6%** |
| rows matching `[,;/\|]` | **308** (~24% of active) |
| `lower(mnn_cluster) = lower(category_name)` | 230 |

---

## Spot-check: `need_nosology` (15 random)

| direction | need_nosology | category_name (context) |
|-----------|---------------|-------------------------|
| Лекарственные травы… | Сердечно‑сосудистая система растительные гипотензивные и кардиотонические | Растительные кардио‑ и гипотензивные средства |
| Лекарственные средства | Кровеносная система | Нарушения микроциркуляции… |
| Лекарственные средства | Сердце и сосуды | Гипертония БРА… |
| Лекарственные средства | Костно-мышечная система | Боль костно-мышечная… |
| Лекарственные средства | Алкоголизм и табакокурение | Никотиновая зависимость… |
| Лекарственные средства | Сердце и сосуды | Дислипидемия статины… |
| Лекарственные средства | Зрение и слух | Инфекции глаз… |
| Медицинские изделия | Тепло‑ и холодотерапия для дома | Грелки и холодовые пакеты |
| Лекарственные средства | Боль и температура | Комбинированные анальгетики… |
| Медицинские изделия | Средства для обработки кожи и ран | Антисептики… |
| Лекарственные средства | Кожные заболевания | Дерматиты и экзема… |
| Гомеопатия | Гомеопатические средства для детей при ОРВИ и функциональных расстройствах | Детская гомеопатия… |
| Лекарственные травы… | Мочевыделительная система растительные мочегонные сборы | Мочегонные растительные сборы |
| Лекарственные средства | ЖКТ и пищеварение | Спастическая боль… |
| Лекарственные средства | Гормональные препараты | Антитиреоидные средства… |

**LS needs (complete set of 15):** Алкоголизм и табакокурение; Боль и температура; Гормональные препараты; Дыхательная система; ЖКТ и пищеварение; Зрение и слух; Инфекции и укусы; Кожные заболевания; Костно-мышечная система; Кровеносная система; Мочеполовая система; Нервная система и сон; Простуда и ОРВИ; Сердце и сосуды; Стоматология.

### Spot-check: `mnn_cluster` (15 random)

| category_id | direction | category_name | mnn_cluster |
|------------:|-----------|---------------|-------------|
| 501 | Лекарственные средства | Отит… неототоксические антибиотики | Норфлоксацин |
| 824 | Инъекционные… | Стрептомицин | Стрептомицин |
| 447 | Лекарственные средства | Инфекции глаз бактериальные… | Ципрофлоксацин |
| 955 | БАДы и витамины | Витамин B7 (биотин) | Витамин B7 (биотин) |
| 449 | Лекарственные средства | Инфекции глаз бактериальные… | Моксифлоксацин |
| 913 | БАДы и витамины | Витамин A… | Витамин A (ретинола ацетат/пальмитат) |
| 1177 | Медицинские изделия | Спринцовки… | Спринцовка тип А №1, объём ~30–35 мл (детская) |
| 1228 | Медицинские изделия | Средства для обработки и заживления ран | Порошки/присыпки для ран с антисептическим эффектом |
| 1023 | Медицинские изделия | Лейкопластырь бактерицидный… | Размер 1,6 см × 5,7 см |
| 337 | Лекарственные средства | Недержание мочи… | Троспия Хлорид |
| 954 | БАДы и витамины | Витамин B7 (биотин) | Витамин B7 (биотин) |
| 494 | Лекарственные средства | Отит наружного уха… | Антибиотики / Антисептики / Противогрибковые Компоненты / Комбинации С ГКС |
| 761 | Инъекционные… | Цефотаксим | Цефотаксим |
| 738 | Инъекционные… | Урофоллитропин, фоллитропин альфа/бета | Урофоллитропин, фоллитропин альфа/бета |
| 812 | Инъекционные… | Допамин | Допамин |

---

## Implications for cascade v1 (feed into S3/S4)

1. **Need selector:** hard shortlist under direction is safe; expect small lists for LS/MI, near-1:1 for BADы — Skip-LLM when singleton still valuable.
2. **norm():** unicode hyphen variants (`‑` vs `-`), separators in 65 needs — normalize before membership compare.
3. **MNN optional:** empty shortlist / skip when null; split multi-sep (`/`, `,`, `;`, `|`) into candidates; do not treat device size strings as chemical MNN failure — accept as cluster label or null policy later.
4. **Do not invent alternate columns** — live data supports assumed mapping with caveats above.

---

## §13.2 status

**S2 complete** — draft verdicts recorded.  
S3 will attach ≥10–20 dirty/ambiguous rows; S5 ticks plan checkboxes.
