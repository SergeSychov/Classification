# Рекомендации: error-handling для `mnn-drug-enrichment`

**Дата:** 2026-08-11  
**Workflow:** `mnn-drug-enrichment` (`bEyKA1JJr0swuLql`)  
**База:** 37 executions (31 success / **6 error**); soft-scan по 20 success  
**Статус:** P0+P1 **реализованы** в WF (2026-08-11). Hard-20: см. `mnn_drug_enrichment_hard20_results.*` и обновлённый `mnn_drug_enrichment_recommendations.md`.

SearXNG и n8n на одном сервере: недоступность хоста не выделяем как риск «метода». Ниже — ошибки пайплайна (LLM API, деградация поисковых движков внутри SearXNG, контракт ответа, валидация).

---

## 1. Что показали проблемные executions

| id | mode | last node | ошибка | суть |
|---|---|---|---|---|
| **38343** | manual | DeepSeek — Postprocess | `ECONNRESET` ~74s | Search OK (24 snippets), обрыв **DeepSeek** на postprocess |
| **38326** | manual | DeepSeek — Preprocess | `ECONNABORTED` ~90s | Таймаут/обрыв **DeepSeek** на preprocess (timeout ноды = 90s) |
| **38252** | webhook | Preprocess — AI Agent* | Auth failed | Неверный API key (`sk-…` OpenAI) |
| **38251** | webhook | Preprocess — AI Agent* | Auth failed | то же |
| **38250** | webhook | Preprocess — AI Agent* | Auth failed | то же |
| **38249** | webhook | Preprocess — AI Agent* | Auth failed | то же |

\*Ранняя редакция WF (AI Agent + OpenAI creds). Сейчас — HTTP DeepSeek. Класс ошибки всё ещё актуален: **auth/config не ретраить**.

### Soft-деградации на success (не падение WF)

| сигнал | частота (из ~20 success) | пример |
|---|---|---|
| `mnn=null` | 3 | Циннабсин / Сандра (гомеопатия) — ожидаемо |
| `Category=Other` | 2 | гомеопатия |
| 1 из 3 SearXNG-запросов с `results=[]` | 4 | Новема: `[10,10,0]`, MNN всё равно найден |
| `unresponsive_engines` | часто | brave/google cse/startpage: *too many requests* / CAPTCHA; ответ всё же приходит с других движков |

**Сейчас в WF:** ни на одной HTTP-ноде нет `retryOnFail` / `onError`. SearXNG уже `neverError: true`. Aggregate при **нуле** сниппетов делает `throw` → webhook получает сырой 500 без JSON-контракта.

---

## 2. Таксономия ошибок и политика

Разделяем: **retryable** / **degrade** / **fail-fast** / **expected null**.

### A. DeepSeek HTTP (preprocess & postprocess) — главный реальный fail

| код/симптом | класс | действие |
|---|---|---|
| `ECONNRESET`, `ECONNABORTED`, `ETIMEDOUT`, socket hang up | retryable | **retry 2–3** с backoff (1s → 3s → 8s) |
| HTTP **429** / `rate_limit` | retryable | retry с backoff **длиннее** (5s → 15s → 30s), ≤3 |
| HTTP **5xx** | retryable | retry 2–3 |
| HTTP **401/403** invalid key | fail-fast | **без retry**; `error_code=auth_failed` |
| HTTP **402** / insufficient balance | fail-fast | без retry; `error_code=billing` |
| HTTP **400** bad request | fail-fast | без retry; логировать body |

Сейчас preprocess timeout 90s / postprocess 120s — при длинном wait + retry клиент webhook может «висеть». Нужен **бюджет ретраев** и предсказуемый error JSON (см. §4).

### B. SearXNG search (локальный инстанс)

| симптом | класс | действие |
|---|---|---|
| TCP/HTTP fail к SearXNG | retryable | retry 2–3 на **тот же** query (краткий backoff) |
| HTTP 200, `results=[]`, много `unresponsive_engines` | degrade | не падать на одном пустом query; см. fallback queries |
| все 3 query пустые | degrade → structured fail | не `throw` сырьём; вернуть JSON `status=search_empty` |
| частичный пустой (1/3) | OK | как сейчас — агрегировать оставшееся |

Fallback queries (если после 3 основных `search_count < N`, напр. `< 3`):

1. повтор без суффикса «ГРЛС»;
2. короткий `trade_name` + «действующее вещество» / «МНН»;
3. опционально: `trade_name` + «инструкция PDF».

Лимит: **не больше +2** дополнительных поисков, чтобы не раздувать latency.

### C. Валидация / семантика ответа

| симптом | класс | действие |
|---|---|---|
| preprocess JSON битый | degrade | уже есть fallback на 3 шаблонных query — **оставить** |
| postprocess не JSON / `ok_json=false` | retryable once | **1** повтор postprocess с тем же `prompt_user`; иначе `status=parse_error` + raw truncate |
| `mnn=null` + Category Other (гомеопатия) | expected | `status=ok`, `mnn=null` — не ошибка |
| `mnn=null` + Category Drug | soft warning | `status=ok_partial`, поле `warning=mnn_not_found` |
| пустой `product` | fail-fast | 400 + `error_code=empty_input` (не 500) |

### D. Конфиг / контракт webhook

| симптом | действие |
|---|---|
| auth DeepSeek | fail-fast + явный код (как §A) |
| исключение в Code-ноде | ловить в Validate/Error branch → JSON, не stack в клиент |
| chat vs webhook | одинаковый error-shape; chat — human text поверх JSON |

---

## 3. Предлагаемая архитектура защиты (после утверждения)

Минимальный инкремент в текущем линейном WF (без перевода на Agent):

```
… → DeepSeek Preprocess  [retryOnFail: transient]
  → Parse Queries
  → SearXNG Search       [retryOnFail: transient; neverError]
  → Aggregate Search     [если мало hits → optional Fallback Searches → re-aggregate]
  → DeepSeek Postprocess [retryOnFail: transient]
  → Validate JSON        [если !ok_json → Postprocess Retry once → re-validate]
  → Error Normalizer     [единый JSON при любом fail]
  → Is Webhook? → Respond
```

### Конкретные рычаги n8n

1. На **DeepSeek Pre/Post** и **SearXNG**:
   - `retryOnFail: true`
   - `maxTries: 3`
   - `waitBetweenTries: 2000` (или Code-wait с эскалацией — если n8n fixed wait недостаточен, обернуть в Loop Over Items / отдельный Retry subgraph)
2. `onError: continueErrorOutput` (или Error Trigger branch) → **Error Normalizer**, чтобы webhook **всегда** отвечал JSON.
3. Aggregate: заменить `throw` на structured item:
   ```json
   { "status": "search_empty", "ok_json": false, "mnn": null, "error_code": "search_empty", ... }
   ```
4. Не ретраить 401/403/402: в Error Normalizer по тексту/`httpCode` классифицировать `retryable=false`.

### Альтернатива (чуть тяжелее, но чище)

Вынести DeepSeek+SearXNG вызовы в маленький Code/HTTP helper с явной классификацией ошибок — больше контроля над backoff и «не ретраить auth», ценой поддержки JS.

**Рекомендую сначала** нативные `retryOnFail` + structured Aggregate + Error Normalizer; backoff-эскалацию и fallback-queries — вторым PR, если после недели логов ещё будут `search_empty` / rate-limit движков.

---

## 4. Единый контракт ответа (success и error)

Добавить поля (обратно совместимо с текущим success):

```json
{
  "status": "ok | ok_partial | error",
  "error_code": null,
  "error_message": null,
  "retryable": false,
  "Category": "Drug|BAS|Other|null",
  "mnn": null,
  "RX_OTC": "not applicable",
  "Age": "Универсальный",
  "Text": "",
  "search_count": 0,
  "search_queries": [],
  "ok_json": false,
  "warnings": []
}
```

| error_code | HTTP webhook (желательно) | retry клиентом? |
|---|---|---|
| `empty_input` | 400 | нет |
| `auth_failed` / `billing` | 503 или 401 | нет (чинить creds) |
| `llm_unavailable` | 503 | да (снаружи, с jitter) |
| `search_empty` | 200 + status=error | да, позже / другой query |
| `parse_error` | 200 + status=error | да, 1 раз |
| `internal` | 500 | ограниченно |

Для batch-runner с нашей стороны: ретраить только `retryable=true` / `llm_unavailable` / сетевые 503.

---

## 5. Другие кейсы, которые стоит закрыть заранее

1. **Burst webhook** (много параллельных POST) → 429 DeepSeek + CAPTCHA движков SearXNG. Защита: очередь/лимит в caller (наш script), опционально `Wait` 200–500ms между search items внутри WF.
2. **Раздутый postprocess prompt** (24×400 символов) → долгий ответ / обрыв как в 38343. Защита: клип до 12–16 сниппетов или 300 символов; приоритет URL с vidal/rls/grls в Aggregate.
3. **Preprocess вернул 0 queries** — уже fallback; оставить тест.
4. **Модель вернула mnn на EN** при RU-правиле — warning + optional normalize (не error).
5. **Chat public** без auth — риск злоупотребления ключом DeepSeek; для prod: отключить public chat или ограничить, оставить только webhook + наш API key/secret header (отдельное решение по безопасности).
6. **Смена модели** (`deepseek-chat` vs flash в логах) — зафиксировать model id в нодах и в ответе (`postprocess_model` уже есть).

---

## 6. План реализации (после «ок»)

**P0 — must**

1. `retryOnFail` на DeepSeek Preprocess / Postprocess / SearXNG (3 tries, ~2s).  
2. Aggregate: не `throw` на 0 hits → `status=search_empty`.  
3. Error Normalizer + Respond всегда с JSON §4.  
4. Классификация auth/billing → без бессмысленных ретраев на ветке continueErrorOutput (если n8n ретраит до onError — задокументировать; при необходимости фильтр в Code «если auth → сразу normalizer»).

**P1 — should**

5. Один повтор Postprocess при `!ok_json`.  
6. Fallback queries при `search_count < 3`.  
7. Ужать/приоритизировать snippets в Aggregate.  
8. `warnings` для `ok_partial` (Drug + mnn null).

**P2 — nice**

9. Caller-side circuit breaker в нашем batch script.  
10. Метрики: доля `llm_unavailable` / `search_empty` / success в артефакт после прогона.

**Не делать**

- Ретраить 401/403/402.  
- Подмешивать ответ модели без SEARCH_RESULTS при `search_empty` (ломает grounded-контракт).  
- Бесконечные loops «пока SearXNG не ответит».

---

## 7. Критерий приёмки

- Повторный прогон тех же продуктов, что дали 38343/38326: success **или** JSON с `error_code=llm_unavailable`, без сырого n8n stack.  
- Имитация пустого SearXNG (временно битый query): `search_empty`, HTTP не 500.  
- Пустой body: `empty_input`.  
- Гомеопатия: `status=ok`, `mnn=null`, не error.  
- Регресс: Новема / Левофлоксацин Реневал / Нитроксолин по-прежнему ок.

---

## Bottom line

Реальные падения текущего контура — **обрывы/таймауты DeepSeek** (2) плюс исторический **auth misconfig** (4). SearXNG чаще **деградирует по движкам**, но не валит WF, пока есть хоть какие-то `results`. Защита: retry на transient LLM/search, structured fail вместо throw, fail-fast на auth/billing, мягкие fallback на пустой поиск — **без** ослабления правила «не выдумывать МНН без сниппетов».

Жду утверждение scope (P0 / P0+P1), после этого правки в workflow на сервере.
