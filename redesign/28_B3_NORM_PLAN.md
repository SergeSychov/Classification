# B3 Norm plan — hierarchy cascade

Date: 2026-07-20  
Scope: нормализация словаря (`categories_dict`) и ключевых входных полей для Sem / Dir / Need / Cat / Mnn.  
Depends on: `21a_SCHEMA_DUMP.md`, `21b_MAPPING_STATS.md`, `21_HIERARCHY_MAPPING_SAMPLES.md`, `29_SHORT_ROADMAP.md`.

## 1. Goals and constraints

- Norm — отдельный шаг перед Sem и дальнейшими стадиями каскада.
- Не менять `categories_dict` и продуктовые таблицы прямыми UPDATE в v1 — нормализация выполняется на уровне workflow/Code-нод.
- Цель Norm: сделать membership и сопоставление устойчивыми к:
  - Unicode-символам (дефисы, пробелы);
  - лишним пробелам и регистру;
  - частичным дубликатам/near-duplicates;
  - простым dirty-кейсам из `21_HIERARCHY_MAPPING_SAMPLES.md` [file:125].
- Norm не решает всё: BAD/травы/косметика остаются quasi-flat каскадом; MNN-устройства остаются SKU-like и требуют отдельной политики [file:124][file:125].

## 2. Norm targets in `categories_dict`

### 2.1 Direction (`direction`)

- Trim внешние пробелы.
- Case-fold: хранить/использовать lower-case форму для внутренних сравнений.
- Unicode-пунктуация: `–` / `—` → `-` при необходимости, но для `direction` это вторично (в исходных данных 10 distinct directions, без пустых) [file:124].
- Norm-ключ: `norm_direction = lower(trim(direction))`.

### 2.2 Need (`need_nosology`)

Based on S2/S3 verdicts: **Confirmed with caveats** [file:124][file:125].

**Norm правила:**

- Unicode-дефис `‑` (U+2011) → ASCII `-`:
  - `Моно‑минералы кальций` → `Моно-минералы кальций` [file:125].
- Collapse whitespace:
  - заменить последовательности пробелов/табов на один пробел;
  - удалить ведущие/замыкающие пробелы.
- Case-fold: `lower()` для внутренних сравнений.
- Не резать по запятым/точкам/слэшам в v1:
  - `Специализированные растворы для коррекции объёма и осмолярности (маннитол, гипертонический NaCl)` остаётся одним need-ключом [file:125].
- Norm-ключ:  
  `norm_need = lower(ascii_hyphen(collapse_whitespace(trim(need_nosology))))`.

**Импликации:**

- LS и MI (15 и 10 потребностей) → чистые каскад-ключи [file:124].
- BAD/травы/косметика: потребность ≈ категория (near-flat). Norm не делает каскад глубже; важно учитывать это при Sem/Dir/Need и policy Skip-LLM для singleton shortlist [file:124][file:125].
- High fan-in needs (`Сердце и сосуды` = 91 категорий, `Гормональные препараты` = 90) требуют аккуратного shortlist scoring; Norm только делает ключ стабильным [file:124].

### 2.3 Category name (`category_name`)

- Trim.
- Collapse whitespace.
- Case-fold для внутренних сравнений.
- Для некоторых направлений (BAD/витамины) `need_nosology` ≈ `category_name`; Norm должна позволять проверять `norm_need == norm_category_name` и помечать такие пары как near-flat [file:124][file:125].

Norm-ключ:  
`norm_category = lower(collapse_whitespace(trim(category_name)))`.

### 2.4 MNN cluster (`mnn_cluster`)

Based on verdict: **Confirmed with caveats**, optional leaf [file:124][file:125].

**Norm baseline:**

- Trim + collapse whitespace + case-fold.
- Unicode-символы/дефисы привести к ASCII аналогу, где безопасно.

**Classification flags (для Sem/Dir/Mnn, не для каскада напрямую):**

- `is_multi_sep`: строка содержит `[,;/\\|]` и выглядит как slash-list многих МНН (пример 16–18) [file:125].
- `is_eq_category`: `norm_mnn == norm_category_name` (пример 8, 955/954) [file:124][file:125].
- `is_device_sku_like`: содержимое похоже на SKU/spec:
  - размеры (`1,6 см × 5,7 см`, `40 × 60 см`) [file:124][file:125];
  - чувствительность (`20–25 мМЕ/мл ЛГ`) [file:125];
  - long brand+size descriptions [file:125].

Norm-ключ:  
`norm_mnn = lower(collapse_whitespace(trim(mnn_cluster)))`.

**Policy для v1:**

- Не использовать `norm_mnn` как жёсткий leaf‑ключ для всего словаря.
- Для Sem: использовать `norm_mnn` и флаги (`is_multi_sep`, `is_device_sku_like`, `is_eq_category`) как признаки, но не как прямой единственный идентификатор [file:125].
- Для Mnn‑стадии (B5+): использовать Norm как подготовку к split/selector, но сам split/selector — отдельный шаг.

## 3. Norm targets in product inputs

### 3.1 Product text (name + description)

- Собрать `combined_text` (уже есть в current Stage 2) и применить:
  - collapse whitespace;
  - unify Unicode дефисы/кавычки, где это помогает Sem;
  - удалить технический шум (HTML, простые артефакты).
- Не трогать клинический текст/индикации — это материал для Sem.

### 3.2 Product-level MNN / attributes

- Если на продукте есть MNN/форма/дозировка как отдельные поля — norm применить аналогично:
  - trim;
  - collapse whitespace;
  - case-fold;
  - ASCII‑дефисы.

- Для дальнейшего B3 Sem Norm важно:
  - иметь stable representation тех же сигнатур, что и словарь (`norm_mnn_product`, `norm_need_candidates`), но без жесткого принуждения к одному leaf.

## 4. Norm implementation pattern (workflow)

Norm в B3 планируется как:

- Code-ноды в `classification-stage2-hierarchy-dev`, которые:
  - читают словарные записи и входные продуктовые поля;
  - прикладывают `norm_*` функции к direction / need / category / mnn / product_text;
  - добавляют поля `norm_*` и флаги (`is_multi_sep`, `is_device_sku_like`, `is_eq_category`, `need_flat_like`) в item json.
- Norm не пишет в `product_classification` напрямую в v1 — это подготовка для Sem и последующих стадий.

## 5. Error-handling considerations (Norm layer)

Только план, без реализации:

- Невалидные Unicode / неожиданно пустые `need_nosology` / `direction` / `category_name`:
  - логировать как Norm warnings в `cascade_trace`;
  - не блокировать Sem, но помечать такие записи как “needs review in mapping”.
- Попытки split MNN, которые дают пустой набор или слишком много элементов:
  - в B3 Sem Norm не делать hard split; оставить как `is_multi_sep` + raw string, чтобы не потерять информацию.
- Отдельный error-handling track (30_ERROR_HANDLING_PLAN.md) будет описывать, как Norm-ошибки влияют на `decision_status` / `next_action`.

## 6. Integration with B3 Sem

Sem дизайн (отдельный `B3_SEM_PLAN`) должен:

- читать `norm_*` поля и флаги;
- **не** возвращать `category_id` на Sem стадии;
- включать Norm‑результаты и флаги в `semantic_attrs` и `semantic_raw_json`.
