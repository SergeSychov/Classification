# Цель продукта и план до production

Источники (репо `/workspace`): `Categories/PROJECT.md`, `Categories/stage2_project_description.md`, `Categories/stage2_workflow_plan.md`, `Categories/stage2_workflow_contract.md`, `Categories/n8n_execution_contract.md`, `Categories/multi_agent_plan.md`, `redesign/00_PROJECT_STATUS.md`, `redesign/29_SHORT_ROADMAP.md`, `README.md`.

Канон решений go-live: [`docs/project-context.md`](project-context.md).

**Важно про репо-канон:** `Categories/stage2_workflow_plan.md` **не обновляем сейчас**. Правки туда — только после (а) подтверждения решений ниже (уже есть) **и** (б) фактических результатов трёх технических prod-like прогонов / пилота. До этого файл в репо не трогаем.

---

## Цель продукта

**Что это:** production-like агент категорирования аптечных товаров (n8n + PostgreSQL + LLM).

**Для кого:** команда каталога / контента аптечной номенклатуры — сократить ручную разметку без потери качества.

**Результат в проде:** партии товаров обрабатываются сессиями (`classification_runs`); уверенные кейсы закрываются автоматически (`classified` + `final_category_id`); сомнительные уходят на следующий уровень и при необходимости к человеку; по каждому товару и запуску есть snapshot + event log. Принцип: не «додумывать» — при сомнении эскалировать (`Categories/stage2_project_description.md`).

Стек и ключи: n8n (`https://n8n.sychovtest.ru`), Postgres (pgAdmin), DeepSeek (массовые раунды), Polza/Qwen (Judge). Инфра — AdminVPS.

---

## Текущее состояние

### Уже есть (Stage 1 / Stage 2)

| Компонент | Статус | Где |
|-----------|--------|-----|
| Stage 1 ShortList (rule engine → shortlist) | Рабочий workflow | `ShortList` / `7hx7k2mhJCbA57BG` |
| Stage 2 primary → 2A → 2B → Judge | Реализован и smoke-проверен | `classification-stage2-dev` / `BaBjEPi78taRj2G5` |
| Run / snapshot / log / пороги / borderline P1 | В контракте и коде | `Categories/stage2_workflow_contract.md` |
| Очередь human review + Telegram workflows | В репо; **не основной path** | primary HITL = **Sheets** (**CONFIRMED**) |
| Ops: execution contract (1 live run, chunk ≤ 10) | Зафиксирован | `Categories/n8n_execution_contract.md` |
| Balance bot DeepSeek/Polza | Есть (отдельный ops-трек) | `agent-balance-bot` |

Документы вроде `Categories/stage2_project_description.md` §«Следующий этап» и чеклист в `Categories/multi_agent_plan.md` частично **устарели**: 2A/2B/Judge закрыты в журнале; Telegram отмечен как сделанный, но основной human path — Sheets.

### Redesign (отдельный трек, не prod)

| Что | Статус |
|-----|--------|
| Hierarchy clone `classification-stage2-hierarchy-dev` | Active but safe: Load `WHERE false`, snapshot-off |
| Norm + Sem0→Sem1→attr Norm | Live path log-only; Dir/Need/Cat/Mnn/Judge **не** wired |
| Wave-100 Sem rubric | **PASS** (~0.58% critical); Wave-500 **не** стартован |
| Offline MNN / RX / Age / Norm v4.1 | Исследования/гейты закрыты; **не** влиты в live Sem/`attr_*` |
| Prod Stage 2 | **Не тронут** redesign’ом |

Канон: `redesign/00_PROJECT_STATUS.md`, `redesign/29_SHORT_ROADMAP.md`.

**Hierarchy (CONFIRMED):** live на паузе; допускается только параллельный B4 design **без** live-wiring / snapshot / SQL-write / изменений prod Stage 2. В cutover MVP hierarchy **не** входит.

### Что ещё не production-ready

1. **Ops readiness (Этап B)** ещё не закрыт: runbook + 3 подряд prod-like прогона 5–10 SKU.
2. **Пилот качества** на ≥200 стратифицированных SKU не проведён — quality gate ниже.
3. **Техдолг:** параметризованный SQL, индексы, диагностики (`Categories/PROJECT.md` «Что ещё открыто»).
4. **Host risk:** параллельные LLM/Merge и «зомби» executions — соблюдение `n8n_execution_contract` обязательно.

---

## Принятые решения go-live (CONFIRMED / согласовано)

Все развилки ниже — **подтверждены пользователем**, не предложения.

### 1. MVP-скоуп

**CONFIRMED:** MVP = **ShortList → `classification-stage2-dev` → Sheets HITL**. Hierarchy **не** в cutover.

### 2. Human path

**CONFIRMED:** Sheets — **единственный primary HITL**. Telegram — неактивный / вспомогательный (не массово активировать).

### 3. Quality gate (приёмка)

**CONFIRMED** пороги на размеченной выборке:

| Метрика | Hard gate | Цель |
|---------|-----------|------|
| Объём выборки | мин. **200** SKU (при необходимости **500**) | — |
| Critical error rate | **≤ 1%** | **0%** |
| Ошибки среди auto-classified | **≤ 3%** | — |
| `needs_human_review` | **≤ 30%** | **≤ 20%** |
| Auto classified (`decision_status=classified`, без human) | **≥ 60%** | **≥ 70%** |
| Ops smoke | **3 подряд** prod-like runs по **5–10** SKU без failed/stuck | — |
| Tracking | **100%** `run_id` / tracking | — |
| HITL writeback | **100%** записей human с `final_source=human` | — |

**Пороги borderline 0.40 / 0.60 — не менять до пилота** (CONFIRMED).

**Critical error (определение, CONFIRMED):** ошибка, при которой система выставила `decision_status=classified` с **неверным** `final_category_id` относительно экспертной разметки — товар ушёл в чужую категорию каталога (неверный leaf / принципиально неверная ветка). Считается в числителе critical rate; цель — 0%, hard gate ≤1% на пилотной выборке. Мягкие/соседние ошибки без «чужой ветки» учитываются в общем **auto-classified errors ≤3%**, но не обязательно как critical — если экспертная разметка помечает кейс как critical, он идёт в critical rate.

### 4. Первый объём

**CONFIRMED** последовательность объёма:

1. Пилот **200** стратифицированных SKU.
2. Затем **500–1000** чанками (после прохождения gates пилота).
3. Весь pending-пул — **только после** прохождения quality/ops gates и явного решения о drain.

### 5. Hierarchy

**CONFIRMED:** пауза live; только параллельный **B4 design** без live-wiring / snapshot / SQL-write / изменения prod Stage 2.

### Последовательность работ (CONFIRMED)

1. **Сначала** ops readiness (**Этап B**).
2. **Затем** controlled pilot **200** SKU.
3. **Затем** решение о drain (500–1000 → весь pending).

---

## План до production

**MVP/prod (CONFIRMED):** текущий Stage 2 (`classification-stage2-dev` + ShortList + Sheets). Hierarchy redesign — v2 / параллельный R&D design-only, не блокер go-live.

### Этап A — MVP-скоуп — DONE (CONFIRMED)

Зафиксировано: Stage 2 as-is; hierarchy не в cutover; HITL = Sheets; Telegram не primary.

### Этап B — Ops-контур Stage 2 на AdminVPS / n8n — СЛЕДУЮЩИЙ

**Сделать:**
- Runbook: ShortList → Stage 2 webhook/runner чанками ≤ 10; один live execution; stop зомби > 30 мин (`Categories/n8n_execution_contract.md`).
- Проверить credentials DeepSeek/Polza, Postgres, webhook Stage 2.
- Sheets-процесс: выгрузка `needs_human_review` / очередь → accept → запись `final_source=human`.
- Balance / лимиты API (bot уже есть — не раздувать cron).

**Критерий готовности (CONFIRMED):** 3 подряд успешных production-like прогона (batch 5–10) с корректным `classification_runs.finished`, snapshot+log, без failed/stuck; 100% `run_id`/tracking.

**Риски:** нагрузка n8n на AdminVPS; исчерпание баланса LLM; пустой/грязный pending-пул.

### Этап C — Controlled pilot 200 (gate go-live)

**Сделать:**
- Стратифицированная выборка **200** SKU (при необходимости расширить до **500**) через полный путь P1→…→Judge / Sheets review.
- Замерить метрики quality gate (§3 выше).
- Пороги 0.40 / 0.60 оставить без изменений до конца пилота.

**Критерий:** hard gates пройдены; отчёт по выборке; решение «можно расширять объём».

**Зависимости:** human labeling (Sheets); время эксперта каталога.

### Этап D — Расширение и drain (после gates)

**Сделать:**
- 500–1000 SKU чанками.
- Решение о полном drain pending — только после успешного расширения и стабильности ops.
- Ежедневный/по-запросу цикл: auto + Sheets backlog.
- Минимальный мониторинг: failed executions, stuck runs, баланс API.

**Критерий:** стабильный drain без деградации хоста; review-очередь под контролем команды.

### Этап E — Техдолг (после стабильного MVP, низкий приоритет)

Индексы, параметризованные SQL, diag-запросы, актуализация устаревших разделов customer/multi_agent docs. Не блокирует go-live.

### Отложить (не в MVP) — CONFIRMED

| Тема | Почему |
|------|--------|
| Hierarchy B4 live / cascade / Wave-500+ / cutover | Только B4 design parallel; без live-wiring/snapshot/SQL-write/prod Stage 2 |
| Merge MNN/RX/Age в live `attr_*` | Blocked до approval |
| Norm v4.1 overwrite `normalized_text` | Только controlled-integration design |
| Telegram как primary HITL | Sheets — единственный primary |
| RX Phase A / GRLS P1 | `KEEP_RX_OTC_P2_SUPPORT_ONLY` |
| Переписывание prod Stage 2 под cascade | Запрещено без dual-run и явного ask |
| Правки `Categories/stage2_workflow_plan.md` | Только после подтверждённых решений (есть) **и** результатов 3 tech runs / пилота |

---

## Статус развилок

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | MVP = текущий Stage 2 + Sheets; hierarchy не блокирует prod? | **CONFIRMED: да** |
| 2 | Sheets primary; Telegram не массово? | **CONFIRMED: да** |
| 3 | Выборка и пороги go-live? | **CONFIRMED:** см. §3 Quality gate |
| 4 | Объём первого prod? | **CONFIRMED:** 200 → 500–1000 → весь pending после gates |
| 5 | Hierarchy дальше? | **CONFIRMED:** пауза live; только B4 design без live-wiring |
