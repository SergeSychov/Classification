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
| **DB —** | Snapshot + event log | нет |
| **Fin —** | Финализация run | нет |
| **Shared —** | Общие ресурсы (модели) | нет |

**Правило именования:** `{Зона} — {Глагол/роль}` на русском или коротком EN, без generic-имён (`Code`, `Merge`, `AI Agent`).

---

## 2. Субпроцессы

### P1 — Primary LLM

```
Load — Limit Batch
  → P1 — Build Prompt
  → P1 — LLM Prepare → P1 — AI Agent ← Shared — DeepSeek
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

**LLM output:** `category_id`, `confidence`, `explanation` — **строго в branch shortlist**

| Итог | final_source | next_action |
|------|--------------|-------------|
| Успех | `fallback_2b` | `none` |
| Конфликт / low conf | `system` | `judge` / `human_review` |

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

---

## 6. Пороги (из `Run — Init Constants`)

| Ключ | Значение | Стадия |
|------|----------|--------|
| `min_confidence_ok` | 0.60 | P1 auto-classify |
| `min_confidence_2a_ok` | 0.40 | 2A → 2B |
| `min_confidence_2b_ok` | 0.60 | 2B auto-classify |

---

## 7. Раскладка на канвасе n8n

Слева направо по потоку данных:

```
In → Run → Load → P1 → 2A → 2B → DB → Fin
         Shared — DeepSeek (ниже P1/2A/2B)
```

- Новые ноды — **в зоне своего префикса**, не перекрывать соседние (+200px по X между колонками)
- Блоки помечены **sticky notes** на канвасе
- После правок: `python3 scripts/reorganize_stage2_layout.py` (только layout) или ручная правка позиций в зоне

---

## 8. Git и деплой

```bash
python3 scripts/pull_workflow.py classification-stage2-dev   # перед правками
python3 scripts/push_workflow.py classification-stage2-dev # после правок
python3 scripts/run_workflow.py --wait                     # smoke-test
```

**Не трогать:** `classification-stage2-prepare-for-llm` (эталон).

---

## 9. Чеклист при добавлении ноды

- [ ] Префикс зоны (`P1 —`, `2A —`, …)
- [ ] `...item.json` + `pairedItem`
- [ ] `constants` из `Run — Init Constants`, не хардкод строк
- [ ] Позиция в блоке, без перекрытий
- [ ] Sticky note обновлён при новом субпроцессе
- [ ] Push + smoke-test
