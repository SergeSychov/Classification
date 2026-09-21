# Classification

Production-like агент классификации аптечных товаров на стеке **n8n + PostgreSQL + LLM**.

Репозиторий **public** — удобно шарить с внешним читателем (в т.ч. Grok). Точка входа для обзора проекта:

1. **[`docs/project-context.md`](docs/project-context.md)** — канон целей и ограничений  
2. **[`docs/product-goal-and-plan.md`](docs/product-goal-and-plan.md)** — план / stages  
3. **[`docs/classification-pipeline-diagram.md`](docs/classification-pipeline-diagram.md)** — схема пайплайна (+ [PNG](docs/media/classification-pipeline-diagram.png), [draw.io](docs/classification-pipeline.drawio))  
4. **[`docs/pilot-200-report.md`](docs/pilot-200-report.md)** — пилот 200 SKU  
5. **[`Categories/PROJECT.md`](Categories/PROJECT.md)** — техническое описание репо

## Что где (карта для внешнего читателя)

| Путь | Назначение |
|------|------------|
| `docs/` | Снимок Project Context: план, ops, failover, Fin, пилот, промпты, схема, Drive mirror, CSV экспорты |
| `docs/media/` | PNG схемы пайплайна |
| `Categories/` | Контракты Stage 2 / n8n executions / LLM healthcheck |
| `workflows/` | JSON workflow + `.id` для n8n (канон код) |
| `scripts/` | pull/push/run и helpers |
| `redesign/` | Hierarchy redesign (вне MVP cutover) |

### Docs snapshot (Context mirror)

| Документ | Тема |
|----------|------|
| [`docs/project-context.md`](docs/project-context.md) | Цели, gates, статус |
| [`docs/product-goal-and-plan.md`](docs/product-goal-and-plan.md) | План продукта |
| [`docs/ops-readiness-stage-b.md`](docs/ops-readiness-stage-b.md) | Ops readiness Этап B |
| [`docs/llm-failover-deepseek-qwen.md`](docs/llm-failover-deepseek-qwen.md) | DeepSeek → Qwen failover |
| [`docs/fin-auto-close-fix.md`](docs/fin-auto-close-fix.md) | Fin auto-close |
| [`docs/pilot-200-report.md`](docs/pilot-200-report.md) | Пилот 200 |
| [`docs/pilot-200-expert-export.csv`](docs/pilot-200-expert-export.csv) / [`full`](docs/pilot-200-full-export.csv) | Экспорты пилота |
| [`docs/classification-scheme-prompts.md`](docs/classification-scheme-prompts.md) | Схема + полные промпты |
| [`docs/google-drive-project-mirror.md`](docs/google-drive-project-mirror.md) | Зеркало на Google Drive |

Сырой `internal/` evidence в этот snapshot **не** входит (часть — на Drive `internal-evidence`).

## Быстрый старт

```bash
cp .env.example .env
# заполните N8N_API_KEY

python3 scripts/pull_workflow.py classification-stage2-dev
python3 scripts/push_workflow.py classification-stage2-dev
python3 scripts/run_workflow.py --wait
```

## Workflows на n8n

| Имя | Файл | Роль |
|-----|------|------|
| `ShortList` | `workflows/shortlist.json` | Stage 1: rule-based shortlist |
| `classification-stage2-prepare-for-llm` | `workflows/classification-stage2-prepare-for-llm.json` | Эталон Stage 2 (read-only) |
| `classification-stage2-dev` | `workflows/classification-stage2-dev.json` | Рабочая Stage 2 (live-synced, 73 nodes: healthcheck + failover) |
| `classification-llm-healthcheck` | `workflows/classification-llm-healthcheck.json` | Probe DeepSeek Agent → Qwen/Polza |
| `polza-qwen-test` | `workflows/polza-qwen-test.json` | Smoke-test Polza.ai + Qwen (Judge) |

Контракты: `Categories/n8n_execution_contract.md` (rule 8 — healthcheck перед chunk), `Categories/llm_provider_healthcheck.md`, `Categories/stage2_workflow_contract.md`.

## Polza.ai (Judge)

Judge в `classification-stage2-dev` использует **Polza.ai**:

- Нода: `Shared — Polza` (`lmChatOpenAi`)
- Credential: `Polza account` (OpenAI API, Base URL `https://polza.ai/api/v1`)
- Модель: `qwen/qwen3.5-flash-02-23@reasoning_effort=none`

P1/2A/2B после healthcheck могут идти на DeepSeek **или** Qwen/Polza; Judge всегда Qwen.

```bash
python3 scripts/polza_test.py --balance
python3 scripts/polza_test.py --json-test
```
