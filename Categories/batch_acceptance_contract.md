# Batch acceptance — контур приёмки заказчиком

Цель: оценивать работоспособность без накопления скрытых ошибок. HITL в Telegram для «сложных» позиций — отдельный контур (приостановлен); **приёмка батча** идёт через Google Sheets.

## Размер батча

1. Старт: **100** товаров на run.
2. После стабильных метрик: **500** (cap webhook = 500).
3. После Fin run — **стоп** автопродолжения (нет следующего batch, пока заказчик не закрыл приёмку).

## Поток

После `Fin — Close Run` в `classification-stage2-dev` вызывается workflow `classification-batch-acceptance`:

1. Claim строки в `batch_acceptance` (идемпотентно: повтор `notified` → no-op).
2. Один Spreadsheet на `run_id`, два листа:
   - `A_classified`
   - `B_open`
3. Балансы DeepSeek + Polza (HTTP).
4. Одно сообщение в Telegram (`pipeline_settings.telegram_ops_chat_id`).

## Две таблицы (Google Sheets)

После каждого batch экспорт **товаров этого run**:

| Sheet | Состав | Действие заказчика |
|-------|--------|-------------------|
| **A_classified** | `classified` этого batch | Проверить категории |
| **B_open** | `needs_human_review` / `error` этого batch | Выбрать категорию из shortlist / проставить вручную |

Spreadsheet шарится как **anyone with the link → editor**.


### Колонки A_classified

`product_name | category_code | category_name | confidence | explanation`

### Колонки B_open

`product_name | shortlist`

`shortlist` — компактная строка `id:name; …` (до 8 позиций).

Экспорт содержит только товары **текущего batch** (`latest_run_id = run_id`).

## Telegram-сообщение (пример)

```
Batch run #123 · finished_with_review
A classified: 87 — https://docs.google.com/spreadsheets/d/.../edit#gid=0
B open: 13 — https://docs.google.com/spreadsheets/d/.../edit#gid=...
Pipeline stopped — wait for customer review.

Balances · 2026-07-19 19:40 MSK
• DeepSeek: $12.40
• Polza (Judge): 450.00 RUB
Below $1 / 80 RUB: — none —
```

## Таблица `batch_acceptance`

| status | смысл |
|--------|--------|
| `pending` / `exporting` | в процессе |
| `notified` | Sheets + (опционально) Telegram готовы |
| `error` | сбой export |

Поля URL: `spreadsheet_id`, `spreadsheet_url`, `sheet_a_url`, `sheet_b_url`; плюс `balances_json`, счётчики.

## Settings (`pipeline_settings`)

| key | value |
|-----|--------|
| `telegram_ops_chat_id` | `{"chat_id":"..."}` |
| `google_sheets_folder_id` | `{"folder_id":""}` (опционально) |
| `balance_alert_threshold_usd` | `{"value":1}` |
| `usd_rub_rate` | `{"value":80}` |

## Разбор ошибок Sheet A (следующий этап)

1. Импорт строк с `ok=нет` → БД (`final_source=human` / QA-log) + журнал `qa_errors`.
2. Агрегация по `error_type`, stage (`llm` / `2b` / `judge`).
3. Промпты менять **только по повторяющемуся паттерну**, с новой `prompt_version` и проверкой на следующем batch.
4. Критерии готовности (ориентир): доля ошибок A &lt; 5% на 100 и &lt; 3% на 500; доля B снижается.

## Баланс агентов

После **каждого batch** в том же Telegram-сообщении:

- DeepSeek (P1 / 2A / 2B)
- Polza (Judge)

Отдельный суточный бот балансов — sibling `agent-balance-bot`.

## Webhook (ops / smoke)

`POST /webhook/classification-batch-acceptance` body: `{"run_id": <id>}`

Также вызывается автоматически из `classification-stage2-dev` → `Fin — Batch Acceptance` после `Fin — Close Run`.

## Cutover

Workflows `classification-human-review-enqueue` / `classification-human-review-send` деактивированы — приёмка идёт через Sheets, не через карточки в Telegram.
