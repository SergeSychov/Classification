# Hierarchy mapping samples (live) — §13.2 / S3

Date: 2026-07-20  
DB: `pharmacy_ai` @ docker `pharmacypostgres` (via `vps-dokploy`)  
Related: [`21a_SCHEMA_DUMP.md`](21a_SCHEMA_DUMP.md), [`21b_MAPPING_STATS.md`](21b_MAPPING_STATS.md)

**PII:** dictionary fields from `categories_dict` only (no product rows).

---

## Verdicts (from S2, confirmed with samples)

| Mapping | Column | Verdict |
|---------|--------|---------|
| Потребность | `need_nosology` | **Confirmed with caveats** |
| МНН | `mnn_cluster` | **Confirmed with caveats** |

---

## Aggregate stats (summary)

| Metric | Value |
|--------|------:|
| Active categories | 1278 |
| Distinct directions | 10 |
| Distinct needs | 205 |
| Need empty | 0 |
| Need cross-direction collisions | 0 |
| MNN non-null | 92.6% |
| MNN multi-separator rows | 308 |
| MNN = category_name | 230 |

Full numbers: [`21b_MAPPING_STATS.md`](21b_MAPPING_STATS.md).

---

## Dirty / ambiguous examples (≥20)

| # | kind | category_id | direction | need_nosology | mnn_cluster / note | why ambiguous |
|---|------|------------:|-----------|---------------|--------------------|---------------|
| 1 | need_long | 891 | Инфузионная терапия… | Растворы для плазмозамещения и регидратации при диарее и ожогах (включая комбинированные составы) | Специализированные растворы для ожоговой болезни (Na/K/Ca/Cl + …) | Very long need; reads as multi-indication paragraph |
| 2 | need_long | 890 | Инфузионная терапия… | *(same as #1)* | Растворы типа «Регидрон для в/в» (Na/K/Cl/Цитрат/Глюкоза…) | Same long need shared by siblings |
| 3 | need_long + sep | 888 | Инфузионная терапия… | Специализированные растворы для коррекции объёма и осмолярности (маннитол, гипертонический NaCl) | Натрия хлорид гипертонический 3–7,5% | Comma inside need; embeds candidate MNNs in need text |
| 4 | need_sep | 830 | Инъекционные… | Неврология, анестезия и неотложная помощь (седативные и противосудорожные инъекционные) | Леветирацетам инъекционный | Comma-separated mega-need (bundle of clinical areas) |
| 5 | need_sep | 827 | Инъекционные… | *(same as #4)* | Диазепам инъекционный | Same bundled need for multiple injectables |
| 6 | need_unicode_hyphen | 972 | БАДы и витамины | Моно‑минералы кальций | *(see category)* | Unicode hyphen `‑` (U+2011) vs ASCII `-` — membership/norm risk |
| 7 | need_unicode_hyphen | 943 | БАДы и витамины | Моно‑витамины витамин B4 (холин) | Витамин B4 (холин) | Unicode hyphen in need; near-duplicate of category |
| 8 | need_near_category | 903 | БАДы и витамины | Моно‑витамины витамин A (ретинола ацетат/пальмитат) | = category_name | Need ≈ leaf category (slash inside need) — flat cascade |
| 9 | need_near_category | 926 | БАДы и витамины | Витамин C жевательные таблетки дети | category: Витамин C | Need is form/age segment, not abstract «потребность» |
| 10 | need_near_category | 920 | БАДы и витамины | Витамин D3 прочие формы взрослые | category: Витамин D3 (холекальциферол) | Form/age phrasing as need key |
| 11 | need_flat_dir | 991 | Лекарственные травы… | ЖКТ растительные средства внутрь желудочные и ветрогонные сборы | Желудочные и ветрогонные сборы | Direction nearly 1 need : 1 category |
| 12 | need_flat_dir | 992 | Лекарственные травы… | ЖКТ растительные средства внутрь слабительные растительные | Растительные слабительные средства | Same flat pattern |
| 13 | need_high_fanin | — | Лекарственные средства | Сердце и сосуды | 91 categories under this need | Soft-to-hard OK at need, but category shortlist must score well |
| 14 | need_high_fanin | — | Лекарственные средства | Гормональные препараты | 90 categories | Same fan-in pressure |
| 15 | need_high_fanin | — | Медицинские изделия | Средства гигиены и ухода | 77 categories | Device hygiene mega-bucket |
| 16 | mnn_multi_sep | 485 | Лекарственные средства | *(dry eye need)* | Гиалуроновая Кислота / Карбомер / ПВС / Повидон / Гипромеллоза / … | Slash-list of many actives — must split for mnn_selector |
| 17 | mnn_multi_sep | 36 | Лекарственные средства | *(cough need)* | Амброксол / Бромгексин / N-ацетилцистеин / Карбоцистеин / … | Same multi-MNN cluster pattern |
| 18 | mnn_multi_sep | 150 | Лекарственные средства | *(liver need)* | Силимарин / L-Орнитин / ЭФЛ / Экстракт Артишока / … | Multi-sep + mixed chemical/botanical |
| 19 | mnn_multi_sep | 494 | Лекарственные средства | *(otitis)* | Антибиотики / Антисептики / Противогрибковые… / Комбинации С ГКС | Class labels, not single INN |
| 20 | mnn_empty | 1252 | Косметика и гигиена | Дерматологическая косметика при псориазе и сухой коже | *(empty)* | Optional MNN stage must skip |
| 21 | mnn_empty | 1143 | Медицинские изделия | Ортезы и поддерживающие изделия | *(empty)* | Empty MNN on devices common |
| 22 | mnn_empty | 1000 | Лекарственные травы… | Нервная система растительные седативные и снотворные | *(empty)* | Phytopreparation without cluster |
| 23 | mnn_eq_name | 820 | Инъекционные… | *(injectable need)* | Флуконазол инъекционный | MNN equals category_name — leaf redundancy |
| 24 | mnn_eq_name | 749 | Инъекционные… | — | Ксекамен / Лорноксикам (лорноксикам) | Brand/INN mash + slash inside “single” cluster |
| 25 | mnn_device_sku | 1194 | Медицинские изделия | Экспресс-диагностика… | Тест на овуляцию, полоски, чувствительность 20–25 мМЕ/мл ЛГ | Not chemical MNN — SKU/spec text |
| 26 | mnn_device_sku | 1179 | Медицинские изделия | — | Спринцовка тип А №3, объём ~90–110 мл | Size/type SKU as cluster |
| 27 | mnn_device_sku | 1097 | Медицинские изделия | — | Размер 40 × 60 см, повышенная впитываемость | Dimension string as cluster |
| 28 | mnn_device_sku | 1111 | Медицинские изделия | — | Lady Mini Plus / Extra, длина ~25–27 см, 3–4 капли | Brand size + absorbency, multi-sep |

*(Rows 13–15 are aggregate buckets without a single `category_id`; they still count as mapping ambiguity for shortlist sizing.)*

---

## Implications for cascade v1

### Need (`need_nosology`)
1. **Keep as cascade key** — especially strong for `Лекарственные средства` (15 clean needs) and `Медицинские изделия` (10).
2. **`norm()` must** fold Unicode hyphen `‑` → `-`, collapse whitespace, case-fold for membership.
3. **Do not split needs on commas for hard identity** in v1 (comma is often prose); membership is on full distinct string after norm. Optional later: alias table.
4. **BADы / herbs / cosmetics:** expect near-flat need→category; Skip-LLM when shortlist size = 1 is important.
5. **High fan-in needs** (Сердце и сосуды = 91 cats): category shortlist scoring + top-N hard cap mandatory.

### MNN (`mnn_cluster`)
1. **Optional stage** remains correct: empty → skip; never fail classify solely on missing MNN.
2. **Split** on `/`, `,`, `;`, `|` into candidate list for selector; trim each part.
3. **Device/SKU clusters:** allow as opaque labels or treat low-value (policy: still selectable if in shortlist; Judge should not invent chemistry).
4. **When mnn == category_name:** selector may null-out without loss (category already identifies leaf).

### What not to do
- Do not switch mapping to another column without a new §13 review.
- Do not require normalized ID tables before Sem validation (still plan v1 text cascade).

---

## §13 samples status

**S3 complete** — ≥20 dirty/ambiguous examples attached.  
Next: S4 isolation design (`22_EXPERIMENT_ISOLATION.md`), then S5 checkbox updates.
