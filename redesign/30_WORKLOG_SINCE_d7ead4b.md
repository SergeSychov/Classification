# Worklog since last commit

**Baseline commit:** `d7ead4ba` — *Record Wave-100 Sem validation run and export artifacts.* (2026-07-30)
**Document date:** 2026-08-10
**Scope:** uncommitted local work + n8n test workflows / offline harnesses created after that commit.
**Prod Stage 2 / SQL DDL:** not changed. Hierarchy-dev remains snapshot-off / kill-switch safe by default.

---

## Summary

После Wave-100 (exec 19932) проделан большой пласт по Sem-каскаду (Sem0 → Sem1 → Norm attrs → Wave-500), затем отдельная линия **offline MNN** (каталоги, Polza+Exa, tool-search bakeoff Qwen/DeepSeek) и тестовые n8n workflow’ы (Qwen search smoke, DeepSeek AI Agent + RU web search). В prod cascade ничего из MNN-web-search **не влито**.

---

## 1. Hierarchy Sem pipeline (n8n `classification-stage2-hierarchy-dev`)

### 1.1 Sem0 product_kind + Sem1 attr_profile

- Добавлена зона **Sem0** перед Sem1: `product_kind` / `product_family` / `attr_profile`, soft-continue в Sem1.
- Политики и версии промптов:
  - v1 → **v2** (`prompt_sem0_v2` / `prompt_semantic_v3`) — журнал п.29–30
  - **v3/v4** после markt-разбора Wave-100 (`prompt_sem0_v3` / `prompt_semantic_v4`) — п.32
  - **rules patch** (`sem0_v3_rules1` / `prompt_semantic_v5`) — шприцы, `rx_otc`, vitamin MNN — п.34
- Node sources: `scripts/hierarchy_nodes/sem0_*.js`, обновления `sem_build_prompt.js` / `sem_post_process.js`, патчеры `_b3_patch_sem0.js`, `_b3_patch_sem.js`.

### 1.2 Norm — Normalize Sem attrs

- Code-нода после Sem1 Post-process: словари route / form / age (и далее `rx_otc`).
- Sources: `scripts/hierarchy_nodes/sem_normalize_attrs.js`, `sem_attr_dictionaries.md`, fixtures `scripts/sem_normalize_attrs_fixtures.test.mjs`.
- Smoke: exec **29035** (N≈15). Журнал п.31.

### 1.3 Wave runs & tooling

| Run | Mode | Result / artifacts |
|-----|------|-------------------|
| Wave-100 v2 (Sem0+v2) | chunked 10×10 (execs ~21611…21659) | rerun после policy v2; progress tooling |
| Wave-500 | chunked 50×10, allowlist N=500 | **500/500**; ~7.7 h wall; seed `sem_wave500_2026-08-04` |
| Policy / rules smokes | mini allowlists | `sem_policy_v3_*`, `sem_rules_patch_*`, `sem0_smoke_*` |

Kind mix Wave-500: drug **224**, vitamin_or_baa **101**, cosmetic_hygiene **75**, medical_device **68**, other **32**.

Ключевые скрипты: `scripts/wave100_chunked_run.py`, `scripts/wave_progress.py`, `scripts/run_hierarchy_workflow.py`, `scripts/sem_smoke_export.py`, `scripts/sem_smoke_settings_via_n8n.py`.

Артефакты: `redesign/artifacts/sem_wave500_report.csv`, `sem_wave500_summary.md`, `sem_wave500_allowlist.json`, wave chunk JSON, progress logs.

Журнал: `Categories/stage2_workflow_plan.md` (п.29–34+); статус/roadmap: `redesign/00_PROJECT_STATUS.md`, `redesign/29_SHORT_ROADMAP.md`.

**Открыто:** human rubric labeling / `critical_error_rate` для Wave-100/500; Dir+ не стартовал.

---

## 2. Offline MNN enrichment (не в cascade)

### 2.1 Catalog competition → `win_mnn` / `win_rx_otc`

- Скрипт: `scripts/sem_wave500_mnn_from_catalogs.py` (+ vote fixtures).
- Источники: uteka / asna / apteka / vidal / stolichki (+ HTML cache `_catalog_cache/`).
- Итог: `sem_wave500_mnn_from_catalogs.csv` (~245 rows), `win_mnn` filled **194**; smoke5/smoke8/shortquery итерации.
- Summary: `sem_wave500_mnn_from_catalogs_summary.md`.

### 2.2 Polza/Qwen enrichment (без web search)

- `scripts/sem_enrich_mnn_rx.py` + `hierarchy_nodes/enrichment_*.js`.
- Wave-500 eligible **254**, errors **0**; MNN filled **93**.
- Artifacts: `sem_wave500_mnn_rx_enriched.*`. Журнал п.35.
- **Не мержится** в `attr_mnn` / Dir–Need.

### 2.3 Polza + Exa web search (baseline для bakeoff)

- Harness: `scripts/mnn_qwen_web_search_test.py`, resume/conflicts helper, fixtures.
- n8n smoke (отдельный TEST WF): `workflows/classification-stage2-mnn-qwen-search-test-dev.json`.
- Важно: на Polza реален путь `plugins: [{id:"web", engine:"exa"}]`; DashScope `enable_search` игнорируется.
- Drugs run **224**: search confirmed **165**, `found` **144** (coverage ≈0.64).
- Output: `sem_wave500_mnn_from_catalogs_qwen_web_search_test.csv`, `qwen_web_search_test_summary.md`, probes JSON.

### 2.4 MNN tool-search bakeoff (shared `web_search` tool)

Единый контур: OpenAI-compatible `tools` + наш search (Serper → fallback DuckDuckGo Lite); в user только `normalized_text`.

| model | n | found | coverage | p50 ms | total tokens | vs catalog exact+norm | vs Polza agree |
|-------|--:|------:|---------:|-------:|-------------:|----------------------:|---------------:|
| deepseek-v4-pro | 224 | 129 | 57.6% | ~5.9s | ~196k | 91 | ~45.8% |
| qwen3.7-max | 224 | 125 | 55.8% | ~47.5s | ~436k | 92 | ~47.9% |
| qwen3.7-flash | 224 | 107 | 47.8% | ~38.6s | ~640k | 45 | ~28.5% |
| qwen3.8-max | 224 | 50 | 22.3% | ~40.4s | ~403k | 36 | ~19.4% |

Scripts: `prep_mnn_tool_search_slice.py`, `mnn_tool_search_bakeoff.py`, `run_mnn_bakeoff_loop.py`, `run_mnn_tool_search_bakeoff_chunked.sh`.
Input: `sem_wave500_mnn_tool_search_input.csv`.
Outputs: `mnn_tool_search_{slug}.csv` + `*_raw.jsonl`, `mnn_tool_search_bakeoff_summary.md`.

`.env.example`: `DASHSCOPE_API_KEY`, `DEEPSEEK_API_KEY`, `SERPER_API_KEY`.

### 2.5 Provider smoke notes (test-only n8n / API)

- **Alibaba Cloud / DashScope:** credential работает на **Singapore / dashscope-intl**; Beijing/US/HK → `invalid_api_key`. Баланс по API key недоступен — смотреть `usage`.
- **DeepSeek Responses API + built-in `web_search`** на `deepseek-v4-flash`: probe OK (`/responses`); текст ответа часто в `output[].message.content`, не в `output_text`.
- **n8n AI Agent + native DeepSeek:** WF `[TEST] DeepSeek MNN — AI Agent web_search RU`
  - id: `OsVinOCuNdZZKNp2`
  - file: `workflows/deepseek-flash-mnn-responses-test.json` (+ `.id`)
  - Manual + webhook `POST /webhook/test/deepseek-flash-mnn`
  - CSV read inside WF: `/files/sem_wave500_mnn_tool_search_input.csv`
  - prompts in Config; tool `web_search_ru` (Code Tool → DDG Lite, `kl=ru-ru` + `site:.ru`)
  - model: **`deepseek-chat`** (не flash: thinking/`reasoning_content` ломает Agent+tools multi-turn в n8n)
  - smoke limit=1: Ascorutin → found, RU search used.

---

## 3. Repo / tooling changes (high level)

### Modified (tracked)

- `workflows/classification-stage2-hierarchy-dev.json` (+ sem-smoke backup)
- Sem node scripts under `scripts/hierarchy_nodes/`
- `Categories/stage2_workflow_plan.md` (крупное дополнение журнала)
- `redesign/00_PROJECT_STATUS.md`, `redesign/29_SHORT_ROADMAP.md`
- Wave-100 report/rubric artifacts (обновления)
- `.env.example`

### New (selected)

- Hierarchy: Sem0 / Norm attrs / enrichment / MNN Qwen search node sources + fixtures
- Offline harnesses: catalogs, enrich, qwen web search, tool-search bakeoff, wave runners
- Workflows: MNN Qwen search TEST; DeepSeek AI Agent TEST
- Artifacts: Wave-500 reports, MNN catalogs/enrich/web-search/bakeoff summaries, allowlists, chunk JSON, run logs
- Large: `redesign/artifacts/_catalog_cache/` (HTML cache, thousands of files) — runtime cache, не для осмысленного review построчно

---

## 4. Explicitly out of scope / not done

- Merge web-search / bakeoff / enriched MNN into Sem `attr_mnn` or Dir–Need–Mnn cascade
- Changes to production `classification-stage2-dev`
- Human labeling / formal Wave-100 & Wave-500 gate scoring
- Full offline harness для DeepSeek Flash Responses (опционально отменено после n8n Agent WF)
- Commit/push этого worklog и артефактов — **не делался** (только создание описания)

---

## 5. Suggested next steps

1. Human rubric на Wave-500 (и/или Wave-100 v2) → `critical_error_rate`.
2. Spot-check `mnn_enriched` / catalog `win_mnn` / Polza Exa / bakeoff winners → выбрать источник для cascade.
3. Если нужен Agent+tools на Flash — ждать/чинить n8n↔DeepSeek `reasoning_content`, либо оставить `deepseek-chat`.
4. Перед commit: решить, что коммитить из artifacts (reports/summaries vs `_catalog_cache` / raw jsonl / pids/logs).

---

## 6. M3 RX/OTC research closeout (2026-08-19)

- M3.0 → M3.2b.5 research **closed / paused**. Decision: **`KEEP_RX_OTC_P2_SUPPORT_ONLY`** and **`DO_NOT_RUN_PHASE_A_YET`**.
- No production / hierarchy-dev / PostgreSQL / `classification_runs` / snapshot / `attr_*` / `product_kind` changes. Workflow `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`) remains inactive. M3.2c not run.
- Scoped Git checkpoint planned (docs + isolated research tooling + compact artifacts only). Raw JSONL / caches / cookies / HTML dumps excluded.
- Next main offline track after M3 closeout was **M4** Age (now done, п.45). Do not start M4 in this M3 closeout section.

---

## 7. M4 Age pilot contract (2026-08-19)

- M4.0–M4.2.2 **validated** as offline/audit-only. Canonical freeze: `mnn_age_threshold_reconciliation_reviewed_v1_1.*`. Journal **п.45**.
- Threshold (integer 0–18) is separate from segment. 12/14/15/16/10 + child+adult → universal. Adults only at 18+. `10046` min=10 accepted; not remapped to 6/12.
- No snapshot / `attr_age_segment` / Sem / DB / n8n. Git checkpoint: docs + M4 scripts + compact Age artifacts (no raw JSONL / caches).
- Next offline: **M5** Norm v4.

---

## 8. Quick pointers

| Topic | Where |
|-------|--------|
| Journal Sem0→Wave-500→enrich | `Categories/stage2_workflow_plan.md` п.29–35 |
| Wave-500 Sem summary | `redesign/artifacts/sem_wave500_summary.md` |
| Catalog win_mnn | `redesign/artifacts/sem_wave500_mnn_from_catalogs_summary.md` |
| Polza+Exa MNN | `redesign/artifacts/qwen_web_search_test_summary.md` |
| Tool-search bakeoff | `redesign/artifacts/mnn_tool_search_bakeoff_summary.md` |
| DeepSeek Agent WF | `workflows/deepseek-flash-mnn-responses-test.json` |
| Hierarchy WF | `workflows/classification-stage2-hierarchy-dev.json` |
