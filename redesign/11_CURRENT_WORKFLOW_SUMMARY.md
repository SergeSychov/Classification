# Current workflow summary

Текущий Stage 2 pipeline устроен так:
1. rule-based shortlist
2. primary LLM
3. fallback 2A
4. fallback 2B
5. judge
6. human review

## Что уже есть
- `classification_runs`
- `product_classification`
- `product_classification_log`
- `classification_shortlist`
- run tracking через `run_id`
- primary/fallback/judge/human-review stages
- раздельные snapshot и event log

## Текущее поведение
### Primary LLM
Пытается довольно рано выбрать финальную `category_id`.

### Fallback 2A
Определяет ветку / block-family, не финальную категорию.

### Fallback 2B
Выбирает категорию внутри branch shortlist.

### Judge
Разрешает conflict / low-confidence / unresolved cases.

## Текущая проблема
Главная архитектурная слабость — слишком ранний shortlist и слишком ранняя попытка выбрать final `category_id` до полноценного semantic understanding товара.
