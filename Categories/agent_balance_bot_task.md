# Задание: доработка `agent-balance-bot`

Workflow на n8n: **`agent-balance-bot`** (`Ly8pjn4ZP51V1xA9`)  
Git: `workflows/agent-balance-bot.json` (экспорт 17 нод, 2026-08-18 14:14 UTC+3)  
Контракт executions: `Categories/n8n_execution_contract.md`

**Сейчас на сервере `active=false` — не включать, пока watchdog не исправлен.**  
Делать в папке проекта (правки JSON → push). Этот файл — ТЗ.

---

## Проблема

Было: cron `* * * * *`. HTTP DeepSeek+Polza + Merge `combineByPosition` зависали, следующая минута копила executions.

**18.08 ~13:44** остановлены 12 зомби (с 13–14.08).  
**18.08 14:14** на сервер залита 17-нодная версия (09:00 + Telegram + watchdog через Public API) и **включена**.  
**18.08 ~14:15–14:22** снова CPU 40%→160% и RAM ~5→6 ГБ, сервер в standby.

Вторая авария — не минутый cron (его уже убрали), а связка:

1. n8n после отмены 12 четырёхдневных run не отдал память (линейный рост RAM на графике с 13:27).
2. Watchdog на **каждом** старте (в т.ч. Telegram) делает три GET `/api/v1/executions`.  
   **`status=new` на этом n8n сломан:** игнорирует фильтр и отдаёт последние 50 executions любых статусов (success/canceled/error).
3. Активация Telegram Trigger сразу после этого — ещё один процесс (getUpdates) на уже раздутом Node.

`executionTimeout: 90` выставлен — это ок. Watchdog в текущем виде **не включать**.

Измерение API (18.08):

| query | bytes | что реально приходит |
|-------|-------|----------------------|
| `status=running` | 29 | корректно `[]` |
| `status=waiting` | 29 | корректно `[]` |
| `status=new` | 11 KB / **50 rows** | 44 success + 5 canceled + 1 error — фильтр **не работает** |
| то же + `includeData=true` | **~660 KB** | полный payload 50 run |

Не вызывать `includeData=true`. Ноду **List new убрать**. Для зомби достаточно `status=running`. Ещё лучше: только `executionTimeout`, без HTTP к своему n8n.

---

## Требования

### 1. Запрос балансов только в 09:00 и по команде

- Убрать cron `* * * * *`.
- Schedule: **один слот 09:00 Europe/Moscow** (например `0 9 * * *` + timezone MSK в Schedule Trigger).
- По Telegram: как сейчас — `/balance` и `/start` сразу дергают HTTP балансов; `/time` может остаться для ответа «daily = 09:00», но **не** для произвольного ежедневного слота, пока снова не понадобится.
- Manual Trigger — ок для отладки.

### 2. Автоматически гасить не прошедшие executions

Предпочтительно **только** `settings.executionTimeout` (уже 90 с) — без HTTP к своему n8n.

Если оставляешь stop-других:

1. Один GET: `.../executions?workflowId={{ $workflow.id }}&status=running&limit=20` — **без** `includeData`.
2. **Не** запрашивать `status=new` (баг API, см. выше).
3. Стопать только `id !== $execution.id` и `startedAt` старше 2 мин.
4. Не ходить в API на каждый Telegram-апдейт, если достаточно timeout.

Не делать minutely watchdog.

После правок: **сначала Manual на inactive workflow**, потом Activate. После серии отменённых зомби — перезапуск контейнера n8n (иначе RAM не падает).

### 3. Не ломать контракт executions

- Не включать workflow, пока пункт 1 не в git и не запушен.
- Не добавлять error-workflow autoresume.
- Merge балансов: либо оставить `combineByPosition` при жёстком timeout, либо `append` + сбор в Code — на усмотрение, главное чтобы одна нога HTTP не держала execution часами.

---

## Приёмка

- [ ] Нет cron каждую минуту; schedule = 09:00 MSK only + Telegram + Manual.
- [ ] Нет ноды `List new` / запросов `status=new`.
- [ ] `/balance` шлёт отчёт. Manual-прогон на **inactive** не роняет RAM/CPU.
- [ ] В 09:01 нет пачки `running`.
- [ ] Зависший HTTP рвётся `executionTimeout` (90 с).
- [ ] `python3 scripts/pull_workflow.py agent-balance-bot` после push совпадает с git.

## Вне скоупа

- Менять пороги `$1` / курс / `OPS_CHAT_ID`.
- Подключать бот к Stage 2 / hierarchy.
- Включать HITL enqueue/send.
