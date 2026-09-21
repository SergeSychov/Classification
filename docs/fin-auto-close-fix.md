# Fin auto-close fix — Stage 2

Дата: 2026-09-20  
Агент: `bc-230d0bad-05b4-5f0d-aa9e-4f38ef171622`  
Live: `classification-stage2-dev` (`BaBjEPi78taRj2G5`)  
PR: https://github.com/SergeSychov/Classification/pull/2 · branch `cursor/fin-auto-close-1622`

## Root cause

`Fin — Pick Run` считал **число pulse’ов** `Fin — Merge Barrier` (`staticData fin_close_count_*` vs `batch_size`). Merge coalescit Upsert+Insert в переменное число вызовов (часто 3–4 при batch=5) → close не срабатывал при n8n `success`. Evidence failover: runs 484/486 miss, 485 hit.

Попытка №1 (`$('DB — Upsert Snapshot').all()`) тоже FAIL: parallel item linking не отдаёт sibling upserts.

## Fix (minimal)

`Fin — Pick Run`: набор unique `product_id` из `$input` по pulse’ам Merge → staticData; close при `seen >= loaded batch`; guard `fin_closed_${runId}`; legacy counter удаляется. Hierarchy / 0.40/0.60 / LLM failover не трогались.

## Verify

| # | exec | run | DB |
|---|------|-----|-----|
| 1 | 42915 | 488 | `finished_with_review` |
| 2 | 42917 | 489 | `finished_with_review` |
| 3 | 42919 | 490 | `finished` |

**PASS 3/3** auto-finish + `finished_at` (без ops-close).  
Pre-fix miss: run 487 ops-`crashed` (upsert-`$all` attempt).

Evidence: Agent Store `internal/fin-auto-close-smoke.md` (не в snapshot).
