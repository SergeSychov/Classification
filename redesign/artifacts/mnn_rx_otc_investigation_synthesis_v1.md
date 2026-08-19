# Сводка исследования RX/OTC (M3.0 → M3.2b.5)

**Дата сводки:** 2026-08-19
**Статус:** feasibility / audit-only. Каталог, `attr_rx_otc`, snapshot и n8n **не** обновлялись.
**Итоговое решение:** `KEEP_RX_OTC_P2_SUPPORT_ONLY` · `DO_NOT_RUN_PHASE_A_YET`

Главный вопрос: можно ли автоматически и воспроизводимо получать **product-specific** доказательство «по рецепту / без рецепта» для лекарственного SKU.

**Ответ:** стабильного официального P1-маршрута нет. Есть узкий P1b (официальные инструкции бренда, 2/10) и широкий, но неавторитетный P2 (аптеки/Vidal/АСНА). Этого недостаточно для записи `final_rx_otc_value` и для Phase A 11+30.

---

## 1. Зачем это делалось

Wave-500 (`run_id=461`): RX/OTC accuracy **72/83 = 86.7%**. Подтверждённых ошибок — **11**. У всех 11 в сохранённых evidence **не было** достаточного product-specific официального статуса (`0/11`).

Причины, зафиксированные до retrieval:

- skip/reuse пути Stage 2 ставили RX/OTC без карточки препарата;
- «ГРЛС» в выдаче оказывался лендингом, не карточкой РУ;
- Vidal/аптеки принимались за истину и путали форму (спрей/крем, таблетки/капсулы).

Архитектура M3.1 (design-only):

```text
P1a  официальная карточка ГРЛС / EGISZ
P1b  официальная инструкция / сайт держателя РУ (MAH)
P2   Vidal / RLS / аптека / розничный каталог  → только supported_only
P3   сниппет поиска / лендинг / generic МНН     → не evidence
```

Контракт v2: статус только из fetched HTTP 2xx тела страницы. Сниппет поиска не даёт RX/OTC. P2 никогда не ставит `final`. P1/P1 конфликт → ручной разбор. Majority vote аптек не повышает уровень до P1.

M2-13 BAS/Other в выборку не входили.

---

## 2. Выборка

Контрольные **10** лекарственных SKU (расширение mini-batch M3.2b.3 с 5 до 10):

| product_id | SKU | Особый guard |
|---|---|---|
| 3065 | Флуконазол-OBL капс. 150 мг №4 Оболенское | бренд+форма+доза |
| 4922 | Термикон **спрей** 1% 30 г | ≠ крем, ≠ таблетки |
| 4924 | Термикон **крем** 1% 15 г | ≠ спрей, ≠ таблетки |
| 19370 | Дюспаталин **таблетки 135 мг** | ≠ капсулы 200 мг |
| 26115 | Амброксол табл. 30 мг Вертекс | generic МНН как бренд |
| 10046 | Папаверин табл. 40 мг Ирбит | generic МНН |
| 7275 | Сановаск табл. 50 мг Ирбит | не «Сановаск Магний» |
| 1053 | Экзоролфинлак лак 5% | лак, не таблетки |
| 2621 | Фурацилин табл. д/р-ра 20 мг Татхимфарм | не мазь |
| 18377 | Йод р-р спирт. 5% 25 мл Гиппократ | завод Гиппократ |

M3.2b.3 гонял только первые пять. Позже все 10.

Нигде в исследовании **не** задавался заранее ожидаемый RX/OTC и **не** писался `final_rx_otc_value`.

---

## 3. Что проверили и чем кончилось

### M3.0 — source audit (offline)

Сохранённые URL/excerpt по 11 ошибкам: sufficient P1 = **0/11**. Лучшие источники: Vidal/RLS 5, snippet 4, официальная инструкция 2 (без явного статуса в excerpt).

### M3.1 — design

Лестница Q1 ГРЛС → Q2 инструкция MAH → Q3 поддержка. Workflow `rx-otc-product-retrieval-dev` спроектирован, **не активирован**.

### M3.2a — skeleton

Локальный/runtime smoke без live retrieval. HTTP в workflow запрещён на этом шаге.

### M3.2b / M3.2b.2 — live retrieval + контракт

SKU 3065 через SearXNG/Bing: outcome `supported_only`, candidate `otc` с Vidal, `final=null`.
v1 смешивал сниппеты с evidence; v2 разделил `discovery_hits` / `fetched_documents` / `validated_evidence`.

### M3.2b.3 — P1 feasibility, 5 SKU, SearXNG/Bing

| Метрика | Значение |
|---|---|
| Валидный P1 | **0/5** |
| P2 supported_only | 2/5 (3065, 19370 Vidal) |
| unresolved | 3/5 |
| Рекомендация | `DO_NOT_RUN_PHASE_A_YET` |

Поиск не находит карточки ГРЛС и почти не показывает сайты MAH. Бюджет съедают аптеки. Формы путаются (Термикон таблетки к спрею; Дюспаталин капсулы 200 к таблеткам 135). Generic «Амброксол» через Bing разваливается в иностранный мусор.

### M3.2b.4 — прямой официальный ГРЛС (P1a), 10 SKU, без поисковиков

| Метрика | Значение |
|---|---|
| Валидный P1 в финальном CSV | **0/10** |
| Route | `P1_ROUTE_NOT_FEASIBLE` |
| Рекомендация | `KEEP_RX_OTC_P2_SUPPORT_ONLY` |

Публичный POST `GRLS.aspx` (`txtTorg` / `bSeek` / `isFS=0`) и `Grls_View_v2.aspx?routingGuid=` **технически существуют**, но портал нестабилен: TLS-цепочка неполная, затем WAF 403, затем `/cp/login`. Финальный прогон — все 10 `p1_portal_blocked`. CAPTCHA/логин не обходились.

Раннее публичное окно (не зачтено как P1): карточки с «Без рецепта» были, identity сначала ломалась о chrome title; повтор после фикса матчера уже упёрся в login wall.

### Brandquad `pharm.brandquad.ru` — зеркало ГРЛС

| Метрика | Значение |
|---|---|
| Публичный JSON API | да, без логина |
| Valid explicit после жёсткой identity | **6/10** |
| Official P1 | **нет** |

`POST /api/grls` + `is_recipe`. Это коммерческая копия, не Минздрав. Нельзя ставить `final`. Не меняет решение P1a.

### M3.2b.5 — P1b официальные инструкции MAH, 10 SKU, без поисковиков

| Метрика | Значение |
|---|---|
| Валидный P1b | **2/10** |
| Route | `P1B_ROUTE_PARTIALLY_FEASIBLE` |
| Рекомендация | `DESIGN_OFFICIAL_INSTRUCTION_MAH_ADAPTER` (не Phase A) |

Сработало только там, где есть живой бренд-сайт с **раздельными** страницами форм:

- 4922 [termikon спрей](https://termikon.ru/instrukcii/termikon-sprey-instrukciya.html) → OTC, identity A
- 4924 [termikon крем](https://termikon.ru/instrukcii/termikon-krem-instrukciya.html) → OTC, identity A

Дюспаталин: страница 135 мг есть, в HTML статуса нет; PDF инструкции скачан, текст не извлечён. Остальные MAH-хосты не резолвятся или не содержат product-specific инструкцию.

### Дистрибьюторы (Катрен, Пульс, Протек, Фармкомплект, БСС, АСНА)

| Хост | Публичный SKU-каталог |
|---|---|
| asna.ru | да (розница ассоциации, не B2B) |
| katren.ru | нет (поиск статей) |
| puls.ru | нет (Qrator 401) |
| protek.ru | нет |
| pharmk.ru | нет (логин) |
| bsspharm.ru | нет |

Конкурентность **между дистрибьюторами невозможна**. АСНА даёт поле «Условия отпуска», но часто соседний завод или line extension (Дюспаталин ДУО, Амброксол Велфарм, Йод не Гиппократ). Это P2.

---

## 4. Сводка по 10 SKU (все маршруты)

`final` везде null. «OTC» ниже — candidate / research, не каталоговое значение.

| ID | P1a ГРЛС | P1b MAH | Brandquad (не P1) | P2 АСНА/Vidal | Комментарий |
|---|---|---|---|---|---|
| 3065 | blocked | host not found | conflict RX+OTC на одной РУ | АСНА OTC (Алиум, не Оболенское); ранее Vidal OTC | держатель РУ съехал |
| 4922 спрей | blocked | **P1b OTC** termikon.ru | OTC, identity A | АСНА OTC, форма спрей | лучший P1-кейс |
| 4924 крем | blocked | **P1b OTC** termikon.ru | OTC, identity A | АСНА OTC, форма крем | отдельная страница от спрея |
| 19370 табл. 135 | blocked | страница A, статус в HTML нет | OTC, identity A | АСНА взял **ДУО**; Vidal 135 был P2 | PDF MAH не распарсен |
| 26115 | blocked | not found | OTC Вертекс табл. | АСНА Велфарм, не Вертекс | generic МНН |
| 10046 | blocked | host not found | OTC Ирбит табл. | АСНА Медисорб | generic МНН |
| 7275 | blocked | host not found | identity C (Сановаск Магний) | АСНА 50 мг Ирбит — ближе к SKU | зеркало путает линейку |
| 1053 | blocked | host not found | A, `is_recipe` пустое | АСНА Фитолакс D | бренд-сайт не найден |
| 2621 | blocked | not found | OTC Татхимфарм | АСНА Авексима | generic МНН |
| 18377 | blocked | прайс PDF, D | identity C (нет 5% у Гиппократа) | АСНА 10 мл МФФ | слишком общий «йод» |

Единственные **зачтённые официальные P1** за всё исследование: две инструкции Термикон на `termikon.ru`.

---

## 5. Что доказано про методы

| Метод | Воспроизводимый P1? | Почему |
|---|---|---|
| SearXNG / Bing | нет | не находит ГРЛС-карточки и MAH; сжигает fetch на P2 |
| Прямой ГРЛС portal | нет как unattended adapter | POST есть, доступ нестабилен (403 / login) |
| Brandquad API | да как зеркало, нет как P1 | не официальный хост |
| Сайт MAH / бренд | редко (2/10) | нужен microsite с раздельными формами |
| Аптеки / Vidal / АСНА | да как P2 | чужие формы и заводы |
| B2B дистрибьюторы | нет публично | логин / WAF / корпоративный сайт |
| Голосование источников | не делает P1 | P2 vs P2 при споре = unresolved |
| LLM | не использовался | статус из модели запрещён контрактом |

Identity-guards работают, когда страница product-specific (Термикон спрей≠крем). Ломаются на generic МНН и на «бренд+доза» без завода (Дюспаталин ДУО).

---

## 6. Решение

1. **Не запускать M3.2c Phase A (11+30).** Тот же acquisition failure повторится в большем масштабе.
2. **Не писать RX/OTC в snapshot / `attr_*` / classification_runs.**
3. **Не считать P1:** Brandquad, АСНА, Vidal, RLS, аптеки, поисковые сниппеты.
4. **Оставить текущую политику:** `KEEP_RX_OTC_P2_SUPPORT_ONLY`. P2 можно показывать человеку как soft signal с veto по форме/заводу.
5. **Единственный осмысленный engineering follow-up (не Phase A):** адаптер P1b только для брендов с официальным microsite инструкций + разбор PDF (как Дюспаталин). Это не покрывает generic МНН.
6. Прямой ГРЛС-адаптер имеет смысл **только если** появится стабильный публичный интерфейс без login/WAF.

Workflow `UqssZ24Jr7Qk9ef4` / `rx-otc-product-retrieval-dev` остаётся inactive.

---

## 7. Изоляция (все этапы)

Не было: n8n execute/activation, PostgreSQL writes, `classification_runs`, snapshot/`attr_*`/`product_kind`, LLM для статуса, git commit/push, обход CAPTCHA/логина, массовый каталоговый поиск.

---

## 8. Артефакты и runners

| Этап | Runner | Сводка |
|---|---|---|
| M3.0 audit | `scripts/mnn_rx_otc_source_audit_v1.py` | `redesign/artifacts/mnn_rx_otc_source_audit_v1_summary.md` |
| M3.1 design | — | `redesign/m3_1_rx_otc_retriever_design.md` |
| M3.2b | `scripts/run_rx_otc_m3_2b_one_item.py` | `mnn_rx_otc_retrieval_m3_2b_summary.md` |
| contract v2 | `scripts/test_rx_otc_m3_2b_evidence_contract_v2.py` | `redesign/m3_2b_rx_otc_evidence_contract_v2.md` |
| M3.2b.3 | `scripts/run_rx_otc_m3_2b_3_p1_feasibility.py` | `mnn_rx_otc_retrieval_m3_2b_3_summary.md` |
| M3.2b.4 P1a | `scripts/run_rx_otc_grls_access_v1.py` | `mnn_rx_otc_grls_access_v1_summary.md` |
| Brandquad | `scripts/run_rx_otc_brandquad_grls_v1.py` | `mnn_rx_otc_brandquad_grls_v1_summary.md` |
| P1b MAH | `scripts/run_rx_otc_p1b_instruction_v1.py` | `mnn_rx_otc_p1b_instruction_v1_summary.md` |
| Дистрибьюторы | `scripts/run_rx_otc_distributor_p2_v1.py` | `mnn_rx_otc_distributor_p2_v1_summary.md` |
| Эта сводка | — | `redesign/artifacts/mnn_rx_otc_investigation_synthesis_v1.md` |
