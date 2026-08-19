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

23. **Smoke-test 2B + Judge + фиксы пути (2026-07-17)**

* **Цель:** дотянуть и подтвердить runtime-цепочку `P1 → 2A → 2B → Judge` на реальных товарах.
* **Найденные блокеры и фиксы:**
  * **Stale LLM `output`:** после P1 поле `output` оставалось в item и при Merge 2A/2B/Judge перезаписывало ответ текущего Agent → `missing_branch_fields`. Фикс: `withoutStaleLlmOutput()` в `2A/2B/Judge — LLM Prepare`.
  * **UNIQUE shortlist:** в БД был UNIQUE только по `product_id`, а `2B — Insert Branch Shortlist` делал `ON CONFLICT (product_id, stage)` → ошибка. Миграция: `stage=primary_rules` для старых строк; UNIQUE `(product_id, stage)`. Stage 1 `ShortList` обновлён под тот же conflict target.
  * **Пустой branch shortlist:** keyword-score часто 0 при непустой ветке → `empty_branch_shortlist` и обрыв до Judge. Soft-fill в `2B — Branch Shortlist Builder`: top-5 из ветки с `reasons=['branch_membership_only']`.
* **Harness:** `scripts/smoke_2b_judge.py` — временный smoke-режим (select `pending`+`needs_human_review`, пониженные пороги 2A/2B), несколько batch, авто-restore production settings. `run_workflow.py` ждёт и `error`/`crashed`, не только `finished`.
* **Runtime подтверждение:**
  | Exec | 2B | Judge | Комментарий |
  |------|----|-------|-------------|
  | `5529` | ✅ | ✅ | product 62: 2B `cat=1024` conf 0.6 → Judge Polza `winner=fallback_2b` conf 0.65 → `human_review` |
  | `5530` | ✅ | ✅ | тот же путь |
  | `5531` | — | — | все остановились на 2A `human_review` (низкий conf) |
* **Итог:** полный автопуть до Judge подтверждён; production-пороги после smoke восстановлены.
* **Следующий крупный блок:** Telegram human review + policy borderline primary (п.3 / п.5).

24. **Borderline policy P1 + Telegram human review (2026-07-17)**

* **P1 routing:** `min_confidence_borderline_low=0.40`; valid conf в `(0.40, 0.60]` → `pending_fallback` / `fallback_2a` (раньше сразу `human_review`); valid conf ≤ 0.40 → `human_review`; broken/null/outside shortlist → `fallback_2a`.
* **Контракт:** `Categories/human_review_contract.md`; очередь `classification_review_queue` (статусы + payload карточки).
* **Workflows:** `classification-human-review-enqueue`, `classification-human-review-send`, `classification-human-review-callback`.
* **Tech debt:** один `Fin — Close Run` на run (счётчик batch), индекс `product_classification_log(run_id, stage)`, диагностические SQL.

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

3. **Подготовка к fallback 2A / 2B** — **2A выполнено (п.19)** ✅ | **2B выполнено (п.20)** ✅ | **Judge выполнено (п.22)** ✅ | **runtime 2B→Judge подтверждён (п.23)** ✅ | **Telegram — следующий шаг**

* ~~Спроектировать и реализовать fallback 2A~~ → run `11` подтверждён.
* ~~Fallback 2B (branch shortlist + DeepSeek)~~ → п.20.
* ~~Judge (OpenRouter → Polza / Qwen)~~ → п.22 / п.22a.
* ~~Smoke-test полного пути до Judge~~ → п.23 (exec `5529`/`5530`).
* **Осталось:** ~~Telegram human review + policy borderline primary~~ → п.24.

**Решение (2026-07-17, внедрено):**

* «Сломанные» ответы → `fallback_2a`; borderline `(0.40, 0.60]` → `fallback_2a`; ≤ 0.40 → `human_review`; human review после fallback/judge — через очередь + Telegram.

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

5. **Human-in-the-loop / Telegram** — **выполнено (п.24)**

* Очередь `classification_review_queue` + `pipeline_settings.telegram_review_chat_id`.
* Контракт: `Categories/human_review_contract.md`.
* Workflows: enqueue / send / callback (approve · change · unresolved · other→текст).
* Resolve пишет `final_source='human'`, log `stage='human_review'`, `actor_type='human'`.

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
* ~~Индексы~~: `product_classification(decision_status, final_source)`, `product_classification_log(run_id, stage)`, partial unique open queue. [file:1]
* Диагностические SQL: `sql/diagnostics_run_stats.sql`. [file:1]
* `Fin — Pick Run`: один Close Run на batch (`$getWorkflowStaticData` + `batch_size`). [file:1]

---

## Hierarchy redesign progress (updated 2026-08-19)

Отдельный трек от current Stage 2. Канон: `redesign/20_MIGRATION_PLAN.md`, статус: `redesign/00_PROJECT_STATUS.md`, короткий roadmap: `redesign/29_SHORT_ROADMAP.md`.  
**Prod Stage 2** (`classification-stage2-dev`, `BaBjEPi78taRj2G5`) — **не менялся**.

### Done

* **§13 clearance** — schema dump (`21a`), mapping need/mnn (`21b`), dirty samples (`21`), isolation design (`22`).
* **B1** — additive SQL applied in **dev**: 18 hierarchy columns on `product_classification` + 4 `hierarchy_*` keys in `pipeline_settings`; `hierarchy_experiment_enabled=false` (`24_B1_APPLY_REPORT.md`).
* **B2** — skeleton `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`): Load stub `WHERE false`; Manual run **297** + webhook run **298** / n8n exec **7768** → `finished_empty`; source `classification-stage2-dev` untouched (`26_B2_EXECUTION_REPORT.md`).
* Hierarchy workflow status: **active but safe** (0 rows / no LLM path on empty Load) — Load stub intact; kill switch / allowlist defaults not relaxed.
* **B3 Norm** (Code-only) — **закрыта** ✅ (см. п.25).
* **B3 Sem** (`semantic_primary`, log-only) — **закрыта в git** ✅ (см. п.26); Dir не подключён; snapshot не пишется.
* **Sem smoke S0/S1/S2** — **закрыта** ✅ (см. п.27); reversible allowlist; rollback to safe default verified.
* **Wave-100 Sem validation (v1)** — **done** (exec **19932**, N=100, pre-Sem0): LLM-on / snapshot-off; gate awaiting human labels.
* **Sem0 + Sem1 attr_profile policy v2** — **finalized** (см. п.29–30): `prompt_sem0_v2` / `prompt_semantic_v3`; Wave-100 rerun chunked 10×10; progress tooling; rollback verified.
* **Offline MNN identity gate Wave‑500 v3 + enrichment run 461 + human-review quality baseline** — **done** ✅ (см. **п.38**). MNN/RX/Age **не** влиты в live Sem / `attr_*`.
* **Offline BAS/Other override policy v1 + human validation (M2 / M2.1)** — **done** ✅ (см. **п.39**). Audit-only; implementation contract draft **not applied**.
* **M3.0 RX/OTC source audit + M3.1 standalone retriever design** — **done** ✅ (см. **п.40**).
* **M3.2a skeleton created, inactive** — **done** ✅ (см. **п.41**). `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`).
* **M3.2a n8n runtime smoke** — **done** ✅ (см. **п.42**). CLI execs **42679/42680/42681**; workflow left inactive.
* **M3.2b one-item live retrieval** — **done** ✅ (см. **п.43**). SKU `3065`; runner-side SearXNG+fetch; n8n left inactive.
* **M3 RX/OTC research closeout** — **done** ✅ (см. **п.44**). Decision: `KEEP_RX_OTC_P2_SUPPORT_ONLY` / `DO_NOT_RUN_PHASE_A_YET`.
* **M4 Age pilot contract** — **validated** ✅ (см. **п.45**). Audit-only; not a routing gate; not merged to `attr_age_segment`.

### Not done

* Sem human rubric labeling для Wave-100 / Wave-500 (`critical_error_rate`).
* Apply M2 implementation contract (queue filter) — **blocked** until explicit approval.
* **M3.2c** 11+30 retrieval batch — **blocked / not scheduled** (no stable P1 route; re-entry in **п.44**).
* Age merge into live Sem / `attr_age_segment` / routing — **blocked** until explicit approval (п.45).
* **M5** Norm v4 experiment (mfr/pack dedupe) — **next offline track**.
* Optional: SplitInBatches перед Sem0 (Wave-100/500 = chunked runner из‑за Merge/LLM parallel hang).
* Dir / Need / Cat / optional Mnn cascade + Judge rewiring for hierarchy.
* Prod Stage 2 Load allowlist-exclude patch.
* Telegram / HITL beyond Sheets for hierarchy — **not started**.
* Dedicated **error-handling track** for hierarchy — **not planned in detail yet**.

### Next short steps

1. **M5** Norm v4 experiment (mfr/pack dedupe) — offline only; no production Norm rewrite.
2. Parallel Sem track: human rubric labeling Wave-100/500 (`critical_error_rate`).
3. Optional later: apply M2 queue-exclusion contract for 13 IDs (explicit approval only).
4. Dir → Need → Cat → optional Mnn → Judge only after Sem gate + explicit MNN merge approval.
5. M3.2c / RX P1 re-entry — only if **п.44** re-entry criteria are met. Do not activate `rx-otc-product-retrieval-dev`.
6. Age remains audit-only (п.45). Do not write `attr_age_segment`.

---

25. **B3 Norm — Code-only нормализация в hierarchy-dev (2026-07-21)**

* **Дата фиксации в журнале:** 2026-07-22. **Workflow:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`).
* **План:** `redesign/28_B3_NORM_PLAN.md`. **Патчер:** `scripts/_b3_patch_norm.py`. **Источники:** `scripts/hierarchy_nodes/norm_helpers_v1.js`, `norm_normalize_product.js`, `norm_normalize_dict.js`.
* **Ограничения B3 Norm:** только Code-ноды; **нет SQL writes**; **нет LLM**; `categories_dict` / product tables не UPDATE; prod Stage 2 не трогаем.

#### Ноды

| Нода | Тип | Wiring | Роль |
|------|-----|--------|------|
| `Norm — Normalize Product` | Code | **live:** `Load — Attach Run ID` → **эта нода** → `Load — Limit Batch` | Нормализация текста/атрибутов товара |
| `Norm — Normalize Dict` | Code | **на canvas, connections пустые** (не в In-path) | Нормализация осей словаря + dirty-flags |
| `🔗 Norm — B3 (wire Dict later)` | Sticky | — | Памятка: Dict подключить в B4/Dir |

Целевое wiring Dict (ещё не сделано): `Dir — Load Categories` → `Norm — Normalize Dict` → Dir Merge Context.

#### Контракт полей — Product (`Norm — Normalize Product`)

Добавляет / обновляет в item (через `...item.json` + `pairedItem`):

| Поле | Смысл |
|------|--------|
| `normalized_text` | Нормализованный текст товара (HTML strip, quotes, ASCII hyphen, collapse whitespace; cap 12000) |
| `normalize_meta.source_fields` | Откуда взят текст (`combined_text` или fallback name/description) |
| `normalize_meta.truncated` | Обрезка по длине |
| `normalize_meta.empty_flags` | Флаги пустых исходников |
| `norm_mnn_product` | Norm MNN с продукта (`mnn` / `mnn_cluster`), если есть |
| `norm_brand_guess` / `norm_form_guess` / `norm_dosage_guess` / `norm_pack_size_guess` / `norm_product_type_guess` | Norm атрибутов, если были на item |
| `norm_warnings[]` | `{ field, reason, raw }` — warnings, не hard-reject |
| `cascade_trace.path` / `cascade_trace.stages` | Append stage `normalize` (merge-safe) |

#### Контракт полей — Dict (`Norm — Normalize Dict`)

| Поле | Смысл |
|------|--------|
| `norm_direction` | `lower(trim(direction))` |
| `norm_need` | `lower(ascii_hyphen(collapse_whitespace(need_nosology)))` |
| `norm_category` | `lower(ascii_hyphen(collapse_whitespace(category_name)))` |
| `norm_mnn` | `lower(ascii_hyphen(collapse_whitespace(mnn_cluster)))` |
| `is_multi_sep` | MNN slash-list / multi-token |
| `is_eq_category` | `norm_mnn == norm_category` |
| `is_device_sku_like` | эвристика SKU/spec (**флаг, не reject**) |
| `need_flat_like` | `norm_need == norm_category` (near-flat ветки) |
| `mnn_raw` | сырой MNN при `is_multi_sep` |
| `norm_warnings[]` | empty/unusable по осям |

#### Safety (подтверждено по export JSON)

* `Load — Select Batch` остаётся stub: `WHERE false` → 0 rows.
* Live In-path: `Select Batch` → `Attach Run ID` → **`Norm — Normalize Product`** → `Limit Batch`.
* `Load — Limit Batch` → **исходящих связей нет** (`connections.main = [[]]`) → P1/2A/2B/Judge **недостижимы**.
* `Norm — Normalize Dict` **без connections** → не влияет на runtime.
* Kill switch: `hierarchy_experiment_enabled=false`; allowlist пустой.
* Итог: workflow **active but safe** — webhook/smoke без drain pending и без LLM-path.

#### Статус

* **B3 Norm:** **закрыта** ✅ (Code-only в hierarchy-dev).
* **Следующий gate после Norm:** B3 Sem — реализован в п.26 (Limit теперь → Sem; P1 по-прежнему недостижим).

---

26. **B3 Sem — `semantic_primary` log-only в hierarchy-dev (2026-07-22)**

* **Workflow:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`).
* **Источники:** `scripts/hierarchy_nodes/sem_*.js`; патчер `scripts/_b3_patch_sem.js`.
* **Ограничения:** clone-only; **нет** DDL; **нет** snapshot upsert после Sem; **нет** Dict Norm на live path; Load остаётся `WHERE false`; kill switch / allowlist defaults **не** ослаблены; prod Stage 2 не трогаем.

#### Ноды (добавлены)

| Нода | Тип | Роль |
|------|-----|------|
| `Sem — Build Prompt` | Code | System/user; запрет category_id / direction / need |
| `Sem — LLM Prepare` | Code | versions + context; strip stale LLM fields |
| `Sem — AI Agent` | LangChain Agent | prompt_user / prompt_system |
| `Sem — DeepSeek` | Chat Model | zone-local DeepSeek (credential copy) |
| `Sem — Merge LLM` | Merge | combineByPosition |
| `Sem — Post-process` | Code | parse → `semantic_*`; soft-continue |
| `Sem — Route` | Switch | future-safe seam; v1 `direction_select` (+ fallback) → Prepare Log |
| `Sem — Prepare Log` | Code | hierarchy-specific log payload |
| `🔗 Sem — B3 (log-only; Dir later)` | Sticky | notes |

#### Live wiring

```text
… → Norm — Normalize Product → Load — Limit Batch
  → Sem — Build Prompt → Sem — LLM Prepare
      ├─ Sem — AI Agent ← Sem — DeepSeek
      └─ Sem — Merge LLM → Sem — Post-process → Sem — Route
           → Sem — Prepare Log → DB — Insert Log → Fin — Merge Barrier
                → Fin — Pick Run → Fin — Close Run
```

Empty path **unchanged:** `Run — Init Constants` → `Shell — Ensure Empty Fin` → `Fin — Close Run`.

#### Sem JSON schema (model output)

| Field | Required in object? | Nullable | Notes |
|-------|---------------------|----------|-------|
| `mnn` | key expected | yes | string\|null |
| `brand` | key expected | yes | string\|null |
| `rx_otc` | key expected | yes | `rx`\|`otc`\|`unknown`\|null |
| `nosology` | key expected | yes | string\|null |
| `administration_route` | key expected | yes | string\|null |
| `dosage_form` | key expected | yes | string\|null |
| `dosage` | key expected | yes | string\|null |
| `age_segment` | key expected | yes | string\|null |
| `package_hint` | key expected | yes | string\|null |
| `combination_hint` | key expected | yes | string\|null |
| `confidence` | **yes** for valid | no (must be 0..1) | number |
| `explanation` | **yes** for valid | no (non-empty string) | missing → soft-continue + `missing_explanation` |
| `category_id` / `direction` / `need` | **forbidden** | — | non-null → `*_forbidden`, soft-continue |

**Broken / invalid handling (always soft-continue):**

| Case | `semantic_validation_passed` | `semantic_reject_reason` | `next_action` |
|------|------------------------------|--------------------------|---------------|
| empty / non-JSON | false | `empty_output` / `invalid_json` | `direction_select` |
| non-object | false | `invalid_shape` | `direction_select` |
| category_id/direction/need set | false | `category_id_forbidden` / … | `direction_select` |
| bad confidence | false | `invalid_confidence` | `direction_select` |
| missing explanation | false | `missing_explanation` | `direction_select` |
| OK | true | null | `direction_select` |

Never `decision_status=classified` at Sem. Always `pending_fallback`.

#### Item / log fields after Sem

**Item:** `semantic_attrs`, `semantic_confidence`, `semantic_explanation`, `semantic_raw_json`, `semantic_validation_passed`, `semantic_reject_reason`, `workflow_version=stage2_hierarchy_v1`, `prompt_version=prompt_semantic_v1`, `stage=semantic_primary`, `decision_status=pending_fallback`, `next_action=direction_select`, `selected_category_id=null`, `routing_hint`, `cascade_trace` append, `log_status`.

**Log insert (`Sem — Prepare Log` → `DB — Insert Log`):** `stage=semantic_primary`, `selected_category_id=null`, `decision_status=pending_fallback`, `next_action=direction_select`, payloads with semantic_* + cascade_trace; **no** Prepare/Upsert Snapshot.

#### Finish-chain (log-only)

* With Load=0: Sem не исполняется; `Shell — Ensure Empty Fin` закрывает run (`finished_empty`) — как B2.
* Sem → Insert Log → Merge Barrier (input 1) без Upsert — для будущего allowlist path; **не** подключает terminal snapshot.
* При будущем открытии Load: потребуется отдельный gate для Shell empty-closer (сейчас stub держит 0 rows).

#### Safety

* Load `WHERE false` ✅
* Dict Norm без connections ✅
* Sem ↛ Upsert Snapshot / Prepare Snapshot ✅
* Limit ↛ P1 ✅
* prod `classification-stage2-dev` unchanged ✅

#### Статус

* **B3 Sem:** реализован **structurally** в git (9 нод + log-only wiring) ✅
* **Safe defaults сохранены:** Load `WHERE false`; kill switch / allowlist untouched; snapshot path не подключён; Dict Norm unwired; empty Fin intact; prod Stage 2 unchanged.
* **n8n sync:** **выполнен** 2026-07-22 — `PUT` `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`), `updatedAt=2026-07-22T08:42:33.315Z`, `active=true`, Sem-нод на сервере: **9**, Load stub `WHERE false` сохранён.
* **Следующий gate:** Sem smoke S0/S1/S2 — выполнен в п.27; Wave-100 — только по явному запросу; затем Dir (B4).

---

27. **Sem smoke S0/S1/S2 + reversible allowlist (2026-07-22)**

* **Workflow:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`). **Prod Stage 2:** не менялся.
* **Паттерн:** временный allowlist Load + kill switch → smokes → **обязательный rollback** в safe default (`Load WHERE false`, `hierarchy_experiment_enabled=false`, `product_ids=[]`, inject-node отсутствует).
* **Tooling:** `scripts/sem_smoke_patch_workflow.py`, `sem_smoke_allowlist.py`, `sem_smoke_settings_via_n8n.py`, `sem_smoke_export.py`, `run_hierarchy_workflow.py`, `sem_post_process_fixtures.test.mjs`.

#### Results

| Phase | Evidence | Pass |
|-------|----------|------|
| **S0** empty | exec **9880**, run **299**, `finished_empty`; load=0; Sem Agent не вызывался | ✅ |
| **S1** gated Sem | exec **9929**, run **300**; load=15; Sem Post=15; all `pending_fallback` / `direction_select` / `selected_category_id=null`; **upsert snapshot=false** | ✅ |
| **S2 offline** | `node --test scripts/sem_post_process_fixtures.test.mjs` — **8/8** (invalid_json, missing_explanation, nested/partial, category_id/direction/need forbidden, valid, invalid_shape) | ✅ |
| **S2 live** | exec **9935**, run **302**; inject on first item; `validation_passed=false`, `reject_reason=missing_explanation`, soft-continue; snapshot=false | ✅ |
| **Rollback** | backup restore + settings revert; remote Load `WHERE false`; inject absent; enabled=false; allowlist=`[]`; n8n `updatedAt=2026-07-22T12:22:42.532Z` | ✅ |

#### Allowlist S1

* **seed:** `sem_smoke_2026-07-22`
* **n:** 15
* **eligible note:** classic `pending` pool was **empty**; Sem smoke used `needs_human_review` (outside prod Stage 2 pending drain) + seeded `md5(product_id\|\|seed)` + exclude hot prod activity for pending-only.
* **product_ids:** `66, 89, 4611, 5212, 6168, 6613, 10704, 15375, 16215, 16411, 17010, 18205, 21325, 23183, 25794`
* **artifact:** `redesign/artifacts/sem_smoke_S1_allowlist.json`, CSV `redesign/artifacts/sem_smoke_s1_report.csv` (с пустыми `label_*` под Wave-100 rubric)

#### Wave-100 prep (not started)

* Allowlist generator: `python scripts/sem_smoke_allowlist.py --n 100 --seed … --wave-label wave100`
* Template: `redesign/artifacts/sem_wave100_report_template.csv` + rubric note
* **Gate definition:** см. п.28 (planned). B3 Sem smoke green → Wave-100 разрешён **только по явному запросу**.

#### Safety after task

* Load `WHERE false` ✅
* `hierarchy_experiment_enabled=false` ✅
* `hierarchy_product_allowlist=[]` ✅
* inject-node отсутствует ✅
* hierarchy-dev pushed in safe default ✅
* prod `classification-stage2-dev` untouched ✅

---

28. **Wave-100 Sem validation — gate definition + execution (done)** (2026-07-29)

* **Статус:** **done (execution complete)**. Wave-100: LLM-on, snapshot-off, prod untouched; `semantic_validation_passed=true` для 100/100; Sem contract violations (category_id/direction/need) = 0. Gate pass по `critical_error_rate` ожидает human rubric labels.
* **Связь:** после зелёных Sem smoke (п.27). Канон метрик: `redesign/20_MIGRATION_PLAN.md` §3.2 / §9.3; short roadmap Step 2.

#### Execution evidence (Wave-100)

* Allowlist seed: `sem_wave100_2026-07-29`, N=100 (см. `redesign/artifacts/sem_wave100_allowlist.json`).
* n8n execution: **19932** (`load_count=100`, `sem_post_count=100`, `sem_agent_ran=true`, `upsert_snapshot_ran=false`).
* Routing после Sem (hierarchy-dev, log-only): `decision_status=pending_fallback`, `next_action=direction_select`, `selected_category_id=null`.
* Contract enforcement: `semantic_reject_reason` не содержит `category_id_forbidden` / `direction_forbidden` / `need_forbidden`.

#### A. Что такое Wave-100

* Следующий этап hierarchy redesign после Sem smoke.
* **Первый полноценный LLM-on прогон** в `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`) на выборке **N=100**.
* На этапе реально вызывается Sem chain:

```text
Norm — Normalize Product
  → Sem — Build Prompt → Sem — LLM Prepare
      → Sem — AI Agent / DeepSeek → Sem — Merge LLM
      → Sem — Post-process → Sem — Prepare Log
      → DB — Insert Log
```

* Выполняется **только** в hierarchy-dev; **только** через allowlist isolation; **без** Dir / Need / Cat / Mnn / Judge / Sheets / Telegram; **без** правок prod `classification-stage2-dev`.

#### B. LLM-on / snapshot-off / prod untouched

* **LLM-on:** Sem model реально вызывается и возвращает первые production-like `semantic_attrs`.
* **snapshot-off:** после Sem по-прежнему нет upsert в `product_classification`; сохраняются log events / export artifacts.
* **prod untouched:** prod Stage 2 workflow, его Load и snapshot-путь не меняются.

#### C. Что оцениваем

* Качество предобработки: `normalized_text` (Norm) + `semantic_attrs` (Sem).
* **Не** оцениваем final category, direction, need, leaf category.

#### D. Rubric / labels

| Label | Meaning |
|-------|---------|
| `correct` | атрибут согласуется с текстом |
| `incorrect` | атрибут неверен / hallucination |
| `unknown_acceptable` | null допустим — текст не даёт сигнала |
| `missing_should_exist` | null, хотя текст явно содержит сигнал |

#### E. Critical attrs (gate v1)

* Hard gate: `mnn`, `dosage_form`, `administration_route`.
* Secondary / report-only (не основной hard gate v1): `dosage`.

#### F. Основная метрика

```text
critical_error_rate = critical_errors / evidenced_key_attr_cases
```

* `critical_errors` = `incorrect` + `missing_should_exist` по critical attrs.
* `evidenced_key_attr_cases` = случаи, где по тексту соответствующий critical attr должен быть определён.

#### G. Gate rule

* **Pass → можно планировать Wave-500:**
  * `critical_error_rate < 15%`
  * 0 нарушений Sem contract (`category_id`, `direction`, `need` не появляются в Sem output)
  * snapshot after Sem remains disabled
  * rollback to safe default verified
* **Stop / revise prompt-postprocess:**
  * `critical_error_rate >= 15%`
  * заметные hallucinations по critical attrs
  * высокий `missing_should_exist`
  * нарушение Sem contract
  * unstable run / failed rollback

#### H. Review model

* Один reviewer на все 100.
* Seeded spot-check **20–25%** вторым reviewer.
* Disagreement resolution только для spot-check.

#### I. Artifacts (после прогона)

* `redesign/artifacts/sem_wave100_allowlist.json`
* `redesign/artifacts/sem_wave100_report.csv`
* `redesign/artifacts/sem_wave100_report.summary.json`

После прогона: labels (`label_*` в CSV) остаются пустыми — требуется human rubric labeling для расчёта `critical_error_rate`.

---

29. **Sem0 product_kind + Sem1 attr_profile gate (2026-07-30)**

* **Статус:** **done** (wired + smoke + rollback). Clone-only; snapshot-off; prod Stage 2 не менялся.
* **Workflow:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`).
* **Sources:** `scripts/hierarchy_nodes/sem0_build_prompt.js`, `sem0_llm_prepare.js`, `sem0_post_process.js`; обновлены `sem_build_prompt.js`, `sem_llm_prepare.js`, `sem_post_process.js`, `sem_prepare_log.js`; патчер `scripts/_b3_patch_sem0.js`.
* **Versions (initial smoke):** Sem0 `prompt_sem0_v1` / Sem1 `prompt_semantic_v2` (exec **21504**). **Superseded by policy v2** → п.30 (`prompt_sem0_v2` / `prompt_semantic_v3`).

#### Live wiring (после Limit)

```text
… → Load — Limit Batch
  → Sem0 — Build Prompt → Sem0 — LLM Prepare
      ├─ Sem0 — AI Agent ← Sem0 — DeepSeek
      └─ Sem0 — Merge LLM → Sem0 — Post-process
  → Sem — Build Prompt → Sem — LLM Prepare
      ├─ Sem — AI Agent ← Sem — DeepSeek
      └─ Sem — Merge LLM → Sem — Post-process → Sem — Route
           → Sem — Prepare Log → DB — Insert Log → …
```

P1 / Dir / Need / Cat / Mnn / Judge / Upsert Snapshot — **не** подключены (как в п.26–27).

#### Sem0 zone (новые ноды)

| Нода | Тип | Роль |
|------|-----|------|
| `Sem0 — Build Prompt` | Code | System/User: `product_kind`, `product_family`, `attr_profile`; forbid category/direction/need |
| `Sem0 — LLM Prepare` | Code | `prompt_sem0_v1`, stage `product_kind_select` |
| `Sem0 — AI Agent` | LangChain Agent | zone-local |
| `Sem0 — DeepSeek` | Chat Model | credential copy с `Shared — DeepSeek` |
| `Sem0 — Merge LLM` | Merge | combineByPosition |
| `Sem0 — Post-process` | Code | parse/validate; soft-continue всегда в Sem1 |
| `🔗 Sem0 — kind/family before Sem1` | Sticky | notes |

**Sem0 soft-fail:** `product_kind=other`, все `attr_profile` = `applicable`, `sem0_validation_passed=false` — не регрессить ЛС при битом Sem0.

**Item fields после Sem0:** `product_kind`, `product_family`, `attr_profile`, `sem0_confidence`, `sem0_explanation`, `sem0_validation_passed`, `sem0_reject_reason`, `sem0_raw_json`; `cascade_trace.stages` += `product_kind_select` / notes `sem0_v1`.

#### Sem1 (`prompt_semantic_v2`)

* **attrHints** (в user prompt): Norm hints + `product_kind` / `product_family` / `attr_profile` с item после Sem0.
* **System:** если `attr_profile[key]=not_applicable` → вернуть `null`; если `product_kind != drug` → не заполнять pharma-поля (`mnn`, `rx_otc`, `nosology`, `administration_route`, `dosage_form`, `dosage`, `combination_hint`).
* **Ключи JSON модели Sem1** — без новых обязательных полей (как в п.26).

#### Sem1 Post-process enforce (после parse model JSON)

1. Для каждого ATTR_KEY: если `attr_profile[key]==='not_applicable'` → force `null`.
2. Если `product_kind !== 'drug'` → force null: `mnn`, `rx_otc`, `nosology`, `administration_route`, `dosage_form`, `dosage`, `combination_hint`.
3. В `semantic_attrs` вложить `product_kind`, `product_family`, `attr_profile` (плоских `attr_*` колонок на item нет — export flatten из `semantic_attrs`).

#### Smoke (exec **21504**)

* **Seed / wave:** `sem0_smoke_2026-07-30`; N=9; allowlist IDs: `254, 1347, 1623, 5597, 6117, 6168, 9249, 9335, 11225`.
* **Evidence:** `load_count=9`, `sem_post_count=9`, Sem0+Sem1 agents ran, `upsert_snapshot_ran=false`.
* **Outcome (кратко):** non-drug → pharma attrs null; drug `9335` подорожник — `product_kind=drug`, family `Травы`, route/form/dosage заполнены; BAA `1623` / plaster `11225` — pharma null из‑за hard rule § выше.
* **Rollback:** Load `WHERE false`; `hierarchy_experiment_enabled=false`; allowlist `[]`; prod Stage 2 untouched verified.

#### Artifacts

* `redesign/artifacts/sem0_smoke_report.csv`
* `redesign/artifacts/sem0_smoke_report.md`
* `redesign/artifacts/sem0_smoke_report.summary.json`
* `redesign/artifacts/sem0_smoke_analysis.json`
* `redesign/artifacts/sem_smoke_sem0_smoke_allowlist.json`
* `redesign/artifacts/sem_chain_nodes_current.json` (Sem0+Sem1 snapshot)
* Sources / WF: `scripts/hierarchy_nodes/sem0_*.js`, `workflows/classification-stage2-hierarchy-dev.json`

#### Open questions → **closed in п.30**

Initial hard rule `product_kind != drug ⇒ null all pharma` был слишком жёстким (БАД/пластырь теряли form/dosage). Финальная policy и Wave-100 rerun — см. **п.30**.

---

30. **Sem0/Sem1 policy v2 finalized + Wave-100 rerun + progress tooling (2026-07-30)**

* **Статус:** **done**. Clone-only; snapshot-off; prod untouched; safe default restored.
* **Versions:** Sem0 `prompt_sem0_v2` (notes `sem0_v2`); Sem1 `prompt_semantic_v3` (notes `semantic_primary_v3`).
* **Sources:** updated `sem0_*.js`, `sem_build_prompt.js`, `sem_post_process.js`, `sem_llm_prepare.js`, `sem_prepare_log.js`; patcher `_b3_patch_sem0.js`.

#### Final policy (attr_profile + hard-null)

**vitamin_or_baa**

* attr_profile: `mnn/brand/nosology/route/form/dosage/age/package/combination` = applicable; `rx_otc` = not_applicable.
* Sem1 hard-null: **только** `rx_otc`.
* Vitamins: `nosology` ∈ {отдельные нутриенты, комплексные профили}; `mnn` = витамин/нутриент или `Комплекс`.
* BAA: `nosology` ∈ {нутрицевтики, парафармацевтики, эубиотики}; `mnn` может быть null.

**medical_device**

* Sem0 post выставляет `medical_device_profile` = `hygiene_like` | `clinical_like` (+ `product_kind_group_hint`).
* hygiene_like: pharma route/form/dosage = not_applicable; brand/age/package applicable.
* clinical_like: route/form/dosage applicable; mnn/rx/nosology/combination not_applicable.
* Sem1 hard-null: `mnn`, `rx_otc`, `nosology`, `combination_hint` only; route/form/dosage живут по attr_profile.

**cosmetic_hygiene:** hard-null pharma set (mnn/rx/nosology/route/form/dosage/combination).
**drug:** без ослабления.
**other:** приоритет attr_profile (soft).

#### Progress tooling

* `scripts/wave_progress.py` — poll n8n execution; `processed/N`, `%`, elapsed, ETA; artifact JSON; soft message on poll interrupt + final API check.
* DB log fallback — **opt-in** (`--use-db-logs`); на больших волнах temp SQL может конкурировать с live run.
* `scripts/wave100_chunked_run.py` — Wave-N чанками (default 10): progress `chunks_done`, ETA по last_chunk_sec.
* `run_hierarchy_workflow.py --wait` печатает progress lines + пишет artifact.

#### Wave-100 rerun evidence

* Same allowlist as exec 19932 (`sem_wave100_allowlist.json`); seed `sem_wave100_2026-07-30_policy_v2`.
* **Mode:** chunked 10×10 (single N=100 hang: Sem0/Sem1 Merge `combineByPosition` + parallel DeepSeek).
* **Executions:** `21611, 21617, 21622, 21627, 21632, 21637, 21642, 21648, 21653, 21659` — all success, 10 posts each.
* Kind mix: drug 44 / vitamin_or_baa 19 / medical_device 18 / cosmetic_hygiene 13 / other 6.
* Spot-check: Черника nosology+form; шприц/пластырь route+form; ватные палочки pharma null; подорожник drug filled.
* **Rollback:** Load `WHERE false`; enabled=false; allowlist `[]`; Sem0 v2 re-pushed after revert; prod untouched.

#### Artifacts

* `redesign/artifacts/sem_wave100_report.csv` (+ `product_kind`/`product_family`/`medical_device_profile`)
* `redesign/artifacts/sem_wave100_report.md` / `.summary.json`
* `redesign/artifacts/wave100_progress_summary.json`
* `redesign/artifacts/wave100_v2_chunked_run.log`
* `redesign/artifacts/sem_wave100_report_template.rubric.txt` (policy evidencing notes)
* `redesign/artifacts/sem_wave100_report_exec19932_pre_sem0.csv` (archive)
* `redesign/artifacts/sem_chain_nodes_current.json`

#### Rubric / gate

Critical attrs for gate остаются `mnn` / `dosage_form` / `administration_route`, но evidencing зависит от kind (см. rubric note). `rx_otc` null для vitamin_or_baa = корректно.


---

31. **Norm — Normalize Sem attrs (route / form / age) (2026-08-04)**

* **Статус:** **done** (wired + offline fixtures + smoke + rollback). Clone-only; snapshot-off; prod Stage 2 не менялся.
* **Workflow:** `classification-stage2-hierarchy-dev` (`o8sugljHYuUs7IEC`).
* **Нода:** `Norm — Normalize Sem attrs` (Code) — **после** `Sem — Post-process`, **до** `Sem — Route` / Prepare Log.
* **Sources:** `scripts/hierarchy_nodes/sem_normalize_attrs.js`, словари `sem_attr_dictionaries.md`; патчер `scripts/_b3_patch_sem_norm.js` (также встроен в `_b3_patch_sem.js`).
* **Contract:** Sem0/Sem1 prompts и soft-continue не менялись; нормализация — упорядочивающий слой поверх `semantic_attrs` + плоские `attr_*`.
* **Паттерн:** `...item.json` + `pairedItem`.

#### Live wiring (фрагмент)

```text
… → Sem — Merge LLM → Sem — Post-process
  → Norm — Normalize Sem attrs
  → Sem — Route → Sem — Prepare Log → DB — Insert Log → …
```

#### Словари (canonical)

* **route:** `перорально` | `наружно` | `ингаляционно` | `внутримышечно` | `внутривенно` | `подкожно` | `ректально` | `сублингвально` | `офтальмологический` | `назальный` | `отологический` | `инъекционное` | `не применимо`
* **form:** `таблетки` | `таблетки жевательные` | `капсулы` | `порошок` | `гранулы` | `сироп` | `суспензия` | `раствор` | `лиофилизат` | `мазь` | `крем` | `гель` | `спрей` | `аэрозоль` | `фильтр-пакеты` | `батончик` | `смесь` | `пластырь` | `капли` | `не применимо`
* **age:** `взрослые` | `дети` | `универсальный` | `не применимо`

Policy v2 baseline: hygiene_like → route+form `не применимо`; BAA без age-сигнала → `универсальный`; drug без сигнала → `null`; clinical_like шприц → route `инъекционное`. **Policy v3 (п.32):** `cosmetic_hygiene` больше не force-NA для route/form (нормализатор не обнуляет при явном сигнале).

#### Smoke (exec **29035**)

* Seed `sem_norm_attrs_2026-08-04`; N=15; allowlist: `36, 91, 254, 1347, 1623, 2131, 4782, 6117, 6168, 6633, 9335, 10283, 11225, 16540, 25286`.
* Evidence: `load_count=15`, `sem_post_count=15`, `sem_norm_count=15`, `upsert_snapshot_ran=false`, dict violations = 0.
* Примеры до→после: `внутрь`→`перорально`; `интраназально`→`назальный`; `раствор для в/м`→`раствор`; hygiene/cosmetic → `не применимо`; BAA age null → `универсальный`.
* Offline: `node --test scripts/sem_normalize_attrs_fixtures.test.mjs` — **10/10**.
* **Rollback:** Load `WHERE false`; enabled=false; allowlist `[]`; Norm остаётся на canvas; prod untouched.

#### Artifacts

* `redesign/artifacts/sem_norm_attrs_report.csv` (+ `*_raw` columns)
* `redesign/artifacts/sem_norm_attrs_report.summary.json`
* `redesign/artifacts/sem_smoke_sem_norm_attrs_allowlist.json`
* `redesign/artifacts/sem_norm_attrs_run.log`
* Dictionaries: `scripts/hierarchy_nodes/sem_attr_dictionaries.md`

---

32. **Sem0/Sem1 policy+prompt patch v3/v4 (после Wave-100 markt) (2026-08-04)**

* **Статус:** **done** (patch + focus smoke + rollback). Clone-only; snapshot-off; prod untouched.
* **Workflow:** `classification-stage2-hierarchy-dev` only. Prod `classification-stage2-dev` не менялся (`updatedAt` 2026-07-19).
* **Versions:** Sem0 `prompt_sem0_v3` (notes `sem0_v3`); Sem1 `prompt_semantic_v4` (notes `semantic_primary_v4`).
* **Вход:** `sem_wave100_report_markt.csv` + `redesign/artifacts/sem_wave100_markt_analysis.md`.
* **Sources:** `sem0_build_prompt.js`, `sem0_llm_prepare.js`, `sem0_post_process.js`, `sem_build_prompt.js`, `sem_llm_prepare.js`, `sem_post_process.js`, `sem_prepare_log.js`; точечно `sem_normalize_attrs.js` (`forceNaContext`: cosmetic больше не blanket-NA); rubric `sem_wave100_report_template.rubric.txt`.
* **Паттерн:** `...item.json` + `pairedItem`. SQL/DDL не трогали. Словари route/form/age сохранены.

#### Policy / prompt changes

**Sem0 kind borderlines**

* Шприц + явная доза (мг/мл) + бренд ЛС → `drug` (не `medical_device`).
* Педикулицид / «от вшей» → `other` (не cosmetic).
* Травы / ф/п / листья без явного МНН → `vitamin_or_baa`.
* Капсулы/таблетки «БАД-like» с мг при `other` → `vitamin_or_baa` (Визлея и аналоги).

**Sem0 attr_profile**

* `vitamin_or_baa`: mnn/nosology/route/form/dosage/age/package/combination applicable; `rx_otc` not_applicable.
* `cosmetic_hygiene`: route/form **applicable** при топическом сигнале в тексте.
* `medical_device` hygiene_like vs clinical_like — без смены контракта v2.

**Sem1 MNN / nosology / age**

* drug: mnn только если вещество явно в тексте; иначе `null` (не угадывать по бренду). Post-process: grounding → null, если токен МНН не найден в `normalized_text`.
* vitamin_or_baa: nosology ∈ {нутрицевтики, парафармацевтики, эубиотики, отдельные нутриенты, комплексные профили}; сырой «Витамин C» → в `mnn`, nosology → enum.
* age_segment: явные правила взрослые/дети/универсальный/не применимо; при неясности — не выдумывать узкий возраст.

**Gate / rubric**

* `administration_route` + `dosage_form` для `cosmetic_hygiene` и `medical_device`+`hygiene_like` — **non-critical** (не поднимают `critical_error_rate` перед Wave-500).
* age_segment — analytics-only для gate.

#### Smoke evidence

* Seed `sem_policy_v3_2026-08-04`; focus N=12 (chunked 6+6); allowlist `redesign/artifacts/sem_smoke_policy_v3_focus.json`.
* **Executions:** `29078`, `29085` — success; `sem0_post=6`, `sem_post=6`, `sem_norm=6` each; `upsert_snapshot_ran=false`.
* Offline fixtures: `node --test scripts/sem_normalize_attrs_fixtures.test.mjs` — **11/11**.
* Spot-check before→after (Wave-100 v2 → smoke):
  * Метортрит `medical_device`→**drug**; Гипосарт/Артогистан wrong INN→**mnn null**;
  * Брусника `drug`→**vitamin_or_baa** (nosology enum); Визлея `other`→**vitamin_or_baa**;
  * Лайснер `drug`→**other**; аскорбинки nosology `Витамин C`→**отдельные нутриенты** (mnn сохранён);
  * детский крем: route/form **наружно/крем** (больше не hard-null).
* **Rollback:** Load `WHERE false`; enabled=false; allowlist `[]`; Sem0/Sem1 v3/v4 остались на canvas; prod untouched.

#### Artifacts

* `redesign/artifacts/sem_policy_v3_smoke_report.csv`
* `redesign/artifacts/sem_policy_v3_smoke_run.log`
* `redesign/artifacts/sem_smoke_policy_v3_allowlist.json` / `sem_smoke_policy_v3_focus.json`
* Rubric: `redesign/artifacts/sem_wave100_report_template.rubric.txt`

#### Next

* ~~Review → Wave-500~~ → **done**, см. п.33.

---

33. **Wave-500 Sem run (Sem0 v3 + Sem1 v4 + Norm) (2026-08-04 → 2026-08-05)**

* **Статус:** **done** (chunked LLM-on; snapshot-off; prod untouched; safe default restored).
* **Workflow:** `classification-stage2-hierarchy-dev` only.
* **Versions:** Sem0 `prompt_sem0_v3`; Sem1 `prompt_semantic_v4`; Norm Sem attrs on.
* **Seed / allowlist:** `sem_wave500_2026-08-04` → `redesign/artifacts/sem_wave500_allowlist.json` (N=500; isolation: exclude hot prod Stage 2 activity 24h).
* **Orchestration:** chunked **50×10** via `scripts/wave100_chunked_run.py` (pattern A). Mid-chunk live progress + ETA; `--resume` after transient failure; retries (3) on chunk LLM errors.
* **Progress tool:** `scripts/wave_progress.py` — single-exec poll **или** `--from-progress-artifact` для chunked волны; артефакт `wave500_progress_summary.json`.

#### Progress example

```text
Wave progress: processed 250/500 (50.0%) | chunks 25/50 | elapsed=13787s eta~13787s | state=running | current_exec=29377
PROGRESS processed 500/500 (100.0%) …
```

* **Итог:** processed **500/500**; wall ≈ **27619 s** (~7.7 h); `finished_at` 2026-08-05T03:23:49Z.
* **Executions:** 50 success ids from `29107` … `29663` (полный список в progress/summary). Transient fail chunk 35 exec `29479` (`Sem — AI Agent` ECONNRESET) → resume; не в финальном success set.
* **Snapshot:** `upsert_snapshot_ran=false` (log-only).
* **Kind mix:** drug 224 / vitamin_or_baa 101 / cosmetic_hygiene 75 / medical_device 68 / other 32.
* **Attr fill (non-empty):** mnn 97 · nosology 300 · route 481 · form 397 · age 499.

#### Artifacts

* `redesign/artifacts/sem_wave500_report.csv`
* `redesign/artifacts/sem_wave500_summary.json` (+ `.md`)
* `redesign/artifacts/wave500_progress_summary.json`
* `redesign/artifacts/sem_wave500_allowlist.json`
* `redesign/artifacts/sem_wave500_run.log`

#### Rollback

* Load `WHERE false`; `hierarchy_experiment_enabled=false`; allowlist `[]`; inject absent.
* Prod `classification-stage2-dev` untouched.
* **Note:** smoke `revert` restores workflow backup — после волны локально re-patched Sem0/Sem1 v3/v4 (`_b3_patch_sem0.js`); remote push после revert требует подтверждения, если backup был старше v3/v4.

#### Next

* Human labeling / gate scoring Wave-500 (отдельный шаг). Rubric: cosmetic route/form non-critical.
* Rules patch (шприцы / rx_otc / vitamin MNN) — см. п.34.

---

34. **Sem0/Sem1/Norm rules patch (шприцы, rx_otc, vitamin MNN) (2026-08-05)**

* **Статус:** **done** (patch + focused smoke + rollback). Clone-only; snapshot-off; prod untouched.
* **Workflow:** `classification-stage2-hierarchy-dev` only.
* **Versions:** Sem0 `prompt_sem0_v3` (notes `sem0_v3_rules1`); Sem1 `prompt_semantic_v5` (notes `semantic_primary_v5`); Norm attrs + `rx_otc`.
* **Sources:** `sem0_build_prompt.js`, `sem0_post_process.js` (`correctProductKind` empty-syringe→`medical_device`); `sem_build_prompt.js`, `sem_llm_prepare.js`, `sem_post_process.js`, `sem_prepare_log.js`; `sem_normalize_attrs.js` (`normRxOtc`); `sem_attr_dictionaries.md`.
* **Паттерн:** `...item.json` + `pairedItem`. SQL/DDL не менялись. Route/form/age словари сохранены.

#### Rules

1. **Шприцы / иглы:** пустой шприц, инсулиновый шприц (U-40/U-100), игла для пен-ручек → `medical_device` (`clinical_like`), **кроме** именованных filled pens (Туджео, Тресиба, НовоРапид, Велгия, Гонал-Ф, Теваграстим, …) → `drug`.
2. **`attr_rx_otc`:** канон `rx` | `otc` | `не применимо` (non-drug → `не применимо`; «рецептурный»→`rx`, «без рецепта»→`otc`).
3. **vitamin_or_baa MNN:** доминантный нутриент (Куркумин, Коллаген, Омега-3, …) в `mnn`; `Комплекс` только без доминанты / мультивитаминные бренды; `combination_hint` ∈ {монокомпонентный, комбинированный, многокомпонентный …}.

#### Offline + smoke evidence

* Offline: `node --test scripts/sem0_kind_rules_fixtures.test.mjs scripts/sem_normalize_attrs_fixtures.test.mjs` — **17/17**.
* Focus smoke N=30, seed `sem_rules_patch_2026-08-05`, chunked 3×10.
* **Executions:** `30065`, `30073`, `30083` — success; upsert=false.
* Spot-check before→after:
  * empty/insulin syringes + IME needle: `drug`→**`medical_device`**; Toujeo/NovoRapid/Метортрит remain **`drug`**;
  * rx_otc: only `rx` / `не применимо` (no free-text «рецептурный»);
  * Псиллиум/Лецитин: `Комплекс`→nutrient; Компливит stays `Комплекс`; combo labels normalized.
* Kind mix smoke: medical_device 7 / drug 9 / vitamin_or_baa 14.

#### Artifacts

* `redesign/artifacts/sem_policy_rules_patch_smoke_report.csv`
* `redesign/artifacts/sem_rules_patch_smoke_allowlist.json`
* `redesign/artifacts/wave_rules_patch_progress.json`
* `redesign/artifacts/sem_rules_patch_smoke_run.log`

#### Rollback

* Load `WHERE false`; enabled=false; allowlist `[]`; inject absent; Sem0/Sem1 v5 re-pushed after backup restore; prod untouched.

#### Next

* Human labeling / gate scoring Wave-500 (отдельный шаг).
* Offline MNN/RX enrichment (п.35).

---

35. **Offline MNN/RX enrichment — drug + vitamin_or_baa via Polza/Qwen (2026-08-05)**

* **Статус:** **done** (offline layer; cascade untouched). Clone-only hierarchy Sem export; snapshot-off; prod untouched; SQL/DDL не менялись.
* **Цель:** после Sem+Norm дополнить snapshot/log-кандидаты полями `mnn_enriched` / `rx_otc_enriched` (и `combination_hint_enriched` для БАД), **не переписывая** baseline `attr_mnn` / `attr_rx_otc`.
* **Workflow:** offline Python pipeline (логический аналог n8n enrichment-нод). Hierarchy-dev / Sem0→Sem1→Norm / Dir/Need **не трогались**.
* **Version:** `prompt_enrichment_v1`.
* **Model:** Polza OpenAI-compatible → `qwen/qwen3.5-flash-02-23@reasoning_effort=none` (`response_format=json_object`, temp 0.2).
* **Sources:**
  * `scripts/sem_enrich_mnn_rx.py` — load CSV → filter → Polza → post-process → artifacts;
  * `scripts/hierarchy_nodes/enrichment_build_prompt.js` — system/user (drug | vitamin_or_baa);
  * `scripts/hierarchy_nodes/enrichment_post_process.js` — parse/canon/eligibility helpers;
  * `scripts/sem_enrich_mnn_rx_fixtures.test.mjs` — offline fixtures.

#### Eligibility (Wave-500)

* **drug:** enrich если `attr_mnn` пуст **или** `attr_rx_otc` не в каноне `rx|otc|не применимо` (free-text Wave-500).
* **vitamin_or_baa:** enrich при nutrient-hit (`NUTRIENT_RULES`: Куркумин, Омега-3, Коэнзим Q10, …) **или** пустой mnn без мультивитаминного бренда; **skip** `mnn=Комплекс` + (мультивитамин / нет nutrient-hit).
* Иные kind → out of scope.

#### Output contract

```json
{
  "mnn_enriched": "...|null",
  "rx_otc_enriched": "rx|otc|unknown|не применимо",
  "combination_hint_enriched": "monocomponent|multicomponent|unknown|null",
  "mnn_source": "qwen_enrichment",
  "rx_source": "qwen_enrichment",
  "confidence_enriched": 0.0,
  "explanation_enriched": "..."
}
```

* drug: `rx_otc_enriched` ∈ {`rx`,`otc`,`unknown`}; vitamin: `не применимо` + combination_hint.
* Errors/timeouts → `mnn_enriched=null`, `rx_otc_enriched=unknown` (drug) / `не применимо` (vitamin), `error_message` set. Max 1 retry.

#### Evidence (Wave-500)

* Input: `redesign/artifacts/sem_wave500_report.csv` (500).
* Eligible **254** (drug 183 / vitamin_or_baa 71); skipped 246 (out_of_scope 175 / drug_ok 41 / vitamin_complex 23 / vitamin_no_signal 7).
* Called **254**, errors **0**.
* **MNN filled:** 93 (drug 73 / vitamin 20); null 161.
* **RX (drug):** rx 47 / otc 50 / unknown 86.
* **Vitamin combination_hint:** mono 19 / multi 6 / unknown 46.
* Smoke N=10 beforehand: mnn_filled 6 / errors 0.
* Offline fixtures: `node --test scripts/sem_enrich_mnn_rx_fixtures.test.mjs` — **15/15**.

#### Artifacts

* `redesign/artifacts/sem_wave500_mnn_rx_enriched.csv`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched.json`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched_summary.md`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched_summary.json`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched_run.log`
* Smoke: `sem_wave500_mnn_rx_enriched_smoke10.*`

#### Explicitly out of scope (this patch)

* Merge `mnn_enriched` / `rx_otc_enriched` into Dir/Need/MNN cascade or Sem `attr_*`.
* Changes to `classification-stage2-hierarchy-dev` / prod Stage 2.
* Human labeling Wave-500.

#### Next

* Review Wave-500 enrichment quality (spot-check drug INN + vitamin nutrients).
* Decide merge rule: when confident `mnn_enriched` may override / feed Dir–Need–Mnn (отдельный шаг).
* Human labeling / gate scoring Wave-500.
* Offline MNN/RX enrichment (п.35).

---

35. **Offline MNN/RX enrichment — drug + vitamin_or_baa via Polza/Qwen (2026-08-05)**

* **Статус:** **done** (offline layer; cascade untouched). Clone-only hierarchy Sem export; snapshot-off; prod untouched; SQL/DDL не менялись.
* **Цель:** после Sem+Norm дополнить snapshot/log-кандидаты полями `mnn_enriched` / `rx_otc_enriched` (и `combination_hint_enriched` для БАД), **не переписывая** baseline `attr_mnn` / `attr_rx_otc`.
* **Workflow:** offline Python pipeline (логический аналог n8n enrichment-нод). Hierarchy-dev / Sem0→Sem1→Norm / Dir/Need **не трогались**.
* **Version:** `prompt_enrichment_v1`.
* **Model:** Polza OpenAI-compatible → `qwen/qwen3.5-flash-02-23@reasoning_effort=none` (`response_format=json_object`, temp 0.2).
* **Sources:**
  * `scripts/sem_enrich_mnn_rx.py` — load CSV → filter → Polza → post-process → artifacts;
  * `scripts/hierarchy_nodes/enrichment_build_prompt.js` — system/user (drug | vitamin_or_baa);
  * `scripts/hierarchy_nodes/enrichment_post_process.js` — parse/canon/eligibility helpers;
  * `scripts/sem_enrich_mnn_rx_fixtures.test.mjs` — offline fixtures.

#### Eligibility (Wave-500)

* **drug:** enrich если `attr_mnn` пуст **или** `attr_rx_otc` не в каноне `rx|otc|не применимо` (free-text Wave-500).
* **vitamin_or_baa:** enrich при nutrient-hit (`NUTRIENT_RULES`: Куркумин, Омега-3, Коэнзим Q10, …) **или** пустой mnn без мультивитаминного бренда; **skip** `mnn=Комплекс` + (мультивитамин / нет nutrient-hit).
* Иные kind → out of scope.

#### Output contract

```json
{
  "mnn_enriched": "...|null",
  "rx_otc_enriched": "rx|otc|unknown|не применимо",
  "combination_hint_enriched": "monocomponent|multicomponent|unknown|null",
  "mnn_source": "qwen_enrichment",
  "rx_source": "qwen_enrichment",
  "confidence_enriched": 0.0,
  "explanation_enriched": "..."
}
```

* drug: `rx_otc_enriched` ∈ {`rx`,`otc`,`unknown`}; vitamin: `не применимо` + combination_hint.
* Errors/timeouts → `mnn_enriched=null`, `rx_otc_enriched=unknown` (drug) / `не применимо` (vitamin), `error_message` set. Max 1 retry.

#### Evidence (Wave-500)

* Input: `redesign/artifacts/sem_wave500_report.csv` (500).
* Eligible **254** (drug 183 / vitamin_or_baa 71); skipped 246 (out_of_scope 175 / drug_ok 41 / vitamin_complex 23 / vitamin_no_signal 7).
* Called **254**, errors **0**.
* **MNN filled:** 93 (drug 73 / vitamin 20); null 161.
* **RX (drug):** rx 47 / otc 50 / unknown 86.
* **Vitamin combination_hint:** mono 19 / multi 6 / unknown 46.
* Smoke N=10 beforehand: mnn_filled 6 / errors 0.
* Offline fixtures: `node --test scripts/sem_enrich_mnn_rx_fixtures.test.mjs` — **15/15**.

#### Artifacts

* `redesign/artifacts/sem_wave500_mnn_rx_enriched.csv`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched.json`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched_summary.md`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched_summary.json`
* `redesign/artifacts/sem_wave500_mnn_rx_enriched_run.log`
* Smoke: `sem_wave500_mnn_rx_enriched_smoke10.*`

#### Explicitly out of scope (this patch)

* Merge `mnn_enriched` / `rx_otc_enriched` into Dir/Need/MNN cascade or Sem `attr_*`.
* Changes to `classification-stage2-hierarchy-dev` / prod Stage 2.
* Human labeling Wave-500.

#### Next

* Review Wave-500 enrichment quality (spot-check drug INN + vitamin nutrients).
* Decide merge rule: when confident `mnn_enriched` may override / feed Dir–Need–Mnn (отдельный шаг).
* Human labeling / gate scoring Wave-500.

---

36. **MNN Catalog Consensus + Enrichment Router v1 (offline, 2026-08-12)**

* **Цель:** два последовательных слоя для hierarchy-dev / offline batch:
  1. `MNN — Catalog Consensus Resolver` (без LLM) — нормализация, `anchor_component` safe-union, RX/Age независимо;
  2. `MNN — Enrichment Router` — только `unresolved_catalog` drug → `POST /webhook/mnn-drug-enrichment` (`bEyKA1JJr0swuLql`).
* **Eligibility:** только `product_kind=drug`; skip homeopathy / device / vitamin_or_baa / cosmetic / other.
* **Safe union:** union только при наличии `anchor_component` (≥2 evidence-qualified sources: `explicit_mnn|active_ingredient`); иначе `unresolved_catalog` → enrichment.
* **Canonical vs raw:** `resolved_mnn` = join канонических компонентов; raw только в `source_raw_mnn` / audit. Не использовать «самую длинную» карточную строку.
* **Не перезаписывать:** `attr_mnn`, `attr_rx_otc`, `semantic_attrs.mnn`, snapshot `product_classification`.
* **DB logging:** schema gate → `db_logging_mode=artifacts_only_schema_blocked` (Docker/Postgres unreachable). Mode 2 `new_enrichment_run` (`run_type=stage2_mnn_catalog_enrichment_v1`) предпочтителен при доступной БД. Новые log events с `run_id=null` запрещены. Stages (когда DB up): `mnn_catalog_resolve`, `mnn_enrichment`.
* **Prod / live:** `classification-stage2-dev` и live-wire hierarchy-dev **не менялись**. JS mirrors подготовлены, не подключены.

#### Code / nodes

* `scripts/lib/mnn_normalization.py`
* `scripts/lib/mnn_catalog_consensus.py`
* `scripts/lib/mnn_enrichment_map.py`
* `scripts/mnn_catalog_resolution_wave500.py`
* `scripts/mnn_catalog_consensus_fixtures.test.mjs`
* `scripts/hierarchy_nodes/mnn_normalization.js`
* `scripts/hierarchy_nodes/mnn_catalog_resolve.js`
* `scripts/hierarchy_nodes/mnn_enrichment_router.js`
* `scripts/hierarchy_nodes/mnn_catalog_prepare_log.js`

#### Offline tests

* `node scripts/mnn_catalog_consensus_fixtures.test.mjs` — **23/23**.

#### Wave-500 batch (eligible drugs)

* total **217** · catalog resolved **165** · unresolved catalog **52**
* enrichment called **52** · accepted **21** · unresolved final **31**
* `db_logging_mode=artifacts_only_schema_blocked`

#### Artifacts

* `redesign/artifacts/mnn_catalog_resolution_wave500.csv`
* `redesign/artifacts/mnn_catalog_resolution_wave500.json`
* `redesign/artifacts/mnn_catalog_resolution_wave500_summary.md`
* `redesign/artifacts/mnn_catalog_resolution_wave500_progress.json`
* `redesign/artifacts/mnn_catalog_resolution_schema_gate.md`

#### Explicitly out of scope

* Live wire into hierarchy-dev Sem→Dir path.
* Prod Stage2 changes / DDL / snapshot writes / auto-overwrite `attr_*`.
* vitamin_or_baa nutrient MNN layer.

#### Next

* When Postgres available: Mode 2 `new_enrichment_run` + log stages `mnn_catalog_resolve` / `mnn_enrichment`.
* Spot-check enrichment accepts; decide soft-signal merge of `resolved_mnn` into Dir/Need/Mnn (separate confirmation).
* Do **not** connect resolver to live Stage2 until explicit approval.


---

37. **Wave-500 MNN v2 (Sem + Catalog + Enrichment → PostgreSQL + Search Evidence Bundle) (2026-08-12)**

* **Цель:** новый изолированный Sem wave (без overlap с prior Wave-500) → **обязательный rollback** hierarchy-dev → offline Catalog Consensus + Enrichment Router с DB audit logs, auto-retry и Search Evidence Bundle.
* **DeepSeek fix:** native `@n8n/n8n-nodes-langchain.lmChatDeepSeek` + `deepseek-v4-flash` / `deepseek-chat` → **401 Incorrect API key**. Sem0/Sem переключены на community node **`DeepSeek V4 Chat Model`** (`n8n-nodes-deepseek-v4-thinking-fix.deepSeekV4ChatModel`, model `deepseek-v4-flash`, `thinkingMode=disabled`, credential `DeepSeek account`). Smoke exec **40248** `sem_post=1` OK. Backup smoke JSON тоже с V4, чтобы rollback не откатывал на broken LM.
* **Allowlist N:** requested 500; load-compatible pool after exclude prior Wave-500 + smoke allowlists → **N=57** (tier1 classified fill removed — Load only `pending|needs_human_review`). Overlap prior Wave-500 = **0**. Artifact: `sem_wave500_mnn_v2_allowlist.json`.
* **Sem:** chunks 6×10 (last 7), execs **40252,40255,40258,40261,40265,40268**; hierarchy run_ids in report **398–403**; report rows **57** (drug **28**). Rollback: kill-switch off, allowlist `[]`, Load `WHERE false`, assert-safe OK **before** MNN.
* **MNN enrichment run:** `classification_runs.id=405`, `run_type=stage2_mnn_catalog_enrichment_v1`, status `finished_with_review`, success_count=27, error_count=1, metadata.total_count=28, needs_review_count=1. (Orphan `id=404` left `running` from stdout-parse glitch on first create — superseded by 405; close manually if needed.)
* **DB logs (run 405):** `mnn_catalog_resolve=28`, `mnn_enrichment=8`.
* **Metrics (eligible drugs 28):** catalog resolved **20**; enrichment calls **8**; attempts **11**; raw SearXNG saved **11**; retries **3**; accepted **7**; avg search_count **16.0**; selected evidence rows **132**; unresolved final **1** (with evidence); human_review CSV **28** (cap = eligible).
* **Search Evidence Bundle:** append-only JSONL + curated `research_context` in enrichment `output_payload` + normalized research_context CSV/JSON. Helper `load_latest_mnn_resolution(product_id)` prepared — **not** live-wired to Sem/Dir/Need.
* **Prod / attr_* / snapshot:** not modified.

#### Code

* `scripts/lib/mnn_search_evidence.py`
* `scripts/lib/mnn_resolution_query.py`
* `scripts/mnn_catalog_resolution_wave500_v2.py`
* `scripts/sem_wave500_mnn_v2_allowlist.py` (load-compatible only)
* `scripts/sem_wave500_mnn_v2_orchestrator.py`
* `scripts/mnn_wave500_v2_score_labels.py` (stub)

#### Artifacts

* `redesign/artifacts/sem_wave500_mnn_v2_allowlist.json`
* `redesign/artifacts/sem_wave500_mnn_v2_report.csv` / `_progress.json`
* `redesign/artifacts/sem_wave500_mnn_v2_from_catalogs.csv`
* `redesign/artifacts/mnn_catalog_resolution_wave500_v2.{csv,json,_summary.md,_progress.json,_human_review.csv}`
* `redesign/artifacts/mnn_wave500_v2_searxng_raw.jsonl`
* `redesign/artifacts/mnn_wave500_v2_research_context.{csv,json}`
* `redesign/artifacts/mnn_wave500_v2_schema_gate.md`

#### Explicitly out of scope

* Live-wire evidence → Dir/Need/Mnn / Sem shortlist.
* Closing orphan run 404 (ops).
* Expanding allowlist back to N=500 without load-compatible pool.

#### Next

* Human labels on `mnn_catalog_resolution_wave500_v2_human_review.csv` → score stub.
* Soft-context use of `load_latest_mnn_resolution` in future Dir/Need (explicit approval).
* Optionally close run 404; optionally rebuild larger allowlist if pending pool grows.

---

38. **Offline MNN identity gate Wave‑500 v3 + post-identity enrichment (run 461) + human-review quality baseline (2026-08-17)**

* **Статус:** **done** (offline quality baseline). Prod Stage 2 / live Sem / snapshot / `attr_mnn` / `attr_rx_otc` / `attr_age_segment` — **не менялись**.
* **Цель шага:** зафиксировать fact-backed quality baseline **до** изменения policy / prompt / normalization / workflow.
* **Канон метрик:** `redesign/artifacts/mnn_identity_enrichment_pass_review_metrics_v1.md` (+ `.json`); inventories `*_review_*_errors_v1.csv`, `*_non_drug_null_mnn_v1.csv`, `*_text_quality_v1.csv`.
* **Labeled input:** `redesign/artifacts/mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv` (не перезаписывался).

#### Done (подтверждено артефактами)

* Offline **MNN catalog identity gate** Wave‑500 **v3** — завершён (отдельные `*_identity_gate*` / `*_from_catalogs_identity*` artifacts; baseline v3 immutable).
* **Post-identity enrichment pass:** `classification_runs.id=461`, `run_type=stage2_mnn_identity_gate_enrichment_v1`.
* Enrichment: **104** calls · **86** accepted · **9** retries · **18** `unresolved_final`.
* **Human-review v2:** **100** строк · **0** duplicate `product_id` · `label_mnn` 100/100; RX/Age labelled 83/100 (17 `not_labeled`, совпадают с non-drug/`should_be_empty` slice).

#### Headline metrics (human labels)

* **MNN (all relevant):** 99/100 = 99.0% (`correct` + `should_be_empty` vs error outcomes).
* **MNN drugish slice** (rows where `label_mnn ≠ should_be_empty`; **не** computed Drug classifier): **82/83**.
* **Correct null-MNN for non-drug** (`label_mnn=should_be_empty`): **17**.
* **RX/OTC:** **72/83** = 86.7%.
* **Age:** **59/83** = 71.1%.
* **MNN gaps in sample:** **1** error row — `product_id=19198`, «Зверобоя трава Фитофарм», `new_enrichment_status=ok_partial`, `final_mnn_method=unresolved_final`, empty `final_candidate_mnn`, reviewer `label_mnn=incorrect` (notes: Drug / OTC / взрослый). Корректное МНН **не** выводилось автоматически.
* **Norm text quality (confirmed):** manufacturer-like duplicate `|` segments **100/100**; pack-token dups **14/100**; median length 82 / p90 124.1.

#### Policy decisions (зафиксировано; без prod merge)

* **MNN** — пока **не** вливать в `attr_mnn` и **не** подключать в live Sem / Dir–Need–Mnn.
* **RX/OTC** — **не** использовать как hard gate для RX clusters.
* **Age** — **не** использовать в routing до формализации словаря и evidence policy.
* Уточнение **product kind** из enrichment (`Category=BAS|Other|Drug` в research / proposed override buckets) — только **proposed / offline candidate**. Это **не** изменение `product_type` / `product_kind` в snapshot и **не** write в `product_classification`.

#### Explicitly out of scope (этот пункт)

* INSERT/UPDATE `product_classification` / `attr_*` / Sem live wiring / Norm rewrite.
* New SearXNG / webhook / LLM passes beyond already-finished run 461.
* Treating review sample as random population estimate.

#### Next (roadmap)

1. ~~Offline BAS/Other override policy~~ → **done**, см. **п.39**.
2. ~~M3.0 source audit + M3.1 retriever design~~ → **done**, см. **п.40**.
3. ~~M3.2a inactive skeleton + n8n runtime smoke~~ → **done**, см. **п.41** / **п.42**.
4. ~~M3.2b one-item live retrieval~~ → **done**, см. **п.43**.
5. ~~M3 RX/OTC research closeout~~ → **done**, см. **п.44**.
6. ~~Age contract~~ → **done**, см. **п.45**.
7. **Norm v4 experiment** (dedupe manufacturer/pack в `normalized_text`; offline only).

#### Key artifacts

* Identity gate: `mnn_catalog_resolution_wave500_v3_identity_gate.*`, `sem_wave500_mnn_v3_from_catalogs_identity.*`
* Enrichment pass 461: `mnn_identity_enrichment_pass_{results,summary,candidates,human_review*}`
* Review baseline: `mnn_identity_enrichment_pass_review_metrics_v1.{md,json}` + error/non-drug/text-quality CSVs
* Analyzer: `scripts/mnn_identity_enrichment_pass_review_metrics_v1.py`

---

39. **Offline BAS/Other override policy v1 + human validation (M2 / M2.1) (2026-08-17)**

* **Статус:** **done** (offline / audit-only; human-validated). Prod Stage 2 / live Sem / snapshot / `product_kind` / `product_type` / `attr_*` — **не менялись**.
* **Вход:** 18 reviewed null-MNN / non-drug candidates из Wave‑500 identity enrichment **run_id=461** (`mnn_identity_enrichment_pass_review_non_drug_null_mnn_v1.csv` + metrics / results / research_context / human-review v2).
* **Policy v1:** детерминированные proposals по existing evidence only — **no new SearXNG / LLM / enrichment**.
* **Human validation (M2.1):** labeled `mnn_non_drug_override_policy_v1_human_review - mnn_non_drug_override_policy_v1_human_review.csv` → immutable freeze `mnn_non_drug_override_policy_v1_reviewed.csv`.

#### Applied offline proposals (reviewed freeze)

| Outcome | Count | Notes |
|---------|------:|-------|
| **BAS** | **12** | `final_proposed_product_kind=bas` |
| **Other** | **1** | `product_id=9197` |
| **no applied proposal** | **5** | `72`, `11272`, `45`, `19198`, `9941` |
| **exclude from future drug-MNN enrichment / human queue** | **13** | `final_queue_action=remove_from_future_mnn_human_queue` |
| MNN action for applied | — | null / not_applicable (`keep_null_not_applicable` semantics) |

#### Policy posture

* Remains **offline / audit-only**.
* **No** PostgreSQL writes; **no** `classification_runs`; **no** `product_kind` / `product_type` / snapshot / Sem / `attr_*` updates.
* Implementation contract `mnn_non_drug_override_policy_v1_implementation_contract.md` is **draft only — not applied**.

#### Key artifacts

* Policy: `mnn_non_drug_override_policy_v1.{csv,summary.md,summary.json,human_review.csv,data_dictionary.md}`
* Reviewed freeze: `mnn_non_drug_override_policy_v1_reviewed.{csv,summary.md,summary.json}`
* Contract (draft): `mnn_non_drug_override_policy_v1_implementation_contract.md`
* Analyzer: `scripts/mnn_non_drug_override_policy_v1.py`

#### Next

* ~~M3.0/M3.1~~ → **done**, см. **п.40**.
* **M3.2a** inactive skeleton `rx-otc-product-retrieval-dev` (explicit ask; не hard gate).
* ~~M4 Age contract~~ → **done**, см. **п.45**.
* **M5** Norm v4 experiment.
* Apply M2 queue-exclusion contract only after explicit approval.

---

40. **M3.0 RX/OTC source audit + M3.1 standalone Product Retrieval design (2026-08-18)**

* **Статус:** **done** (design only). Prod Stage 2 / hierarchy-dev / `mnn-drug-enrichment` / live Sem / snapshot / `attr_*` — **не менялись**. Workflow `rx-otc-product-retrieval-dev` — **не создан**.
* **M3.0:** 11 confirmed RX/OTC error rows (Phase A IDs `1053`, `2621`, `3065`, `4922`, `4924`, `7275`, `10046`, `18377`, `19198`, `19370`, `26115`); **0/11** product-specific sufficient evidence; **0** saved GRLS product-card; **0** explicit status in saved titles/excerpts. Приказ Минздрава №100н = regulatory context only, not SKU evidence.
* **Architecture (locked):** standalone workflow **design** for future inactive workflow `rx-otc-product-retrieval-dev`, `workflow_version=rx_otc_retrieval_dev_v1`. n8n workflow **not created**. Not a sub-branch of MNN identity/enrichment. MNN acceptance ≠ RX/OTC acceptance. **Not** a hard routing gate. **No** automatic production merge.
* **Evidence:** GRLS product record / official instruction = **P1**; pharmacy/aggregator = **P2 supporting only** (`candidate_rx_otc_value` set, `final_rx_otc_value=null`, outcome=`supported_only`); landing/generic MNN = **P3 discovery**. P2 **never** sets a final accepted RX/OTC value and cannot drive snapshot/`attr_*`/routing.
* **Budget:** `logical_search_query_count <= 8` (Q1≤3, Q2≤3, Q3≤2); `transport_retry_attempt_count <= 2` per logical query; `fetched_page_count <= 4`. Search ≠ fetch; transport retries do not increment the logical query count.
* **M2-13** approved BAS/Other IDs — excluded from RX retrieval (`not_applicable`). **19198** remains Drug / eligible for retrieval; `review_label_inconsistency=true`; out of RX/OTC precision denominator until `expected_rx_otc_manual` ∈ {rx, otc, unknown}. Historic labels **not** rewritten.
* **Rollout:** M3.2a inactive skeleton (stubs, no HTTP/DB) → M3.2b one-item after explicit approval → M3.2c 11 errors + 30 blind (no snapshot/`attr_*`) → M3.3 human metrics → M3.4 proposed layer only if metrics pass.

#### Key artifacts

* Design: `redesign/m3_1_rx_otc_retriever_design.md`
* Contract: `redesign/m3_1_rx_otc_retriever_contract.json`
* Query examples (designed, not executed): `redesign/m3_1_rx_otc_retriever_query_examples.csv`
* Data model (proposal, no migration): `redesign/m3_1_rx_otc_retriever_data_model.md`
* M3.2 test plan: `redesign/m3_1_rx_otc_retriever_m3_2_test_plan.md`
* M3.0 audit: `redesign/artifacts/mnn_rx_otc_source_audit_v1_summary.{md,json}`

#### Next

* ~~M3.2a inactive skeleton~~ → **done**, см. **п.41**.
* **M3.2a n8n runtime smoke** pending (task runner). Do not start M3.2b until live execute works.

---

41. **M3.2a inactive skeleton `rx-otc-product-retrieval-dev` (2026-08-18)**

* **Статус:** **done** (skeleton created, **inactive**). Runtime smoke: **п.42**.
* **Workflow:** `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`), `workflow_version=rx_otc_retrieval_dev_v1`, `active=false`.
* **Isolation:** no HTTP / LLM / Postgres nodes; prod Stage 2 / hierarchy-dev / `mnn-drug-enrichment` untouched; `run_id=null` (`run_id_mode=none_no_db_in_m3_2a`); no `attr_*` / snapshot / `product_kind`.
* **Structural verification:** export 32 nodes; required topology present; webhook path `rx-otc-product-retrieval-dev`; no credentials; forbidden-node check ok. Local Code-node replay of export: Smoke A (3065 pass / unresolved), B (9197 exclude / `E_M2_NON_DRUG`), C (empty text / `E_INPUT_IDENTITY`).
* **Runtime gap (closed in п.42):** Public API has no `POST /workflows/{id}/run`; production webhook returns 404 while inactive (expected). CLI `n8n execute` needs `N8N_RUNNERS_BROKER_PORT≠5679`.

#### Key artifacts

* Export: `workflows/rx-otc-product-retrieval-dev.json` + `.id`
* Inventory / smoke: `redesign/artifacts/rx_otc_retrieval_m3_2a_{workflow_inventory,smoke_results,smoke_summary}.*`
* Identity source: `scripts/hierarchy_nodes/rx_otc_build_identity.js`
* Create helper: `scripts/create_rx_otc_retrieval_m3_2a.py`
* Local replay: `scripts/rx_otc_m3_2a_local_smoke.js`

#### Next

* ~~M3.2a n8n runtime smoke~~ → **done**, см. **п.42**.
* Not: activate workflow, HTTP/SearXNG/LLM, DB writes, `attr_rx_otc` merge, M3.2b without explicit ask.

---

42. **M3.2a n8n runtime smoke `rx-otc-product-retrieval-dev` (2026-08-18)**

* **Статус:** **done** (live CLI executes on inactive workflow). Prod Stage 2 / hierarchy-dev / `mnn-drug-enrichment` / snapshot / `attr_*` — **не менялись**.
* **Workflow:** `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`) left `active=false`. Export jsCode restored after smokes (matches git).
* **Execute path:** `docker exec -e N8N_RUNNERS_BROKER_PORT=15679 n8n execute --id=…`. Public API `/run` still 405. Default broker 5679 is taken by the live instance. `n8n execute` **ignores pinData** (Manual Trigger starts as `{}`); runner temporarily injects the case payload into `In — Normalize Input`, then restores the git export.
* **Results (success, ~3 s each, sequential):**

| Case | exec | m2 | outcome | error |
|------|------|----|---------|-------|
| A eligible 3065 | **42679** | pass | unresolved | `E_SOURCE_NOT_FOUND` (stubs, executed search/fetch = 0; Q1/Q2/Q3 planned 3/3/2) |
| B exclude 9197 | **42680** | exclude | not_applicable | `E_M2_NON_DRUG` (Q1/Q2/Q3 did not run) |
| C invalid 999999 | **42681** | — | rejected | `E_INPUT_IDENTITY` (Q1/Q2/Q3 did not run) |

* Production webhook while inactive: **HTTP 404** (expected). `run_id=null`. Isolation flags all false.
* Earlier failed CLI **42674** (08:09 UTC) was task-broker timeout on port 5679 — superseded.

#### Key artifacts

* Runtime: `redesign/artifacts/rx_otc_retrieval_m3_2a_runtime_smoke_{results.json,summary.md}`
* Runner: `scripts/run_rx_otc_m3_2a_runtime_smoke.py`

#### Next

* ~~M3.2b one-item live retrieval~~ → **done**, см. **п.43**.
* Not: activate skeleton, LLM, DB writes, M3.2c batch, `attr_rx_otc` merge.

---

43. **M3.2b one-item live RX/OTC retrieval SKU 3065 (2026-08-18)**

* **Статус:** **done** (runner-side SearXNG + page fetch). Prod Stage 2 / hierarchy-dev / `mnn-drug-enrichment` / snapshot / `attr_*` / n8n RX/OTC workflow — **не менялись**. Workflow `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`) left `active=false` (HTTP must land in git artifacts, not n8n).
* **SKU:** `3065` Флуконазол-OBL капс. 150 мг №4 (M2-13 not sent). Identity: `"ФЛУКОНАЗОЛ-OBL" "капсулы" "150 мг"`. `run_id=20260818` ephemeral artifact-only (no `classification_runs`).
* **Search:** 7 logical queries (Q1=3, Q2=3, Q3=1; cap 8). Default SearXNG engines unresponsive (429/CAPTCHA); same logical queries retried with `engines=bing` (1 transport retry). Q1 `site:grls` returned **no** GRLS `Grls_view_V2` records.
* **Fetch:** 4 pages (cap 4). Brand-matching P2 only in Q3 (Q1/Q2 do not spend fetch budget on pharmacy/RLS). Vidal `fluconazole-obl__37379` = P2 product card, identity A, explicit «Без рецепта». `apteka.ru` = JS shell, no status.
* **Outcome:** `supported_only` / candidate `otc` / **`final_rx_otc_value=null`** (P2 never sets final). Comparators read-only: sem=`rx`, catalog=`otc`. Human-review `expected_rx_otc_manual` left empty.
* **Isolation:** LLM false; postgres/snapshot/`attr_*`/`product_kind` false; n8n inactive.

#### Key artifacts

* Runner: `scripts/run_rx_otc_m3_2b_one_item.py`
* `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_{one_item.json,human_review.csv,summary.md}`
* Raw: `redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl`

#### Next

* ~~M3 research closeout~~ → **done**, см. **п.44**.
* Not: activate skeleton, LLM, DB writes, `attr_rx_otc` merge, M3.2c.

---

44. **M3 closeout — RX/OTC evidence feasibility decision (2026-08-19)**

* **Title:** M3 closeout — RX/OTC evidence feasibility decision.
* **Статус:** **done** (research closed / paused). Prod Stage 2 / hierarchy-dev / snapshot / `attr_*` / `product_kind` / `product_type` / Sem live / PostgreSQL / `classification_runs` — **не менялись**. Workflow `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`) remains **inactive**. No CAPTCHA/login bypass.

#### Completed

* M3.0 source audit
* M3.1 standalone RX/OTC retriever design
* M3.2a inactive skeleton + n8n runtime smoke
* M3.2b one-item live P2 support test
* M3.2b.2 evidence contract v2 patch
* M3.2b.3 SearXNG/Bing P1 feasibility (5 SKU)
* M3.2b.4 direct official GRLS access investigation (10 SKU)
* M3.2b.5 MAH/official instruction feasibility (10 SKU)
* Brandquad / distributor probes (research/support only; not official P1)
* Investigation synthesis v1

#### Confirmed technical facts

* Wave-500 baseline RX/OTC: **72/83 = 86.7%**; **11** confirmed RX/OTC errors; M3.0 **0/11** sufficient product-specific evidence.
* **No stable unattended official GRLS P1 route:** public form/record endpoints exist (`GRLS.aspx` POST, `Grls_View_v2`) but final testing encountered TLS / WAF 403 / `/cp/login` barriers. No CAPTCHA/login bypass. M3.2b.4 valid P1 in final CSV: **0/10**.
* **MAH P1b route is only partially feasible:** **2/10** valid official product-specific Termikon spray/cream instructions. Not a general mass route.
* Brandquad public GRLS mirror may be useful research/support data but is **not** official P1 and must not set `final_rx_otc_value`.
* P2 (Vidal/RLS/pharmacy/ASNA) remain supporting-only. P2 may set `candidate_rx_otc_value` but **never** `final_rx_otc_value`.
* M3.2b evidence contract v2 passes: `discovery_hits` / `fetched_documents` / `validated_evidence` separated; only fetched HTTP 2xx content can validate status.
* Identity guards correctly reject form conflicts: Termikon spray vs cream/tablets; Duspatalin tablets 135 mg vs capsules 200 mg.
* Do **not** claim final RX/OTC correctness, P1 coverage beyond 2/10 P1b feasibility, any DB/production merge, or that Brandquad is official.

#### Decision

`KEEP_RX_OTC_P2_SUPPORT_ONLY` and `DO_NOT_RUN_PHASE_A_YET`.

#### Operational policy

* RX/OTC must not be merged into `attr_rx_otc` / snapshot / Sem.
* RX/OTC must not be a hard routing gate for RX clusters.
* P2 may be displayed as audit/human-review soft signal only, with identity guard by brand/form/strength/manufacturer.
* Standalone workflow remains inactive.
* M3.2c (11 errors + 30 blind) does **not** run.

#### Future re-entry criteria

* stable public official GRLS interface without login/WAF; **or**
* approved MAH/official instruction source registry with enough coverage; **or**
* separate user-approved decision to validate P2 as a soft signal via a new human-reviewed experiment.

#### Key artifacts

* Synthesis: `redesign/artifacts/mnn_rx_otc_investigation_synthesis_v1.md`
* Contract v2: `redesign/m3_2b_rx_otc_evidence_contract_v2.md`
* M3.2b.3/4/5 summaries: `redesign/artifacts/mnn_rx_otc_retrieval_m3_2b_3_summary.md`, `mnn_rx_otc_grls_access_v1_summary.md`, `mnn_rx_otc_p1b_instruction_v1_summary.md`

#### Next

* **M4** Age contract + evidence policy (offline/audit-only) — **done**, см. **п.45**.
* Not: M3.2c, workflow activation, snapshot/`attr_*` merge.
* **M5** Norm v4 experiment — next offline track.

---

45. **M4 Age pilot contract validated (M4.0–M4.2.2) (2026-08-19)**

* **Статус:** **done** (offline / audit-only; pilot contract validated). Prod Stage 2 / hierarchy-dev / snapshot / `attr_age_segment` / `attr_*` / `product_kind` / Sem live / PostgreSQL / `classification_runs` — **не менялись**. No web / LLM / n8n in M4.2.x.
* Age is **not** a routing gate. Do not merge into `attr_age_segment` until explicit approval.

#### Completed

* M4.0 Age contract audit + evidence model (`age_contract_v1`)
* M4.1 / M4.1.1 Age policy replay v1→v2 (historical `not_applicable` without M2 → unknown, not conflict)
* M4.2 threshold reconciliation: min years separate from segment; 12/14/15/16 ≠ adults
* M4.2.1 reviewed merge of labelled follow-up (7 rows)
* M4.2.2 accept explicit `age_min_years=10` (integer 0–18); v1.1 freeze

#### Pilot result (40 unique drug `product_id`)

| reviewed_age_segment | n |
|----------------------|--:|
| взрослые (18+) | 16 |
| универсальный | 24 |
| дети | 0 |
| unknown / conflict / not_applicable | 0 |
| exceptions | 0 |

* Of original `should_be_adults` **26**: **16** stayed adults; **10** (12–16) → universal.
* `product_id=10046`: explicit min **10** + `children_and_adults` → универсальный; **not** remapped to 6 or 12.
* Children-only prevalence **cannot** be inferred: 0 explicit pediatric-only rows in this sample.

#### Canonical freeze

* Reviewed: `redesign/artifacts/mnn_age_threshold_reconciliation_reviewed_v1_1.*`
* Contract: `redesign/m4_age_threshold_reconciliation_reviewed_contract_v1_1.md`
* Mapping: `redesign/m4_age_threshold_mapping_v1.md`
* Script: `scripts/mnn_age_threshold_reconciliation_reviewed_v1.py` (writes v1_1 only; does not overwrite v1)

#### Next

* **M5** Norm v4 experiment (offline).
* Not: Age DB/routing/`attr_*` merge; M3.2c; activate `rx-otc-product-retrieval-dev`.
