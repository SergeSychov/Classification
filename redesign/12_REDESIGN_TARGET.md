# Redesign target

## Подтверждённая иерархия категорий
- Направление
- Потребность
- Категория
- МНН

В каждом следующем уровне иерархии число допустимых вариантов сравнительно небольшое.

## Целевой принцип redesign
Новая ветка workflow должна перейти от shortlist-first к semantic-first и hierarchy-aware cascade.

## Целевой pipeline
1. normalize product
2. semantic_primary
3. direction_selector
4. shortlist builder for needs inside selected direction
5. need_selector
6. shortlist builder for categories inside selected need
7. category_selector
8. optional mnn_selector inside selected category
9. judge / human review

## Ключевые требования
- `semantic_primary` не выбирает final `category_id`
- ранняя стадия должна извлекать полезные semantic attributes
- ограничения по дереву нужно делать через DB/Code shortlist stages, а не только через prompts
- верхние уровни дерева должны использовать soft-to-hard policy
- нижние уровни дерева должны быть жёстко ограничены разрешёнными потомками
- модель должна уметь возвращать `null` / `unknown`, а не галлюцинировать

## Примеры полезных semantic attributes
- `mnn`
- `brand`
- `rx_otc`
- `nosology`
- `administration_route`
- `dosage_form`
- `dosage`
- `age_segment`
- `package_hint`
- `combination_hint`

## Validation requirement
После реализации primary semantic agent нужно предусмотреть пользовательскую валидацию на случайных выборках:
- 100 товаров
- 500 товаров
- 1000 товаров
