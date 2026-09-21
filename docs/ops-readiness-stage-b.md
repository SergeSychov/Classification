# Этап B — Ops readiness Stage 2

Дата: 2026-09-20 (LLM failover + **Fin auto-close fix**)  
Агенты: Stage B `bc-225b554d…`; smoke retry `bc-b493bf26…`; failover `bc-4958a021…`; **Fin** `bc-230d0bad-05b4-5f0d-aa9e-4f38ef171622`  
Канон: [`project-context.md`](project-context.md), [`product-goal-and-plan.md`](product-goal-and-plan.md), [`llm-failover-deepseek-qwen.md`](llm-failover-deepseek-qwen.md), [`fin-auto-close-fix.md`](fin-auto-close-fix.md)  
Репо: `Categories/n8n_execution_contract.md` rule 8, `Categories/llm_provider_healthcheck.md`, `stage2_workflow_contract.md` § DB+Fin  
PR failover [#1](https://github.com/SergeSychov/Classification/pull/1) · PR Fin [#2](https://github.com/SergeSychov/Classification/pull/2)

## Вердикт Этапа B

**PASS (LLM path via Qwen + Fin auto-close)** — 2026-09-20. DeepSeek LangChain Agent на AdminVPS **всё ещё 403 geo**; failover Qwen/Polza сохранён. Fin barrier: close по unique `product_id` из Merge pulses (не счётчик вызовов). Smoke 3× batch=5 после фикса: runs **488** / **489** / **490** → terminal + `finished_at` без ops-close. Hierarchy / пороги 0.40/0.60 не менялись.

Evidence: Agent Store `internal/fin-auto-close-smoke.md` · failover: `internal/llm-failover-smoke.md` (не в snapshot; см. Drive mirror).

---

## 1. Runbook

### Предусловия

| # | Что | Как |
|---|-----|-----|
| 1 | `.env` / env | `N8N_URL`, `N8N_API_KEY` |
| 2 | SSH `vps-dokploy` | `root@5.35.127.249` |
| 3 | Credentials в n8n | `Postgres account`, `DeepSeek account`, `Polza account` |
| 4 | Active workflows | `classification-stage2-dev` (`BaBjEPi78taRj2G5`), **`classification-llm-healthcheck` (`AS3d7jZXevM1K3n5`)**, batch-acceptance |

### Правила исполнения

1. Один live execution на workflow; idle перед новым webhook.
2. Chunk ≤ 10; smoke default **5**.
3. Stop stuck > 30 мин перед новым run.
4. **Перед каждым chunk** Stage 2 сам вызывает LLM healthcheck (DeepSeek→Qwen).
5. Не трогать hierarchy live и пороги 0.40 / 0.60.

### Smoke

```bash
python3 scripts/run_workflow.py --batch-size 5 --wait --timeout 900
# ×3 с idle между (скрипт сам ensure_idle + healthcheck idle)
```

Healthcheck manual: `POST /webhook/classification-llm-healthcheck`

---

## 2. Чеклист ops readiness

| # | Проверка | Статус 2026-09-20 Fin fix |
|---|----------|--------------------------|
| C1 | n8n UI | **PASS** |
| C2 | `N8N_API_KEY` | **PASS** |
| C3 | SSH AdminVPS | **PASS** (`root@5.35.127.249`) |
| C4 | Webhook Stage 2 | **PASS** active |
| C5 | ShortList webhook | **FAIL (info)** inactive |
| C6 | Creds Postgres / DeepSeek / Polza | **PASS** (+ healthcheck uses same) |
| C7 | `classification_runs` finish | **PASS** — 488/489/490 auto-finish |
| C8 | Единый `run_id` snapshot/log | **PASS** |
| C9 | Snapshot + log на batch | **PASS** |
| C10 | Stage routing P1→… | **PASS** via Qwen Agents |
| C11 | Sheets HITL | **PARTIAL** — Fin closes; BA wire still optional gap |
| C12 | Sheets writeback human | **NOT RUN** (gap) |
| C13 | 3× smoke batch=5 | **PASS** Fin auto-close 3/3 |

---

## 5. Итог прогонов (Fin fix verify)

| # | batch | n8n exec | run id | status | Pass? |
|---|-------|----------|--------|--------|-------|
| 1 | 5 | 42915 | 488 | `finished_with_review` | **PASS** |
| 2 | 5 | 42917 | 489 | `finished_with_review` | **PASS** |
| 3 | 5 | 42919 | 490 | `finished` | **PASS** |

Provider: **qwen** (failover). Pre-fix: 487 ops-`crashed` (bad upsert-`$all` attempt); failover-era 484/486 were Fin-miss before this fix.

---

## 6. Blockers

1–3. ~~API / SSH / Activate Stage 2~~ — снято.
4. **DeepSeek Agent 403** — **mitigated** failover Qwen/Polza.
5. ~~Fin barrier flaky~~ — **fixed** (PR #2); verify 488–490.
6. ShortList inactive — info (для пилота C временно активировали seed→rollback).
7. Sheets writeback human — **следующий шаг** после export пилота C.
8. `Fin — Batch Acceptance` connection empty on Close Run — residual (не блокер auto-close).

---

## 7. Scope не трогали

- Hierarchy live / B4.
- Пороги 0.40 / 0.60.
- Telegram mass HITL.
- LLM healthcheck/failover wiring (сохранено).

---

## 8. Этап C — pilot 200 (статус)

**Ops DONE** 2026-09-20: 200 SKU, runs **491–510**, Fin close 20/20.  
Quality gate — **открыт** до Sheets labels. См. [`pilot-200-report.md`](pilot-200-report.md).
