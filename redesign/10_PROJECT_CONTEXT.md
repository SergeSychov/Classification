# Project context

Проект: production-like классификатор аптечных товаров на базе n8n + PostgreSQL.

Технологический контур:
- orchestration: n8n
- database: PostgreSQL
- DB admin: pgAdmin
- code nodes: JavaScript

Ключевые project rules:
- Stage 2 использует `classification_runs` как сущность запуска.
- Один запуск Stage 2 = один `run_id`.
- `product_classification.latest_run_id` должен указывать на текущий запуск.
- Все новые записи в `product_classification_log` должны содержать `run_id`.
- Во всех Code nodes сохраняем входные поля через `...item.json`.
- После каждого LLM шага делаем post-processing: parse JSON, validate fields, compute review flags, prepare snapshot/log payloads.
- Если output модели невалиден или не парсится, нельзя падать молча: нужно логировать reject reason и направлять запись дальше по policy.

Канонический смысл проекта:
- прозрачная маршрутизация;
- production-safe логирование;
- минимально инвазивные изменения;
- воспроизводимость результата;
- human-in-the-loop для спорных кейсов.

## Status pointer (2026-07-20)

- Status board: [`00_PROJECT_STATUS.md`](00_PROJECT_STATUS.md)
- Approved hierarchy migration design v1: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md)
- Hierarchy cascade: **approved design**; **§13 cleared** (see `21a`/`21b`/`21`/`22`); B1/B2 unblocked, not started
- Current Stage 2 remains the only implemented LLM classification pipeline
