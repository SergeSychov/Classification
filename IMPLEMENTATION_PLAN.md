# План выхода из pre-implementation limbo

Дата анализа: 2026-09-21  
Канон go-live: [`docs/project-context.md`](docs/project-context.md), [`docs/product-goal-and-plan.md`](docs/product-goal-and-plan.md)  
Этот файл — **только план**. Код пайплайна не трогался.

---

## 1. Проект в одном абзаце

**Classification** — агент автоматического категорирования аптечных SKU для команды каталога: название/описание + справочник `categories_dict` → партиями через n8n (`https://n8n.sychovtest.ru`) + PostgreSQL + LLM. Принцип: уверенное решение фиксируется (`classified` + `final_category_id`); при сомнении товар эскалируется, а не «додумывается». Рабочий MVP-путь уже существует: Stage 1 `ShortList` (`workflows/shortlist.json`, id `7hx7k2mhJCbA57BG`) → Stage 2 `classification-stage2-dev` (`BaBjEPi78taRj2G5`, 73 ноды: P1 → 2A → 2B → Judge, healthcheck DeepSeek→Qwen) → human path через Google Sheets. Hierarchy-clone `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`) — параллельный R&D, **не** входит в cutover ([`docs/product-goal-and-plan.md`](docs/product-goal-and-plan.md) §MVP).

Пользователи: контент/каталог аптечной номенклатуры. Проблема: ручная разметка большого потока SKU, неоднородность категорий, отсутствие прозрачного batch-аудита.

---

## 2. Зрелость (не «docs-only»)

| Слой | Состояние | Доказательства |
|------|-----------|----------------|
| **Stage 2 prod-like** | **Рабочий код + live runs** | `workflows/classification-stage2-dev.json`; ops smoke runs **488–490**; пилот 200 SKU runs **491–510** ([`docs/ops-readiness-stage-b.md`](docs/ops-readiness-stage-b.md), [`docs/pilot-200-report.md`](docs/pilot-200-report.md)) |
| **Stage 1 ShortList** | Код есть, **сейчас inactive** | `workflows/shortlist.json`; C5 FAIL(info) в ops checklist |
| **HITL Sheets export** | Workflow есть, **writeback не сделан** | `workflows/classification-batch-acceptance.json`; контракт [`Categories/batch_acceptance_contract.md`](Categories/batch_acceptance_contract.md) §«Разбор ошибок Sheet A» = «следующий этап» |
| **Telegram HITL** | В репо, **не primary** | `workflows/classification-human-review-*.json`; writeback SQL уже есть в `classification-human-review-callback.json` |
| **Hierarchy redesign** | Partial code + **много design-docs**; live Load = `WHERE false` | `workflows/classification-stage2-hierarchy-dev.json` (94 ноды); Sem0→Sem1→attr Norm на live path; Dir = static stub `need_not_implemented_static`; N1-T seam disarmed |
| **Offline R&D** | Скрипты + freeze-артефакты, **не влиты** | `scripts/mnn_*`, `scripts/run_rx_otc_*`, `redesign/artifacts/` (~287 файлов) |
| **GitHub process** | **0 issues, 0 milestones** | Draft PR #1/#2 всё ещё OPEN; содержимое уже на `main` через PR #3 (2026-09-21) |

Итог: это **частично production-like пайплайн с незакрытым human-контуром**, а не пустой прототип. «Limbo» — не отсутствие кода, а (а) незакрытый quality gate пилота 200 и (б) иерархический трек, который пишет дизайн быстрее, чем чинит одну строку JS.

Объёмы репо (ориентир): ~118 `.md`, ~73 `.py`, 13 workflow JSON, журнал `Categories/stage2_workflow_plan.md` > 2200 строк. Сентябрь: 3 коммита на `main` до snapshot vs 19 в июле / 22 в августе — плюс пачка агентных прогонов 20.09, которые попали в `docs/` через PR #3, но **не** в журнал (`stage2_workflow_plan.md` заморожен политикой в `docs/project-context.md`).

---

## 3. Что уже есть vs что только обсуждается

### Есть и проверено runtime

- Stage 2: primary / 2A / 2B / Judge; `classification_runs` + snapshot + log; пороги 0.40 / 0.60 ([`Categories/stage2_workflow_contract.md`](Categories/stage2_workflow_contract.md)).
- LLM healthcheck + failover P1/2A/2B на Qwen/Polza при 403 DeepSeek Agent ([`Categories/llm_provider_healthcheck.md`](Categories/llm_provider_healthcheck.md), `workflows/classification-llm-healthcheck.json`).
- Fin auto-close по unique `product_id` из Merge (runs 488–490, 491–510) ([`docs/fin-auto-close-fix.md`](docs/fin-auto-close-fix.md)).
- Контракт executions: 1 live run / workflow, chunk ≤ 10, zombie > 30 мин ([`Categories/n8n_execution_contract.md`](Categories/n8n_execution_contract.md)).
- Пилот 200: 20×10, Fin 20/20, failed/stuck 0; CSV [`docs/pilot-200-expert-export.csv`](docs/pilot-200-expert-export.csv) (колонки `expert_*` **пустые**).
- Hierarchy Sem Wave-100 exec **19932** rubric PASS `1/171 ≈ 0.58%` (журнал п.51).
- B1 additive schema + B2 clone + B3 Norm/Sem в hierarchy-dev ([`redesign/00_PROJECT_STATUS.md`](redesign/00_PROJECT_STATUS.md)).

### Есть код, но это stub / inactive / не wired

| Что | Файл | Факт |
|-----|------|------|
| Hierarchy Load | `Load — Select Batch` в hierarchy-dev | SQL `WHERE false` — 0 товаров |
| Direction | `Dir — Candidate Builder` / `Dir — Static Post-process` | `candidate_scope_status=not_loaded_static`, `stop_reason=need_not_implemented_static` |
| N1-T seam | `N1-T — Gate Eval/IF/Stub Emit` | `N1_T_ONE_SHOT_ARMED = false`; runtime FAIL exec **42880** / run **476** |
| RX/OTC | `workflows/rx-otc-product-retrieval-dev.json` | inactive; политика `KEEP_RX_OTC_P2_SUPPORT_ONLY` |
| Telegram review | `classification-human-review-*` | деактивированы; primary = Sheets |
| `agent-balance-bot` | `workflows/agent-balance-bot.json` | **не включать** watchdog (`Categories/agent_balance_bot_task.md`) |
| Fin → Batch Acceptance | `Fin — Close Run` в stage2-dev | **исходящие connections пустые** (`"main": [[]]`); нода BA есть, не вызывается |
| Sheet A/B writeback | контракт §импорт | **не реализован** (C12 NOT RUN) |

### Только план / freeze / «explicit ask»

- Hierarchy cascade Dir→Need→Cat→Mnn→Judge: [`redesign/20_MIGRATION_PLAN.md`](redesign/20_MIGRATION_PLAN.md), [`redesign/12_REDESIGN_TARGET.md`](redesign/12_REDESIGN_TARGET.md).
- B4 N1-T: семь дизайн-доков за один день (`redesign/40_`…`46_`) до одного runtime, который упал на `typeof number`.
- M3 RX P1, M4 Age → `attr_age_segment`, M5.1 overwrite `normalized_text`, Wave-500 Sem, Manufacturer Alias Dictionary — **не вливать** без отдельного решения.
- `Categories/multi_agent_plan.md` и §«Следующий этап» в `stage2_project_description.md` **устарели** (2A/2B/Judge уже закрыты).
- `redesign/00_PROJECT_STATUS.md` внутри себя противоречит: сверху Wave-100 PASS / next = B4 design; внизу «Next gate» всё ещё «human rubric labeling for Wave-100».

---

## 4. Топ-5 блокеров внедрения (реальные, не абстрактные)

1. **Quality gate пилота 200 не закрыт, потому что нет экспертной разметки.** Ops PASS, quality NOT CLOSED. Auto **83/200 = 41.5%** (hard ≥60%), NHR **117/200 = 58.5%** (hard ≤30%). `expert_final_category_id` / `expert_is_critical` в CSV пустые. Без этого нельзя ни drain pending, ни честно менять пороги 0.40/0.60. Источник: [`docs/pilot-200-report.md`](docs/pilot-200-report.md).

2. **Human writeback в БД отсутствует.** Контракт Sheets описывает экспорт A/B, но импорт `ok=нет` / выбранной категории → `final_source=human` помечен как «следующий этап». Ops C11 PARTIAL, C12 NOT RUN. Close Run **не соединён** с `Fin — Batch Acceptance`. Цикл «модель → человек → snapshot» дырявый: эксперт может разметить Sheets, система об этом не узнает. Источники: [`Categories/batch_acceptance_contract.md`](Categories/batch_acceptance_contract.md), `workflows/classification-stage2-dev.json` (connections `Fin — Close Run`).

3. **Культура «explicit ask» на hierarchy съедает календарь.** 12.09 N1-T: design → package → contract resolution → eligibility SQL → operator lock → local-only impl → Mode C SQL → G3 arming → push → fresh-pull → preflight → one-run approval → FAIL на `coerceFiniteNumber` (`scripts/hierarchy_nodes/n1_t_gate_v1.js` принимает только `typeof number`; Postgres отдал `"55"` / `"476"`) → hard stop «remediation не авторизована». Семь markdown (`redesign/40`–`46`) + журнал п.B4.3B-T ради **не** реализации Direction. Это и есть limbo. При этом go-live уже **CONFIRMED**: hierarchy live на паузе ([`docs/project-context.md`](docs/project-context.md) пункт 5).

4. **Два канона «что дальше».** `docs/*` (20.09): Этап B DONE, Этап C ops DONE, дальше Sheets labels. `Categories/PROJECT.md` / `redesign/29_SHORT_ROADMAP.md` (09.09): next = B4 soft design. Журнал `stage2_workflow_plan.md` заморожен и **не знает** про failover, Fin-fix и пилот 200. Нет GitHub issues — приоритет живёт в конкурирующих markdown.

5. **Авто-rate уже провален на стратах, которые код мог бы чинить — но чинить их до labels запрещено политикой порогов.** `weak_shortlist` 0 classified / 30 NHR; `type_baa` 4/24; Judge дошёл до **53** товаров, `final_source=judge` = **0**. DeepSeek LangChain Agent на AdminVPS по-прежнему 403 geo (mitigated Qwen). ShortList inactive. 21 stale `classification_runs` `running` (preflight 12.09). Это операционный и качественный долг MVP, не hierarchy.

---

## 5. Предлагаемый MVP (самый маленький shippable slice)

Совпадает с уже **CONFIRMED** решением в `docs/product-goal-and-plan.md`. Не придумывать третий MVP.

### IN

- Stage 1 ShortList (активировать только на время волны, затем rollback — как в пилоте C).
- Stage 2 `classification-stage2-dev` as-is (пороги 0.40/0.60 **не** трогать до закрытия quality gate).
- LLM healthcheck + Qwen failover (уже в live JSON).
- Fin auto-close (уже в live JSON).
- Sheets HITL: экспорт 136 строк пилота → эксперт → **writeback** `final_source=human` + log `stage=human_review`.
- Скрипт метрик quality gate по заполненному CSV (critical ≤1%, auto-error ≤3%).
- Один канон статуса: `docs/project-context.md`. Одна GitHub issue на writeback, одна на quality gate.

### OUT (не в ближайшие 1–2 недели, не блокируют ship)

- Hierarchy B4 live / Dir LLM / Need / Cat / Mnn / Wave-500 / N1-T retry (кроме явного «не делать»).
- Merge MNN / RX / Age в `attr_*` / snapshot.
- Norm v4.1 overwrite `normalized_text`.
- Telegram как primary HITL; массовая активация `agent-balance-bot` watchdog.
- RX Phase A / GRLS P1 (`KEEP_RX_OTC_P2_SUPPORT_ONLY`).
- Переписывание prod Stage 2 под cascade.
- Новые design-only файлы в `redesign/40+`.
- Drain всего pending-пула.
- Правки эталона `classification-stage2-prepare-for-llm`.

---

## 6. Последовательность на 1–2 недели

Опора: Этап B PASS, пилот ops PASS. Код только там, где без него gate не закроется. Параллельно — **человек** размечает CSV (это не агентная задача).

| День | Что | Done-when | Не делать |
|------|-----|-----------|-----------|
| **1 (завтра)** | Код: writeback пилота (задача §8) | 1 NHR-строка с заполненным `expert_final_category_id` → snapshot+log; dry-run по умолчанию | Hierarchy, пороги, N1-T |
| **1–3** | Процесс: эксперт заполняет 136 строк CSV / Sheets | `expert_final_category_id` не пустой у всех 117 NHR + 19 auto-sample | Ждать «идеальный» UI |
| **2** | Код: `scripts/pilot200_quality_gate.py` считает critical / auto-error / auto% / NHR% по CSV | Печатает таблицу vs hard gates из `docs/project-context.md` | Менять промпты |
| **3** | Ops: прогнать writeback на все валидные expert-строки (chunked, 1 live exec если через n8n; иначе один Python-проход) | C12: 100% размеченных NHR с `final_source=human` | Telegram enqueue |
| **4** | Провод: `Fin — Close Run` → `Fin — Batch Acceptance` в **dev-копии** + один smoke batch=5 | После Close появляется/обновляется `batch_acceptance` для `run_id`; rollback если BA падает | Менять BA-логику экспорта |
| **5** | Разбор страт **после** labels: `weak_shortlist`, `type_baa`, Judge 53→0 classified | Запись в issue: 3 конкретные гипотезы с product_id из CSV | Wave-500, B4 |
| **6–8** | Только если critical PASS, а auto% всё ещё <60%: **один** targeted фикс (сначала ShortList keywords для weak_shortlist **или** Judge «может classified», не оба) + 1 smoke 10 SKU той же страты | Метрика страты улучшилась на повторном chunk; `prompt_version` / shortlist versionBump | Пороги 0.40/0.60, hierarchy |
| **9–10** | Решение go/no-go drain 500 | Issue с цифрами; ShortList activate+seed только под волну | Полный pending drain |

Если labels задерживаются — **не** заполнять паузу N1-T/B4 docs. Разрешённый фон: закрыть draft PR #1/#2 (код уже на `main` через #3); одна SQL-заметка по 21 stale `running` (cleanup только по явному ops-окну); не включать balance-bot.

---

## 7. Tech / process (n8n здесь центральный)

**n8n**

- Контракт [`Categories/n8n_execution_contract.md`](Categories/n8n_execution_contract.md) соблюдать буквально: один live execution, chunk ≤ 10, stop > 30 мин, **не** `status=new` (фильтр сломан, отдаёт 50 любых), не `includeData=true` из workflow.
- CLI: `n8n execute` + `N8N_RUNNERS_BROKER_PORT=15679` (не 5679). CLI игнорирует pinData — Manual `{}` → batch default 5 (`Run — Apply Batch Cap`).
- Postgres в Code-нодах отдаёт **строки**. Любой gate/`Number()` должен принимать `"55"`. Баг N1-T — учебник: `coerceFiniteNumber` в `scripts/hierarchy_nodes/n1_t_gate_v1.js`.
- Merge `combineByPosition` + Agent = все items батча параллельно. Fin close считать по unique `product_id` из `$input`, не по числу pulse (уже починено в Stage 2; hierarchy Pick Run — отдельный риск).
- Не активировать `agent-balance-bot` watchdog (`Categories/agent_balance_bot_task.md`: RAM/CPU standby 18.08).
- Hierarchy-dev: Load держать `WHERE false`, `N1_T_ONE_SHOT_ARMED=false`, пока MVP не закроет quality gate. **Не** чинить N1-T на этой неделе.
- Не писать новые `redesign/4x_*.md` «design only». Следующий hierarchy-код — только после go-live MVP и явного «делаем Dir LLM на allowlist 10», одним PR, без 8 промежуточных гейтов.

**Процесс**

- Один канон: `docs/project-context.md`. `redesign/00_PROJECT_STATUS.md` — статус **hierarchy R&D**, не go-live.
- Завести GitHub issues (сейчас 0): `pilot-200 labels`, `sheets writeback`, `BA wire from Close Run`, `stale running=21`, `close draft PR 1/2`.
- Журнал `stage2_workflow_plan.md` разморозить **одним** апдейтом после writeback+метрик (политика в `docs/project-context.md` уже выполнена по смыслу: 3 tech runs + пилот ops есть).
- Не плодить параллельные агенты на hierarchy и Stage 2 в одном n8n.

---

## 8. Первая кодовая задача на завтра утро

**Название:** writeback экспертной категории из пилота 200 в `product_classification` + log.

**Почему именно это:** единственный закрываемый кодом разрыв MVP-цикла. Labels — человеческая работа параллельно; без writeback даже заполненный CSV не делает продукт. Hierarchy/N1-T — ловушка процесса. Пороги менять рано.

**Где:** новый `scripts/pilot200_sheets_writeback.py` (offline, без n8n). Образец SQL уже есть в `workflows/classification-human-review-callback.json` (resolve → snapshot `final_source=human` + `product_classification_log`). Вход: [`docs/pilot-200-expert-export.csv`](docs/pilot-200-expert-export.csv). Не трогать `classification-stage2-dev.json`, hierarchy, пороги.

**Контракт поведения**

- Default: `--dry-run` (только отчёт: сколько apply / skip / invalid).
- Apply только если `expert_final_category_id` парсится в finite int **и** `product_id` есть в CSV.
- Для строк `decision_status=needs_human_review`: `decision_status=classified`, `final_source=human`, `final_category_id=<expert>`, `next_action=none`, `reviewed_at=now()`, log `stage=human_review`, `actor_type=human`.
- Для `auto_sample_25pct`: **не** затирать auto `final_category_id`, если expert совпал; если не совпал — писать QA-поля / log `validation_passed=false` + **не** менять `final_source` в v1 (critical считаем в gate-скрипте, не ломаем auto snapshot до отдельного решения).
- Пустые `expert_*` → skip.
- Идемпотентность: повторный прогон той же тройки `(product_id, expert_final_category_id, human)` не плодит дубликаты log с тем же `run_id`+`stage`+одинаковым `selected_category_id` (или пишет один log с `status=success` и выходит).
- Isolation: один `UPDATE`/`INSERT` на строку; без `WHERE false` патчей workflow; без hierarchy.

**Done-when (обязательные критерии)**

1. `python3 scripts/pilot200_sheets_writeback.py --csv docs/pilot-200-expert-export.csv` без `--apply` печатает counts и **0** SQL writes.
2. На **одной** заранее выбранной NHR-строке (подставить test `expert_final_category_id` локально в копии CSV, не коммитить фейковые labels в `docs/pilot-200-expert-export.csv`): `--apply --limit 1` → в БД у этого `product_id`: `final_source='human'`, `decision_status='classified'`, `final_category_id` = expert; есть новая строка `product_classification_log` с `stage='human_review'`.
3. Повтор `--apply --limit 1` на том же id не меняет snapshot повторно осмысленно (нет третьего конфликтующего `final_category_id`).
4. Stage 2 / hierarchy JSON diff пустой. Пороги 0.40/0.60 не менялись.
5. Короткий отчёт в issue или `docs/pilot-200-writeback.md` (10–15 строк): product_id, before/after, log id.

**Не входит в задачу:** Google Sheets API, Telegram, Fin→BA wiring, quality_gate.py (день 2), фикс `n1_t_gate_v1.js`.

---

## 9. Явно не делать на этой неделе

- Remediation N1-T / Mode C Load / G3 arming (`N1_T_RUNTIME_FAIL_GATE_FALSE` оставить как исторический баг).
- B4 Direction LLM, Wave-500 Sem, M5.1 n8n, RX retrieval, Age→routing.
- Новые «design only» документы.
- `batch_size=100`/`500` в одном LLM execution.
- Включать `agent-balance-bot` и Telegram HITL mass-send.
- Менять `classification-stage2-prepare-for-llm`.
