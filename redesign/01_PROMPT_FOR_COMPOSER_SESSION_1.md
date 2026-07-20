Мы проектируем redesign workflow категоризации аптечных товаров.

Рабочий контекст лежит в файлах текущей папки:
- `10_PROJECT_CONTEXT.md`
- `11_CURRENT_WORKFLOW_SUMMARY.md`
- `12_REDESIGN_TARGET.md`

Задача этой сессии:
выполнить только анализ и подготовить migration plan для новой ветки workflow. Ничего не реализовывай, пока план не подтверждён.

Требования к работе:
1. Сначала изучи контекстные файлы проекта.
2. Сформируй понимание текущей архитектуры.
3. Найди слабые места текущего pipeline.
4. Предложи минимально инвазивный migration path.
5. Не ломай текущий workflow.
6. Предлагай новую ветку / клон workflow.
7. Если данных недостаточно, сначала запроси недостающие материалы.
8. После существенных изменений плана напомни: «давай обновим файл проекта».

Что нужно спроектировать:
- semantic-first подход вместо early final category selection;
- hierarchy-aware cascade по дереву:
  - Направление
  - Потребность
  - Категория
  - МНН
- soft-to-hard ограничение кандидатов;
- DB/Code shortlist stages между уровнями дерева;
- judge / human review для спорных кейсов.

Что важно сохранить:
- `classification_runs`, единый `run_id`
- `product_classification.latest_run_id`
- `product_classification_log.run_id`
- паттерн `...item.json` в Code nodes
- post-processing после каждого LLM stage
- raw + validated logging
- workflow_version + prompt_version

Что хочу получить в ответе:
1. Understanding of current architecture
2. Weak points in current pipeline
3. Proposed target architecture
4. Node-level migration plan for n8n
5. DB/schema changes
6. Prompt/data contracts for new stages
7. Risks and open questions
8. Step-by-step implementation order

Дополнительно:
после реализации primary semantic agent нужно будет заложить пользовательскую валидацию на случайных выборках 100 / 500 / 1000 товаров.
