# Pilot 200 — отчёт Этапа C

Дата: 2026-09-20  
Агент: `bc-369194e9-3e1f-5dcf-a3fb-6c63fa3fcdae`  
Workflow: `classification-stage2-dev` (`BaBjEPi78taRj2G5`)  
Канон: [`project-context.md`](project-context.md), [`ops-readiness-stage-b.md`](ops-readiness-stage-b.md)  
Выборка / runs: Agent Store `internal/pilot-200-selection.md`, `internal/pilot-200-runs.md` (также на Drive — см. [`google-drive-project-mirror.md`](google-drive-project-mirror.md)).  
Expert export: [`pilot-200-expert-export.csv`](pilot-200-expert-export.csv)

## Вердикт

**Ops path PASS · Quality gate NOT CLOSED** (нет human labels).

- Обработано **200 / 200** стратифицированных SKU (20× chunk=10).
- Fin auto-close **20/20** (`finished_with_review` + `finished_at`, без ops-close).
- Failed/stuck runs: **0**.
- Auto classified **41.5%** (ниже hard gate ≥60%); NHR **58.5%** (выше ≤30%) — ориентиры до разметки, не финальный gate.
- Critical / auto-error rate — **не считаем** без экспертной разметки Sheets.

## Пул и выборка

Исходный Load-eligible pending был **47** (<200). Пополнение: временный ShortList по seed `pilot_c_200_seed` (282) → eligible **228** → отбор **200** в `pilot_c_200_selection`. Не-selected 28 держались через `pilot_c_hold` (восстановлены). ShortList query rollback + deactivate. Hierarchy / 0.40/0.60 / Stage 2 Load SQL не менялись.

## Метрики (без expert labels)

| Метрика | Значение | Hard gate |
|---------|----------|-----------|
| N processed | **200** | ≥200 |
| Auto classified (`classified`, ≠human) | **83 (41.5%)** | ≥60% |
| `needs_human_review` | **117 (58.5%)** | ≤30% |
| `error` / leftover pending | **0** | — |
| Fin auto-close (runs 491–510) | **20/20 (100%)** | — |
| Failed/stuck n8n/DB | **0** | — |
| Critical / auto-error | **N/A — нужна Sheets разметка** | ≤1% / ≤3% |

### Final source (auto)

| final_source | N |
|--------------|---|
| llm (P1) | 48 |
| fallback_2b | 35 |
| judge | 0 |

### Routing (unique products reaching stage, runs 491–510)

| Stage | Products |
|-------|----------|
| P1 `primary_llm` | 200 |
| 2A `fallback_2a` | 152 |
| 2B `fallback_2b` | 89 |
| Judge | 53 |

NHR deepest exit (approx): Judge **53**, 2A **32**, P1 **31**, 2B **1**.

### По стратам (auto vs NHR)

| stratum | classified | NHR |
|---------|------------|-----|
| dirty_text | 33 | 25 |
| short_shortlist | 15 | 21 |
| type_cosmetic | 18 | 0 |
| type_device_mi | 13 | 16 |
| type_bad | 4 | 24 |
| weak_shortlist | 0 | 30 |
| type_drug | 0 | 1 |

### LLM provider (log actor_name)

- P1: `deepseek-chat` — **200/200**
- Judge: `openai/gpt-4.1-mini` — **53** (Polza-compatible id)
- Healthcheck перед каждым chunk — встроен в Stage 2

## Executions

ShortList: **42921**, **42922**.  
Stage 2: exec **42923…42961** (odd), runs **491–510**. Детали — Agent Store / Drive `internal/pilot-200-runs.md`.

## Human review / quality gate

**Gate critical/auto-error не закрывать** до разметки.

Подготовлено для эксперта:

- все **117** NHR + **~25%** sample auto (**19**) → **136** строк  
- [`pilot-200-expert-export.csv`](pilot-200-expert-export.csv) (+ Agent Store json)  
- колонки `expert_final_category_id`, `expert_is_critical`, `expert_notes` пустые под Sheets

## Blockers / next

1. **Sheets HITL разметка** 136 строк → critical/auto-error rates.
2. Auto **41.5%** / NHR **58.5%** уже ниже/выше volume gates на этой strate — решение о drain **после** labels + разбор weak_shortlist / БАД.
3. ShortList снова inactive (ожидаемо); для следующих волн — явный activate + seed/allowlist.

## Scope не трогали

- Hierarchy live / B4 wiring  
- Пороги 0.40 / 0.60  
- Постоянные правки prod Stage 2 / репо (временный ShortList патч откатан)  
- PR не открывался
