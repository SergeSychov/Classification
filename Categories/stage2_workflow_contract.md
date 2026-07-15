# Stage 2 Workflow — контракт и соглашения

Канонический workflow: **`classification-stage2-dev`** (`BaBjEPi78taRj2G5`)  
Журнал фаз: `Categories/stage2_workflow_plan.md`

---

## 1. Зоны (префиксы нод)

| Префикс | Назначение | Субпроцесс |
|---------|------------|------------|
| **In —** | Триггеры (manual, webhook) | нет |
| **Run —** | Создание `classification_runs`, константы стадии | нет |
| **Load —** | Загрузка партии товаров из БД | нет |
| **P1 —** | Primary LLM round | **да** |
| **2A —** | Fallback: выбор ветки (direction/block) | **да** |
| **2B —** | Fallback: выбор `category_id` в ветке | **да** |
| **Judge —** | Арбитраж спорных случаев (Polza / Qwen) | **да** |
| **DB —** | Snapshot + event log | нет |
| **Fin —** | Финализация run | нет |
| **Shared —** | Общие ресурсы (модели) | нет |

**Правило именования:** `{Зона} — {Глагол/роль}` на русском или коротком EN, без generic-имён (`Code`, `Merge`, `AI Agent`).

---

## 2. Субпроцессы

На канвасе каждый субпроцесс — **отдельная swimlane** (см. §7). Вход/выход item — по схемам ниже.

### P1 — Primary LLM

```
Load — Limit Batch
  → P1 — Build Prompt
  → P1 — LLM Prepare → P1 — AI Agent ← P1 — DeepSeek
  → P1 — Merge LLM → P1 — Post-process → P1 — Route
```

**Вход:** item с `shortlist_json`, `combined_text`, `run_id`, `constants`  
**Выход:** `product_classification_update`, `next_action`, `decision_status`

| next_action | Куда |
|-------------|------|
| `none` | DB (classified) |
| `human_review` | DB |
| `fallback_2a` | 2A |

---

### 2A — Fallback branch

```
P1 — Route [fallback_2a]
  → DB — Prepare Log (stage=primary_llm)  // параллельно
  → 2A — Categories Trigger → 2A — Load Categories
  → 2A — Merge Context → 2A — Rule Branch Filter
  → 2A — Skip LLM? → (LLM chain | bypass) → 2A — Post-process → 2B — Route
```

LLM chain: `2A — LLM Prepare → 2A — AI Agent ← 2A — DeepSeek → 2A — Merge LLM`

**LLM output:** `direction`, `block_family`, `family_code`, `nosology_hint`, `confidence`, `explanation` — **без `category_id`**

| next_action после 2A | Куда |
|----------------------|------|
| `fallback_2b` | 2B |
| `human_review` | DB |

---

### 2B — Fallback category

```
2B — Route [fallback_2b]
  → DB — Prepare Log (stage=fallback_2a)  // параллельно
  → branch shortlist build → Insert classification_shortlist
  → 2B — Skip LLM? → (LLM chain | bypass) → 2B — Post-process → DB
```

LLM chain: `2B — LLM Prepare → 2B — AI Agent ← 2B — DeepSeek → 2B — Merge LLM`

**LLM output:** `category_id`, `confidence`, `explanation` — **строго в branch shortlist**

| Итог | final_source | next_action |
|------|--------------|-------------|
| Успех | `fallback_2b` | `none` |
| Конфликт / low conf | `system` | `judge` / `human_review` |

---

### Judge — Арбитраж (Polza / Qwen)

```
2B — Post-process
  → Judge — Route [judge]
      → DB — Prepare Log (stage=fallback_2b)  // параллельно
      → Judge — LLM Prepare → Judge — AI Agent ← Shared — Polza
      → Judge — Merge LLM → Judge — Post-process → DB
  → Judge — Route [other] → DB
```

**LLM output:** `winner_source`, `category_id`, `confidence`, `explanation`, `needs_human_review`

| Итог | final_source | next_action |
|------|--------------|-------------|
| Успех | `judge` | `none` |
| Низкая уверенность / спор | `system` | `human_review` |

---

## 3. Контракт item (между нодами)

### Обязательные поля (сохранять через `...item.json`)

| Поле | Когда появляется |
|------|------------------|
| `run_id`, `run_meta` | после `Load — Attach Run ID` |
| `constants` | после `Run — Init Constants` |
| `product_id`, `product_raw_id` | из Load |
| `shortlist_json`, `combined_text` | из Load |
| `llm_*` | после P1 |
| `fallback_2a_*` | после 2A |
| `fallback_2b_*`, `branch_shortlist_json` | после 2B |
| `judge_*` | после Judge |
| `product_classification_update` | Post-process каждой стадии |
| `next_action`, `decision_status`, `routing_hint` | Post-process |

### Code-нода — обязательный паттерн

```javascript
return items.map((item, index) => ({
  json: { ...item.json, /* новые поля */ },
  pairedItem: index  // или { item: index }
}));
```

### Ссылка на run

```javascript
$('Run — Create Run').first().json
```

Нельзя ссылаться на ноду из параллельной ветки, если она не предок item (паттерн Merge Context).

---

## 4. Контракт БД

### `classification_runs`

- Создаётся в `Run — Create Run`, закрывается в `Fin — Close Run`
- `metadata`: `trigger`, `total_count`, `needs_review_count`

### `product_classification` (snapshot)

- Upsert по `product_id` в `DB — Upsert Snapshot`
- Одна строка на товар, поля стадий `llm_*`, `fallback_2a_*`, `fallback_2b_*`, `final_*`

### `product_classification_log` (event log)

- Insert без upsert, одна запись на попытку стадии
- `stage`: `primary_llm` | `fallback_2a` | `fallback_2b` | `judge` | `human_review`

### `classification_shortlist`

| stage | shortlist_type | parent_stage |
|-------|----------------|--------------|
| `primary_rules` | `rule_shortlist` | — |
| `fallback_2b` | `branch_shortlist` | `fallback_2a` |

---

## 5. Версии workflow / prompt

| Стадия | workflow_version | prompt_version |
|--------|------------------|----------------|
| P1 | `stage2_primary_llm_v1` | `prompt_primary_llm_v1` |
| 2A | `stage2_fallback_2a_v1` | `prompt_fallback_2a_v1` |
| 2B | `stage2_fallback_2b_v1` | `prompt_fallback_2b_v1` |
| Judge | `stage2_judge_v1` | `prompt_judge_v1` |

---

## 6. Пороги (из `Run — Init Constants`)

| Ключ | Значение | Стадия |
|------|----------|--------|
| `min_confidence_ok` | 0.60 | P1 auto-classify |
| `min_confidence_2a_ok` | 0.40 | 2A → 2B |
| `min_confidence_2b_ok` | 0.60 | 2B auto-classify |
| `min_confidence_judge_ok` | 0.60 | Judge auto-classify |

---

## 7. Раскладка на канвасе n8n (swimlanes)

Workflow читается **сверху вниз** по субпроцессам; внутри каждой полосы — **слева направо**.

```
┌─ Setup ─────────────────────────────────────────┐
│  In → Run → Load                                │
└───────────────────────┬─────────────────────────┘
                        ▼
┌─ P1 — Primary LLM (субпроцесс) ─────────────────┐
│  Build → Prepare → Agent → Merge → Post → Route │
│  P1 — DeepSeek (под Agent)                      │
└───────────────┬─────────────────┬───────────────┘
                │ fallback        │ classified
                ▼                 │
┌─ 2A (субпроцесс) ───────────────┤               │
│  Categories∥ → Merge → … → Post │               │
└───────────────┬─────────────────┘               │
                ▼                                 │
┌─ 2B (субпроцесс) ───────────────┤               │
│  Route → shortlist → … → Post   │               │
└───────────────┬─────────────────┘               │
                ▼                                 │
┌─ Judge (субпроцесс) ────────────┤               │
│  Route → Agent → Post           │               │
│  Shared — Polza                 │               │
└───────────────┬─────────────────┘               │
                │                                 │
                └──────────────┬──────────────────┘
                               ▼
┌─ DB + Fin (общий слой сбора) ───────────────────┐
│  Snapshot + Log → Barrier → Close run           │
└─────────────────────────────────────────────────┘
```

### Субпроцессы (визуально)

| Полоса | Sticky note | Цвет (preset) | Префикс нод |
|--------|-------------|---------------|-------------|
| Setup | 📥 Setup | blue (5) | In —, Run —, Load — |
| P1 | 🧠 P1 | green (4) | P1 — |
| 2A | 🌿 2A | orange (3) | 2A — |
| 2B | 🎯 2B | red (2) | 2B — |
| Judge | ⚖️ Judge | purple (6) | Judge — |
| DB + Fin | 💾 DB + Fin | yellow (1) | DB —, Fin — |
| Shared | 🔗 Shared | gray (7) | Shared — |

n8n не поддерживает вложенные sub-workflow без `Execute Workflow` — субпроцессы выделены **sticky notes + префиксы имён**. Логика остаётся в одном workflow для сквозного `item.json`.

### Правила позиций

- Шаг колонок **~220px** по X внутри полосы
- Основной поток — одна линия Y; параллельные ветки (Categories load, LLM bypass) — **+160…+200px** по Y
- Route-ноды — **последняя колонка** субпроцесса; выход «в DB» идёт **вниз** в слой DB + Fin
- Shared-модели — **под** AI Agent своей зоны (короткие ai_languageModel-связи)
- DeepSeek: **отдельная** Chat Model нода на каждый Agent (`P1 —`, `2A —`, `2B — DeepSeek`); одна модель и credential
- Новые ноды — только в зоне префикса, без перекрытий
- После правок layout: `python3 scripts/reorganize_stage2_layout.py`

---

## 8. LLM-модели

### DeepSeek (P1, 2A, 2B)

| Нода | Подключена к | Модель | Credential |
|------|--------------|--------|------------|
| **P1 — DeepSeek** | `P1 — AI Agent` | `deepseek-v4-flash` (или актуальная в n8n) | DeepSeek account |
| **2A — DeepSeek** | `2A — AI Agent` | та же | DeepSeek account |
| **2B — DeepSeek** | `2B — AI Agent` | та же | DeepSeek account |

**Правило:** одна физическая модель и один credential, но **три отдельные** Chat Model ноды — по одной под каждым Agent. Так канвас читается без длинных связей между swimlanes. Запрещено снова объединять P1/2A/2B в одну shared-ноду.

Judge **не** использует DeepSeek — только Polza / Qwen (см. ниже).

### Polza.ai (Judge)

| Нода | Подключена к | Модель | Credential |
|------|--------------|--------|------------|
| **Shared — Polza** | `Judge — AI Agent` | `qwen/qwen3.5-flash-02-23@reasoning_effort=none` | Polza account (`openAiApi`, Base URL `https://polza.ai/api/v1`) |

---

## 9. Каталог нод

Полное описание процесса, маршрутизация и схема потока — в **`Categories/stage2_node_map.md`** (справочник для заказчика).

### Setup

| Нода | Тип | Назначение |
|------|-----|------------|
| In — Manual | Trigger | Ручной запуск |
| In — Webhook | Webhook | POST `/webhook/classification-stage2-dev` |
| In — Webhook Start | Code | `batch_size` из body (1–100, дефолт 5) |
| Run — Create Run | Postgres | INSERT `classification_runs`, статус `running` |
| Run — Init Constants | Code | Словарь `constants` (стадии, пороги, модели) |
| Load — Select Batch | Postgres | Товары `pending` + shortlist из БД |
| Load — Attach Run ID | Code | `run_id`, `run_meta` на каждый item |
| Load — Limit Batch | Limit | Обрезка до `batch_size` |

### P1 — Primary LLM

| Нода | Тип | Назначение |
|------|-----|------------|
| P1 — Build Prompt | Code | Промпт + `deepseek_body`, политика shortlist |
| P1 — LLM Prepare | Code | `context`, `prompt_system` / `prompt_user` |
| P1 — AI Agent | AI Agent | Вызов LLM → JSON `category_id`, `confidence`, `explanation` |
| P1 — DeepSeek | Chat Model | Модель для P1 Agent |
| P1 — Merge LLM | Merge | Context + ответ LLM |
| P1 — Post-process | Code | Валидация, `llm_*`, routing, snapshot/log payload |
| P1 — Route | Switch | `fallback_2a` → 2A; иначе → DB |

### 2A — Fallback ветка

| Нода | Тип | Назначение |
|------|-----|------------|
| 2A — Categories Trigger | Code | Триггер загрузки справочника |
| 2A — Load Categories | Postgres | `categories_dict` (active) |
| 2A — Merge Context | Merge | Товары + справочник (ancestor-safe) |
| 2A — Rule Branch Filter | Code | Top-8 branch-кандидатов, `skip_llm` |
| 2A — Skip LLM? | IF | Bypass LLM при пустых кандидатах |
| 2A — LLM Prepare | Code | Промпт выбора ветки (без `category_id`) |
| 2A — AI Agent | AI Agent | JSON: direction, block_family, family_code, … |
| 2A — DeepSeek | Chat Model | Модель для 2A Agent |
| 2A — Merge LLM | Merge | Context + ответ LLM |
| 2A — Post-process | Code | `fallback_2a_*`, routing → 2B / human_review |

### 2B — Fallback категория

| Нода | Тип | Назначение |
|------|-----|------------|
| 2B — Route | Switch | `fallback_2b` → 2B chain; иначе → DB |
| 2B — Categories Trigger | Code | Триггер справочника (отдельно от 2A) |
| 2B — Load Categories | Postgres | `categories_dict` |
| 2B — Merge Context | Merge | Товары + справочник |
| 2B — Branch Shortlist Builder | Code | Branch shortlist (top-8) |
| 2B — Prepare Shortlist Payload | Code | Payload для `classification_shortlist` |
| 2B — Insert Branch Shortlist | Postgres | Upsert branch shortlist |
| 2B — Skip LLM? | IF | Bypass при пустом shortlist |
| 2B — LLM Prepare | Code | Промпт: `category_id` строго из shortlist |
| 2B — AI Agent | AI Agent | JSON: category_id, confidence, explanation |
| 2B — DeepSeek | Chat Model | Модель для 2B Agent |
| 2B — Merge LLM | Merge | Context + ответ LLM |
| 2B — Post-process | Code | `fallback_2b_*`, routing → classified / judge / review |

### Judge

| Нода | Тип | Назначение |
|------|-----|------------|
| Judge — Route | Switch | `judge` → Judge chain; иначе → DB |
| Judge — LLM Prepare | Code | Сводный промпт P1 + 2A + 2B + shortlists |
| Judge — AI Agent | AI Agent | JSON: winner_source, category_id, … |
| Shared — Polza | Chat Model | Polza / Qwen для Judge |
| Judge — Merge LLM | Merge | Context + ответ Judge |
| Judge — Post-process | Code | `judge_*`, финальное решение → DB |

### DB + Fin

| Нода | Тип | Назначение |
|------|-----|------------|
| DB — Prepare Snapshot | Code | `product_classification_update` |
| DB — Prepare Log | Code | `product_classification_log_insert` |
| DB — Upsert Snapshot | Postgres | Upsert `product_classification` |
| DB — Insert Log | Postgres | Insert `product_classification_log` |
| Fin — Merge Barrier | Merge | Barrier: Upsert + Insert |
| Fin — Pick Run | Code | Один item с `run_id` |
| Fin — Close Run | Postgres | Закрытие `classification_runs` + stats |

**Паттерн записи:** при эскалации (fallback/judge) — сначала **log** стадии; при завершении товара — **snapshot + log**.

---

## 10. Git и деплой

```bash
python3 scripts/pull_workflow.py classification-stage2-dev   # перед правками
python3 scripts/push_workflow.py classification-stage2-dev # после правок
python3 scripts/run_workflow.py --wait                     # smoke-test
```

**Не трогать:** `classification-stage2-prepare-for-llm` (эталон).

---

## 11. Чеклист при добавлении ноды

- [ ] Префикс зоны (`P1 —`, `2A —`, …)
- [ ] `...item.json` + `pairedItem`
- [ ] `constants` из `Run — Init Constants`, не хардкод строк
- [ ] Позиция в блоке, без перекрытий
- [ ] Sticky note обновлён при новом субпроцессе
- [ ] Push + smoke-test
- [ ] Новый LLM Agent → своя Chat Model нода в зоне (`P1 — DeepSeek`, не shared на несколько Agents)
