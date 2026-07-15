**Выполненные задачи (Stage 2 классификатора аптечных товаров)**

1. **Введение run-tracking и run_meta**

* Добавлена таблица `classification_runs` как сущность запуска Stage 2. [file:1]
* В начале workflow создаётся запись в `classification_runs`, возвращаемый `run_id` прокидывается в каждый item. [file:1]
* Введён служебный объект `run_meta`, который идёт вместе с товаром через все основные ноды. [file:1]

2. **Единый паттерн работы Code-ноды с item’ами**

* Зафиксирован паттерн `...item.json` во всех Code-нодах, чтобы не терять служебные поля (`run_id`, `run_meta`, версии, routing-подсказки). [file:1]
* Во всех Code-нодах при формировании нового json-объекта сохраняются исходные поля и только дописываются новые. [file:1]
* При возврате нескольких items из Code-ноды используется поле `pairedItem` для сохранения item linking. [file:1]

3. **Нормализация товара и подготовка промпта (Stage 2 primary round)**

* Реализована Code-нода, которая нормализует сырые данные товара: [file:1]
  * `product_id`, `product_raw_id`; [file:1]
  * `combined_text` (объединённое описание); [file:1]
  * эвристика `product_type_guess`; [file:1]
  * rule-shortlist: `shortlist_json`, `rule_top_category_id`, `rule_top_score`. [file:1]
* Формируется человекочитаемый `userPrompt` и объект `deepseek_body` (`system`/`user` messages) для DeepSeek. [file:1]
* В контекст промпта включены `run_id`, rule-поля и shortlist, что позволяет прозрачно аудировать запуск. [file:1]

4. **Вызов основного LLM (DeepSeek) через AI Agent**

* Настроен AI Agent в n8n для вызова DeepSeek Chat Model с отдельными полями `prompt_system` и `prompt_user`. [file:1]
* Ответ модели ожидается в JSON-формате (`category_id`, `confidence`, `explanation`), но пайплайн устойчив к битому JSON. [file:1]

5. **Merge контекста и LLM-ответа**

* Настроен Merge-узел, который объединяет поток товаров и поток LLM-ответов по `pairedItem`. [file:1]
* После Merge у каждого товара есть одновременно исходные данные (rule-shortlist, текст) и сырой ответ модели. [file:1]

6. **Init Stage Constants**

* Добавлена отдельная Code-нода `Init Stage Constants`, которая прикладывает к каждому item канонический словарь служебных значений: [file:1]
  * `stage`; [file:1]
  * `decision_status`; [file:1]
  * `final_source`; [file:1]
  * `next_action`; [file:1]
  * `actor_type`; [file:1]
  * `log_status`; [file:1]
  * пороги (`thresholds`) и model aliases. [file:1]
* Нода используется как единая точка для строковых констант Stage 2, чтобы не дублировать литералы `primary_llm`, `needs_human_review`, `pending_fallback`, `deepseek-chat` и т. п. по разным Code-нодам. [file:1]
* Зафиксирован практический паттерн: критичные Code-ноды читают значения из `root.constants`, но при необходимости имеют локальные fallback-дефолты. [file:1]

7. **Post-process и формирование решения primary LLM round**

* Code-нода `Post-process` обновлена и переведена на использование `constants` из `Init Stage Constants`. [file:1]
* Нода: [file:1]
  * парсит JSON-ответ модели, обрабатывает случаи битого JSON и отсутствующих полей; [file:1]
  * нормализует `llm_category_id`, `llm_confidence`, `llm_explanation`; [file:1]
  * валидирует ответ по правилам: диапазон confidence, валидность `category_id`, наличие объяснения; [file:1]
  * считает служебные флаги: `llm_validation_passed`, `llm_reject_reason`, `llm_needs_review`. [file:1]
* Введена явная маршрутизация через поля: [file:1]
  * `next_action`; [file:1]
  * `routing_hint`. [file:1]
* Зафиксированы варианты `next_action`: [file:1]
  * `none`; [file:1]
  * `fallback_2a`; [file:1]
  * `judge`; [file:1]
  * `human_review`. [file:1]
* Логика primary round подтверждена на реальных данных: [file:1]
  * валидный и достаточно уверенный ответ -> `decision_status='classified'`, `final_source='llm'`, `next_action='none'`; [file:1]
  * `category_id=null`, `invalid_json`, `empty_output`, `category_outside_shortlist` -> `decision_status='pending_fallback'`, `final_source='system'`, `next_action='fallback_2a'`; [file:1]
  * валидный, но low-confidence ответ -> `decision_status='needs_human_review'`, `final_source='system'`, `next_action='human_review'`. [file:1]
* Порог для auto-success ужесточён: `confidence <= 0.60` не проходит как финальная автоматическая классификация и переводится в review-маршрут. [file:1]
* `Post-process` формирует структуры: [file:1]
  * `product_classification_update` (snapshot для `product_classification`); [file:1]
  * `product_classification_log_insert` (event-log записи для `product_classification_log`). [file:1]

8. **Подготовка snapshot-пейлоада (Prepare DB Payload)**

* Обновлена Code-нода `Prepare DB Payload` с вспомогательными функциями `sqlText`, `sqlNumber`, `sqlBoolean`, `sqlJson`. [file:1]
* Нода сериализует `product_classification_update` в SQL-ready формат, включая: [file:1]
  * идентификаторы и run-tracking: `product_id`, `product_raw_id`, `latest_run_id`; [file:1]
  * версии: `workflow_version`, `prompt_version`; [file:1]
  * rule-поля: `rule_top_category_id`, `rule_top_score`, `rule_shortlist_id`, `rule_decision_status`; [file:1]
  * llm-поля: `llm_category_id`, `llm_confidence`, `llm_explanation`, `llm_needs_review`, `llm_validation_passed`, `llm_reject_reason`, `llm_raw_json`; [file:1]
  * judge-поля: `judge_category_id`, `judge_confidence`, `judge_explanation`, `judge_needs_review`, `judge_raw_json`; [file:1]
  * fallback 2A-поля: `fallback_2a_direction`, `fallback_2a_block_family`, `fallback_2a_family_code`, `fallback_2a_nosology_hint`, `fallback_2a_confidence`, `fallback_2a_explanation`, `fallback_2a_raw_json`; [cite:1]
  * fallback 2B-поля: `fallback_2b_category_id`, `fallback_2b_confidence`, `fallback_2b_explanation`, `fallback_2b_raw_json`; [cite:1]
  * routing-поля: `next_action`, `routing_hint`; [file:1]
  * финальное решение: `final_category_id`, `final_confidence`, `final_explanation`, `final_source`, `decision_status`. [file:1]
* Внедрено авто-заполнение версий по дефолту: `stage2_primary_llm_v1`, `prompt_primary_llm_v1` при отсутствии значений. [file:1]
* После подтверждённого расширения схемы `Prepare DB Payload` готов принимать snapshot не только primary LLM, но и будущих стадий `fallback_2a` / `fallback_2b`, не ломая текущий primary flow. [file:1][cite:1]

9. **Upsert в product_classification**

* Обновлена Postgres-нода `Upsert` с запросом `INSERT ... ON CONFLICT (product_id) DO UPDATE`. [file:1]
* Ранее в таблицу `product_classification` были добавлены колонки `workflow_version` и `prompt_version`. [file:1]
* Дополнительно под routing primary round в схему добавлены и подтверждены колонки: [file:1]
  * `llm_validation_passed boolean`; [file:1]
  * `llm_reject_reason text`; [file:1]
  * `next_action text`; [file:1]
  * `routing_hint jsonb`. [file:1]
* Дополнительно под fallback 2A / 2B в схему `product_classification` добавлены и подтверждены колонки: [cite:1]
  * `fallback_2a_direction text`; [cite:1]
  * `fallback_2a_block_family text`; [cite:1]
  * `fallback_2a_family_code text`; [cite:1]
  * `fallback_2a_nosology_hint text`; [cite:1]
  * `fallback_2a_confidence numeric`; [cite:1]
  * `fallback_2a_explanation text`; [cite:1]
  * `fallback_2a_raw_json jsonb`; [cite:1]
  * `fallback_2b_category_id bigint`; [cite:1]
  * `fallback_2b_confidence numeric`; [cite:1]
  * `fallback_2b_explanation text`; [cite:1]
  * `fallback_2b_raw_json jsonb`. [cite:1]
* Upsert теперь обновляет: [file:1]
  * `product_raw_id`, `latest_run_id`, `workflow_version`, `prompt_version`; [file:1]
  * rule-поля; [file:1]
  * llm-поля, включая `llm_validation_passed` и `llm_reject_reason`; [file:1]
  * judge-поля; [file:1]
  * fallback 2A / 2B snapshot-поля; [cite:1]
  * routing-поля `next_action`, `routing_hint`; [file:1]
  * финальные `final_*` и `decision_status`; [file:1]
  * `updated_at`. [file:1]
* Проверено на реальных данных, что новые поля корректно записываются в БД и совпадают с output `Post-process`; на тестовом primary-only прогоне новые `fallback_2a_*` и `fallback_2b_*` поля остаются `NULL`, а основной сценарий не деградирует. [cite:1][file:1]

10. **Подготовка log-пейлоада (Prepare Log Payload)**

* Обновлена Code-нода `Prepare Log Payload`, которая формирует SQL-ready пейлоад для `product_classification_log`. [file:1]
* Нода подготавливает: [file:1]
  * `run_id`, `product_id`, `product_raw_id`; [file:1]
  * `stage='primary_llm'` для текущего primary round и универсальный контракт для будущих стадий; [file:1]
  * `actor_type='llm'`, `actor_name='deepseek-chat'`; [file:1]
  * `status`; [file:1]
  * `decision_status`, `next_action`; [file:1]
  * `input_payload`, `output_payload`, `routing_hint`; [file:1]
  * `selected_category_id`, `confidence`, `explanation`; [file:1]
  * `validation_passed`, `error_message`; [file:1]
  * `workflow_version`, `prompt_version`. [file:1]
* Нода также использует `...item.json` и `pairedItem` для корректного item linking. [file:1]
* `Prepare Log Payload` расширен так, чтобы `output_payload` уже мог содержать данные primary LLM, `fallback_2a`, `fallback_2b`, judge и final fields без необходимости каждый раз менять схему `product_classification_log`. [file:1]

11. **Insert в product_classification_log**

* Обновлена Postgres-нода `Insert` в `product_classification_log`. [file:1]
* Под routing primary round в схему добавлены и подтверждены колонки: [file:1]
  * `product_raw_id bigint`; [file:1]
  * `decision_status text`; [file:1]
  * `next_action text`; [file:1]
  * `routing_hint jsonb`. [file:1]
* Запрос вставляет одну строку на попытку классификации без upsert, с полями: [file:1]
  * `run_id`, `product_id`, `product_raw_id`, `stage`, `actor_type`, `actor_name`, `status`; [file:1]
  * `decision_status`, `next_action`; [file:1]
  * `input_payload`, `output_payload`, `routing_hint`; [file:1]
  * `selected_category_id`, `confidence`, `explanation`; [file:1]
  * `validation_passed`, `error_message`; [file:1]
  * `workflow_version`, `prompt_version`; [file:1]
  * `created_at=now()`. [file:1]
* Insert теперь совместим не только с `primary_llm`, но и с будущими стадиями `fallback_2a`, `fallback_2b`, `judge`, `human_review`, так как универсальный контракт лога уже собран в `Prepare Log Payload`. [file:1]
* Проверено на реальных запусках, что: [file:1]
  * логи для каждого `run_id` содержат корректные `workflow_version` и `prompt_version`; [file:1]
  * в логи пишутся `decision_status`, `next_action`, `routing_hint`; [file:1]
  * snapshot и log отражают один и тот же результат primary round. [file:1]

12. **Синхронизация веток snapshot и log**

* В конце веток `Upsert` (snapshot) и `Insert` (log) добавлен Merge-узел для синхронизации выполнения. [file:1]
* ~~После него добавлен `Merge Run Context`~~ → **удалён в Фазе 1 (п.18)**; run id читается напрямую из `$('Create Run')`. [file:1]
* Перед завершением run добавлена Code-нода `Pick Run Item`, которая оставляет один item с `classification_runs.id`, чтобы `Finish Run` выполнялся один раз на запуск. [file:1]

13. **Finish Run реализован и проверен**

* Добавлена Postgres-нода `Finish Run` после цепочки `Merge Finish -> Merge Run Context -> Pick Run Item`. [file:1]
* Нода агрегирует итог запуска по `product_classification.latest_run_id = classification_runs.id`. [file:1]
* В `classification_runs` обновляются: [file:1]
  * `success_count`; [file:1]
  * `error_count`; [file:1]
  * `finished_at`; [file:1]
  * `status` (`finished`, `finished_with_review`, `finished_with_errors`, `finished_empty`). [file:1]
* Поскольку в текущей схеме `classification_runs` нет отдельных колонок `total_count` и `needs_review_count`, эти значения временно сохраняются в `metadata` как JSONB. [file:1]
* Проверено на реальном запуске: [file:1]
  * `id=6`; [file:1]
  * `status='finished'`; [file:1]
  * `batch_size=5`; [file:1]
  * `success_count=5`; [file:1]
  * `error_count=0`; [file:1]
  * `metadata.total_count=5`; [file:1]
  * `metadata.needs_review_count=0`. [file:1]
* После расширения payload builders и логирования подтверждено, что `classification_runs` не деградировала; при этом новые запуски `7` и `8` оставались в `status='running'` — исправлено в Фазе 1 (п.18). [cite:1][file:1]

18. **Фаза 1 — стабилизация Finish Run (`classification-stage2-dev`)**

* **Дата:** 2026-06-27. Workflow: `classification-stage2-dev` (`BaBjEPi78taRj2G5`). Агенты: investigator → implementer → verifier.
* **Диагноз:** цепочка финализации не доходила до `Finish Run`:
  * `Upsert` / `Insert` без `RETURNING` → 0 items на выходе Postgres-нод;
  * `Merge Finish` и `Merge Run Context` с пустыми `parameters` → implicit `combineByPosition` (0×N) → 0 items;
  * `Pick Run Item` / `Finish Run` не выполнялись → `classification_runs.status` оставался `running` (runs 7/8).
* **Исправления в dev workflow:**
  * удалена нода `Merge Run Context`; топология: `Upsert` + `Insert` → `Merge Finish` (append) → `Pick Run Item` → `Finish Run`;
  * `Merge Finish`: явный режим `append`, `numberInputs: 2` (barrier, не combine);
  * `Pick Run Item`: `runOnceForAllItems`, run id из `$('Create Run').first().json` (не `items.find(id)`);
  * `Finish Run`: SQL с `run_ref` CTE + `LEFT JOIN product_classification` — run финализируется даже при пустой stats;
  * `Upsert`: `RETURNING product_id, decision_status, latest_run_id`;
  * `Insert`: `RETURNING id, product_id, run_id`;
  * `Init Stage Constants`: aliases моделей — `primary_actor_name`, `fallback_actor_name` = `deepseek-chat`, `judge_actor_name` = `openrouter` (placeholder).
* **Решение по схеме `classification_runs`:** `total_count` и `needs_review_count` **остаются в `metadata`** (JSONB); отдельные колонки — отложить до мониторинговых дашбордов.
* **Деплой:** `python3 scripts/push_workflow.py classification-stage2-dev` — успешно (`updatedAt: 2026-06-27`).
* **Статическая верификация:** 8/8 checks PASS (verifier agent).
* **Runtime smoke-test (2026-06-28):** manual execute `classification-stage2-dev` — **успешно**.
  * `Finish Run` output: `id=9`, `status='finished'`, `batch_size=5`, `success_count=1`, `error_count=0`;
  * `finished_at=2026-06-28T10:14:05.214Z`;
  * `metadata`: `{ trigger: manual, total_count: 5, needs_review_count: 0 }`;
  * execution log: `Pick Run Item` и `Finish Run` отработали (подтверждено пользователем).
  * SQL после прогона: run `9` → `finished`; runs `7`, `8` оставались `running`.
  * Backfill runs 7/8: `UPDATE classification_runs SET status='finished', finished_at=now() WHERE id IN (7,8) AND status='running'` → **UPDATE 2**.
* **Интерпретация run 9:** `total_count=5` (все товары партии обработаны), `success_count=1` (один `decision_status='classified'`); остальные 4 — вероятно `pending_fallback` / другие статусы (ожидаемо для smoke-test с разными сценариями routing).
* **Статус Фазы 1:** **закрыта** ✅

19. **Фаза 2 — Fallback 2A (`classification-stage2-dev`)**

* **Дата:** 2026-06-28. Workflow: `classification-stage2-dev` (`BaBjEPi78taRj2G5`). Агенты: designer → implementer → verifier → orchestrator hotfix.
* **Подход:** rule + DeepSeek по `categories_dict` (не свободный LLM).
* **Новые ноды (8):**
  * `2A — categories_dict` — prefetch справочника из `Create Run`;
  * `2A — Route` — Switch по `next_action === 'fallback_2a'`;
  * `2A — Rule Branch Filter` — scoring по паттернам `shortlist.json`, top-8 branch candidates;
  * `2A — Skip LLM?` — bypass агента при `skip_llm`;
  * `2A — LLM Prepare Payload` / `2A — AI Agent` / `2A — Merge` — вызов DeepSeek;
  * `2A — Post-process` — валидация, `fallback_2a_*`, routing → `fallback_2b` или `human_review`.
* **Топология:**
  * `Post-process` → `2A — Route` (убраны прямые связи с Prepare DB/Log);
  * ветка **other** → Prepare DB/Log → Upsert/Insert → Merge Finish (как раньше);
  * ветка **fallback_2a** → Insert primary_llm log → Rule Filter → (LLM | skip) → Post-process 2A → Upsert/Insert → Merge Finish;
  * `DeepSeek Chat Model` shared с primary и 2A агентом.
* **Init Stage Constants:** добавлены `next_action.fallback_2b`, `thresholds.min_confidence_2a_ok: 0.40`.
* **Версии 2A:** `workflow_version=stage2_fallback_2a_v1`, `prompt_version=prompt_fallback_2a_v1`.
* **2A LLM output:** `direction`, `block_family`, `family_code`, `nosology_hint`, `confidence`, `explanation` — **без `category_id`**.
* **Routing 2A Post-process:**
  * valid + confidence > 0.40 → `decision_status=pending_fallback`, `next_action=fallback_2b`;
  * иначе → `needs_human_review`, `next_action=human_review`;
  * `final_category_id` не устанавливается.
* **Hotfix после verifier:** исправлены синтаксические ошибки в `2A — Rule Branch Filter` (`infant_hygiene`, `slice(0,8)`), упрощён `sourceJson = item.json`.
* **Hotfix 2026-06-28 (runtime):** `$('2A — categories_dict')` не работает с параллельной веткой от `Create Run` — n8n требует, чтобы referenced-нода была в цепочке предков item. Исправление:
  * добавлены `2A — Merge Context` (append) и `2A — Load Categories Trigger` (runOnceForAllItems);
  * топология fallback: `Route → Merge Context (products) + Trigger → categories_dict → Merge Context (categories) → Rule Branch Filter`;
  * `Rule Branch Filter` переведён на `runOnceForAllItems` + разбор `$input.all()` (паттерн ShortList).
* **Деплой:** push успешно (`updatedAt: 2026-06-28T10:41:57`).
* **Статическая верификация:** 9/9 structural PASS; JS syntax fix applied.
* **Runtime smoke-test (2026-06-28, run `11`):** **успешно** ✅
  * `classification_runs.id=11`: `status='finished_with_review'`, `finished_at` заполнен;
  * `metadata.total_count=5`, `success_count=4`, `needs_review_count=1`;
  * Finish Run отработал; интерпретация: 4 товара с `decision_status='classified'`, 1 — `needs_human_review` (возможно после 2A или primary);
  * workflow execute без ошибки на `2A — Rule Branch Filter` после hotfix Merge Context.
* **Статус Фазы 2:** **закрыта** ✅ (код + runtime)
* **Хвост:** run `10` остаётся `running` (прерванный прогон до hotfix); при необходимости backfill: `UPDATE classification_runs SET status='finished', finished_at=now() WHERE id=10 AND status='running'`.
* **Известные нюансы (не блокеры):**
  * на `fallback_2a` items — 2 log-записи (primary_llm + fallback_2a), это ожидаемо;
  * `Insert` count может быть > `Upsert` count в смешанной партии — Merge Finish (append) это допускает.

20. **Фаза 3 — Fallback 2B (`classification-stage2-dev`)**

* **Дата:** 2026-06-28. Workflow: `classification-stage2-dev` (`BaBjEPi78taRj2G5`).
* **Подход:** branch shortlist (rule scoring внутри ветки 2A) + DeepSeek для выбора `category_id`.
* **Новые ноды (12):**
  * `2B — Route` — Switch по `next_action === 'fallback_2b'`;
  * `2B — Merge Context` + `2B — Load Categories Trigger` + `2B — categories_dict` — prefetch справочника (изолированно от 2A);
  * `2B — Branch Shortlist Builder` — scoring по keywords внутри ветки 2A;
  * `2B — Prepare Shortlist Payload` + `2B — Insert Branch Shortlist` — запись в `classification_shortlist` (`stage='fallback_2b'`, `shortlist_type='branch_shortlist'`, `parent_stage='fallback_2a'`);
  * `2B — Skip LLM?` / `2B — LLM Prepare Payload` / `2B — AI Agent` / `2B — Merge` — второй раунд DeepSeek;
  * `2B — Post-process` — валидация, `fallback_2b_*`, routing → `classified` / `judge` / `human_review`.
* **Топология:**
  * `2A — Post-process` → `2B — Route` (убраны прямые связи с Prepare DB/Log);
  * ветка **fallback_2b** → log 2a → branch shortlist → LLM → Post-process 2B → Upsert/Insert → Merge Finish;
  * ветка **other** (human_review после 2A) → Prepare DB/Log → Upsert/Insert → Merge Finish.
* **Init Stage Constants:** добавлен `thresholds.min_confidence_2b_ok: 0.60`.
* **Версии 2B:** `workflow_version=stage2_fallback_2b_v1`, `prompt_version=prompt_fallback_2b_v1`.
* **2B LLM output:** `category_id`, `confidence`, `explanation` — строго внутри branch shortlist.
* **Routing 2B Post-process:**
  * valid + confidence > 0.60 + нет конфликта с primary → `classified`, `final_source=fallback_2b`, `next_action=none`;
  * null_category / outside shortlist / primary conflict / low confidence → `judge` или `human_review`;
  * empty branch shortlist → `human_review`.
* **Деплой:** `python3 scripts/push_workflow.py classification-stage2-dev` — успешно (`updatedAt: 2026-06-28`).
* **Runtime smoke-test (2026-06-28, execution #666):** webhook run `success`, ~54 сек, workflow без ошибок после деплоя 2B.
* **Статус Фазы 3:** **закрыта** ✅ (код + runtime deploy)

21. **Governance — контракт, имена, layout (`classification-stage2-dev`)**

* **Дата:** 2026-07-01.
* **Контракт:** `Categories/stage2_workflow_contract.md` — зоны, субпроцессы, item/DB контракты, пороги, чеклист.
* **Cursor rule:** `.cursor/rules/stage2-workflow.mdc` — для правок workflow JSON.
* **Переименование (30 нод):** префиксы `In —`, `Run —`, `Load —`, `P1 —`, `2A —`, `2B —`, `DB —`, `Fin —`, `Shared —`.
* **Layout:** слева направо по потоку; скрипт `scripts/reorganize_stage2_layout.py`.
* **Sticky notes (10):** обзор + блоки In/Run/Load/P1/2A/2B/DB/Fin/Shared на канвасе n8n.
* **Деплой:** push успешно (`updatedAt: 2026-07-01`).

22. **Фаза 4 — Judge OpenRouter (`classification-stage2-dev`)**

* **Дата:** 2026-07-01. Workflow: `classification-stage2-dev` (`BaBjEPi78taRj2G5`).
* **Подход:** OpenRouter (`openai/gpt-4.1-mini`) арбитражит спорные кейсы после 2B.
* **Новые ноды (6 + sticky):**
  * `Judge — Route` — Switch по `next_action === 'judge'`;
  * `Judge — LLM Prepare` / `Judge — AI Agent` / `Judge — Merge LLM` — вызов OpenRouter;
  * `Judge — Post-process` — `judge_*`, `final_source=judge`, routing;
  * `Shared — OpenRouter` — `lmChatOpenRouter`, credential `OpenRouter account`.
* **Топология:**
  * `2B — Post-process` → `Judge — Route` (вместо прямого DB);
  * ветка **judge** → log fallback_2b → LLM → Post-process Judge → Upsert/Insert;
  * ветка **other** → Prepare DB/Log → Merge Finish (как раньше).
* **Init Stage Constants:** `min_confidence_judge_ok: 0.60`, `judge_actor_name: openai/gpt-4.1-mini`.
* **Версии Judge:** `workflow_version=stage2_judge_v1`, `prompt_version=prompt_judge_v1`.
* **Judge LLM output:** `winner_source`, `category_id`, `confidence`, `explanation`, `needs_human_review`.
* **Routing Judge Post-process:**
  * valid + confidence > 0.60 + category в кандидатах → `classified`, `final_source=judge`, `next_action=none`;
  * иначе → `needs_human_review`, `next_action=human_review`.
* **Скрипты:** `scripts/apply_phase4_judge.py`, `scripts/phase4_nodes/`.
* **Статус Фазы 4:** **закрыта** ✅ (код + runtime deploy)
* **Runtime smoke-test (2026-07-01, execution #1327):** webhook `success`, ~97 сек, workflow без ошибок после деплоя Judge. Judge-ветка не сработала на текущей партии (нет `next_action=judge` — ожидаемо, см. хвост 2B→judge тест).

22a. **Миграция Judge: OpenRouter → Polza.ai / Qwen (`classification-stage2-dev`)**

* **Дата:** 2026-07-15. Причина: недоступность OpenRouter.
* **Модель:** `qwen/qwen3.5-flash-02-23@reasoning_effort=none` (Polza OpenAI-compatible API).
* **Нода:** `Shared — OpenRouter` (`lmChatOpenRouter`) → `Shared — Polza` (`lmChatOpenAi`, credential `Polza account`, Base URL `https://polza.ai/api/v1`).
* **Init Constants:** `judge_actor_name: qwen/qwen3.5-flash-02-23`.
* **Предпроверка:** `polza-qwen-test` + `scripts/polza_test.py --json-test` ✅.
* **Скрипт:** `scripts/migrate_judge_to_polza.py`.

14. **Решение по языку Code-нод**

* Проверена возможность использовать Python в Code-нодах n8n. [file:1]
* В текущем окружении Python недоступен: `Python runner unavailable: Python 3 is missing from this system`. [file:1]
* Принято решение продолжать реализацию проекта на JavaScript Code nodes. [file:1]
* Отдельно зафиксирована будущая инфраструктурная задача: при необходимости подготовить production-ready Python task runner в external mode, но не блокировать им текущую реализацию Stage 2. [file:1]

15. **Подтверждённая схема справочников и shortlist-слоя для fallback**

* По SQL-проверке подтверждено, что в public schema фактически существуют таблицы: `categories_dict`, `categories_raw`, `classification_review_queue`, `classification_runs`, `classification_shortlist`, `product_classification`, `product_classification_log`, `products_prepared`, `products_raw`. [cite:1]
* Таблиц `categories`, `product_categories`, `category_tree`, `rules_shortlist`, `product_rules` в текущей public schema нет. [cite:1]
* Это означает, что fallback 2A / 2B на текущем этапе должны проектироваться на базе уже существующих `categories_dict` и `classification_shortlist`, без зависимости от отдельной tree-table. [cite:1]
* Для `fallback_2a` верхнеуровневое направление/ветка должны определяться прежде всего по `categories_dict.direction`, `hierarchy_level`, `category_name`, `need_nosology`, а также по дополнительным осям `product_type`, `administration_route`, `age_segment`, `mnn_cluster`, `differentiation_degree`, `is_active`. [cite:1]
* Для `fallback_2b` новый shortlist должен строиться заново внутри ветки, а не наследоваться жёстко из первичного global shortlist; для этого используются `categories_dict`, результат 2A и keyword logic из `include_keywords` / `exclude_keywords`. [cite:1][file:1]

16. **Расширение classification_shortlist под branch-shortlist**

* В таблицу `classification_shortlist` добавлены и подтверждены поля: [cite:1]
  * `stage text`; [cite:1]
  * `shortlist_type text`; [cite:1]
  * `parent_stage text`; [cite:1]
  * `shortlist_metadata jsonb`. [cite:1]
* Это позволяет использовать `classification_shortlist` не только для primary rules shortlist, но и как общее хранилище shortlist-ов разных стадий, в том числе branch-shortlist для `fallback_2b`. [cite:1]
* Целевой паттерн хранения: [file:1]
  * primary shortlist -> `stage='primary_rules'`, `shortlist_type='rule_shortlist'`; [cite:1]
  * fallback shortlist -> `stage='fallback_2b'`, `shortlist_type='branch_shortlist'`, `parent_stage='fallback_2a'`; [cite:1]
  * `shortlist_metadata` хранит scope, strategy, branch context и matched keyword/meta информацию. [cite:1]

17. **Smoke-test после обновления схемы и payload-ов**

* Проведён тестовый прогон после расширения схемы `product_classification`, `classification_shortlist`, а также после обновления `Prepare DB Payload`, `Upsert`, `Prepare Log Payload` и `Insert product_classification_log`. [cite:1]
* По `product_classification` на `run_id=8` подтверждены три рабочих сценария: [cite:1]
  * успешная автоматическая классификация -> `final_source='llm'`, `decision_status='classified'`, `next_action='none'`; [cite:1]
  * переход в fallback -> `final_source='system'`, `decision_status='pending_fallback'`, `next_action='fallback_2a'`; [cite:1]
  * переход в manual review -> `final_source='system'`, `decision_status='needs_human_review'`, `next_action='human_review'`. [cite:1]
* По `product_classification_log` на `run_id=8` подтверждено, что: [cite:1]
  * каждая запись создаётся со `stage='primary_llm'`; [cite:1]
  * `actor_type='llm'`, `actor_name='deepseek-chat'`; [cite:1]
  * `decision_status` и `next_action` в логе согласованы со snapshot. [cite:1]
* Итог smoke-test: текущий primary flow не сломан, а схема и payload contracts уже готовы к подключению реальных стадий `fallback_2a` / `fallback_2b`. [cite:1][file:1]

**План дальнейших шагов**

1. **Довести Finish Run до целевого состояния схемы** — **выполнено (Фаза 1, п.18)** ✅

* ~~Решить, нужны ли отдельные колонки `total_count` и `needs_review_count`~~ → **оставить в `metadata`**. [file:1]
* При необходимости добавить миграцию схемы `classification_runs` под расширенную run-статистику — **отложено**. [file:1]
* При необходимости дополнительно посчитать статистику по `pending_fallback` и `llm_reject_reason` — **отложено**. [file:1]
* ~~Проверить runs 7/8 и цепочку finish~~ → **исправлено**; runtime подтверждён на run `9` (2026-06-28); runs 7/8 backfill выполнен. [cite:1][file:1]

2. **Формализация статусов и стадий**

* Набор значений `stage` в `product_classification_log` зафиксирован как целевой: [file:1]
  * `rule_shortlist`, `primary_llm`, `fallback_2a`, `fallback_2b`, `judge`, `human_review`. [file:1]
* Значения `decision_status` в `product_classification` зафиксированы как целевые: [file:1]
  * `classified`, `needs_human_review`, `pending_fallback`, `error`. [file:1]
* Поле `final_source` зафиксировано как целевое: [file:1]
  * `rules`, `llm`, `fallback_2b`, `judge`, `human`, `system`. [file:1]
* Следующий шаг — распространить эти же контракты на fallback, judge и human-review слои. [file:1]

3. **Подготовка к fallback 2A / 2B** — **2A выполнено (п.19)** ✅ | **2B выполнено (п.20)** ✅ | **Judge выполнено (п.22)** ✅ | **Telegram — следующий шаг**

* ~~Спроектировать и реализовать fallback 2A~~ → run `11` подтверждён.
* ~~Fallback 2B (branch shortlist + DeepSeek)~~ → п.20.
* ~~Judge (OpenRouter → Polza / Qwen)~~ → п.22 / п.22a.
* **Осталось:** Telegram human review + policy borderline primary.

**Решение (2026-06-27):**

* Текущая v1: confidence ≤ 0.60 → `needs_human_review`, `next_action='human_review'`.
* Целевая policy: «сломанные» ответы → `fallback_2a`; borderline 0.40–0.60 → сначала fallback 2A/2B; очень низкая уверенность (<0.40) — опционально сразу human; human review — если после fallback уверенность низкая или решения конфликтуют.
* Пороги 0.40 / 0.60 — к уточнению с заказчиком при внедрении fallback.

4. **Judge-слой**

* Модель judge: **Polza.ai / Qwen** (отдельная модель через OpenAI-compatible credential), не DeepSeek. DeepSeek остаётся для primary, 2A, 2B.

* Определить условия вызова judge-модели: [file:1]
  * конфликт решений primary LLM vs fallback 2B; [file:1]
  * низкая уверенность обоих раундов; [file:1]
  * `category_id=null` или нестабильный shortlist. [file:1]
* Реализовать отдельный workflow/ноду judge: [file:1]
  * вход: полный контекст товара + результаты первичных раундов; [file:1]
  * выход: `winner_source`, `final_category_id`, `confidence`, `explanation`, `needs_human_review`; [file:1]
  * логирование как `stage='judge'`. [file:1]
* Внедрить обновление snapshot по результату judge: [file:1]
  * `final_source='judge'`, `decision_status='classified'` или `needs_human_review`; [file:1]
  * запись judge output в уже существующие `judge_*` поля snapshot. [file:1]

5. **Human-in-the-loop / Telegram**

* Спроектировать SQL-представление или отдельную таблицу очереди human review: [file:1]
  * выборка товаров с `decision_status='needs_human_review'` и актуальным `latest_run_id`; [file:1]
  * хранение статуса очереди (`pending`, `sent_to_telegram`, `in_review`, `resolved`). [file:1]
* Спроектировать payload для Telegram-бота: [file:1]
  * нормализованный текст товара; [file:1]
  * rule-shortlist (топ-3–5 кандидатов); [file:1]
  * предложения LLM / fallback / judge с confidence и объяснениями; [file:1]
  * метаданные запуска (`run_id`, версии, источник решения). [file:1]
* Настроить Telegram-бот через ноды Telegram в n8n: [file:1]
  * выдача карточек на ревью с inline-кнопками (`approve / change / mark unresolved`); [file:1]
  * обработка callback query и запись результата в БД. [file:1]
* Логировать ручные решения как `stage='human_review'` с `actor_type='human'` и `actor_name` из Telegram. [file:1]
* Обновлять snapshot: `final_source='human'`, `decision_status='classified'`. [file:1]

6. **Усиление правил пространства (documentation / governance)**

* Зафиксировать в инструкции пространства обязательные паттерны: [file:1]
  * использование `...item.json` во всех Code-нодах для сохранения служебных полей; [file:1]
  * единый `run_id` для всех стадий одного запуска и обязательное заполнение `run_id / latest_run_id` во всех новых слоях; [file:1]
  * заполнение `stage`, `workflow_version`, `prompt_version` во всех лог-записях; [file:1]
  * правило, что невалидный/непарсящийся output LLM всегда логируется с `status='rejected'` и понятной `error_message`; [file:1]
  * использование `Init Stage Constants` как канонической точки для основных строковых констант Stage 2. [file:1]
* Зафиксировать `stage2_workflow_plan.md` как канонический файл проекта в Space files. [file:1]
* Описать контракты таблиц `classification_runs`, `product_classification`, `product_classification_log` и будущей очереди human review. [file:1]

7. **Технический долг и улучшения**

* Постепенно перейти от ручной сборки SQL-строк к параметризованным запросам Postgres-ноды. [file:1]
* Добавить минимальные индексы по `run_id`, `product_id`, `stage`, `decision_status` для аналитики и мониторинга. [file:1]
* Подготовить небольшой набор диагностических запросов/дашбордов: [file:1]
  * доля `needs_human_review` и `pending_fallback` по запуску; [file:1]
  * распределение confidence; [file:1]
  * топ-ошибок `llm_reject_reason`; [file:1]
  * соотношение `classified / fallback / review` по `run_id`. [file:1]
