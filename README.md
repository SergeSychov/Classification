# Classification

Production-like агент классификации аптечных товаров на стеке **n8n + PostgreSQL + LLM**.

Полное описание проекта — в [`Categories/PROJECT.md`](Categories/PROJECT.md).

## Быстрый старт

```bash
cp .env.example .env
# заполните N8N_API_KEY

python3 scripts/pull_workflow.py classification-stage2-dev
python3 scripts/push_workflow.py classification-stage2-dev
python3 scripts/run_workflow.py --wait
```

## Структура

| Путь | Назначение |
|------|------------|
| `Categories/` | Документация, ТЗ, планы (см. `stage2_node_map.md`) |
| `workflows/` | JSON workflow + `.id` файлы для n8n |
| `scripts/` | pull/push/deploy скрипты и code-ноды для 2B |
| `.cursor/rules/` | Конвенции для Cursor Agent |

## Workflows на n8n

| Имя | Файл | Роль |
|-----|------|------|
| `ShortList` | `workflows/shortlist.json` | Stage 1: rule-based shortlist |
| `classification-stage2-prepare-for-llm` | `workflows/classification-stage2-prepare-for-llm.json` | Эталон Stage 2 (read-only) |
| `classification-stage2-dev` | `workflows/classification-stage2-dev.json` | Рабочая копия для разработки |
| `polza-qwen-test` | `workflows/polza-qwen-test.json` | Smoke-test Polza.ai + Qwen (Judge) |

## Polza.ai (Judge)

Judge в `classification-stage2-dev` использует **Polza.ai** вместо OpenRouter:

- Нода: `Shared — Polza` (`lmChatOpenAi`)
- Credential: `Polza account` (OpenAI API, Base URL `https://polza.ai/api/v1`)
- Модель: `qwen/qwen3.5-flash-02-23@reasoning_effort=none`

Проверка API:

```bash
python3 scripts/polza_test.py --balance
python3 scripts/polza_test.py --json-test
```

Миграция (уже применена): `python3 scripts/migrate_judge_to_polza.py`
