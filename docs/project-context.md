# Project Classification — канон контекста

Краткий канон целей, ограничений и **подтверждённых** решений go-live. Детали плана: [`product-goal-and-plan.md`](product-goal-and-plan.md).

Код и репо-канон `Categories/stage2_workflow_plan.md` **не трогаем** до результатов трёх tech-прогонов / пилота.

---

## Цель

Production-like категорирование аптечных SKU: ShortList → Stage 2 (LLM rounds + Judge) → auto-close уверенных кейсов; сомнительные — человеку через Sheets. Не додумывать — эскалировать.

---

## Ограничения

- Один live execution на workflow; chunk ≤ 10; stop stuck > 30 мин (`n8n_execution_contract`).
- Prod Stage 2 и live hierarchy **не** менять redesign’ом / B4 wiring.
- Пороги borderline **0.40 / 0.60** не менять до пилота.
- Telegram не primary HITL.
- `stage2_workflow_plan.md` в репо — только после tech runs + пилот.

---

## Принятые решения (CONFIRMED)

1. **MVP:** ShortList → `classification-stage2-dev` → Sheets HITL. Hierarchy **не** в cutover.
2. **HITL:** Sheets — единственный primary; Telegram — неактивный/вспомогательный.
3. **Quality gate:** ≥200 SKU (при необходимости 500); critical ≤1% (цель 0%); auto-classified errors ≤3%; `needs_human_review` ≤30% (цель ≤20%); auto classified ≥60% (цель ≥70%); 3× prod-like 5–10 SKU без failed/stuck; 100% run_id/tracking; 100% HITL writeback `final_source=human`. Critical = неверный `final_category_id` у auto-classified относительно эксперта (чужая категория/ветка).
4. **Объём:** пилот 200 стратифицированных → 500–1000 чанками → весь pending только после gates.
5. **Hierarchy:** live на паузе; только параллельный B4 design без live-wiring / snapshot / SQL-write / изменений prod Stage 2.
6. **Последовательность:** Этап B (ops readiness) → pilot 200 → решение о drain.

---

## Статус Этапа C (2026-09-20)

Controlled pilot **200 SKU** выполнен (ops): 20×10, Fin auto-close 20/20, failed/stuck 0.  
Auto **41.5%** / NHR **58.5%** (до labels). Quality gate critical/auto-error — **не закрыт** (нужна Sheets разметка).  
Отчёт: [`pilot-200-report.md`](pilot-200-report.md).
