# Sem attr dictionaries (Norm — Normalize Sem attrs)

Source of truth for allowed values of three Sem fields after Sem1 Post-process.
Used by `sem_normalize_attrs.js` in `classification-stage2-hierarchy-dev` only.

Edit synonyms carefully; keep canonical tokens stable for analytics.

## `administration_route` → `attr_administration_route`

| Canonical | Synonyms / signals (non-exhaustive) |
|-----------|--------------------------------------|
| `перорально` | внутрь, орально, для приема внутрь, пероральный |
| `наружно` | наружное, наружное применение, местно (кожа), наружный |
| `ингаляционно` | ингаляции, ингаляционный, через ингалятор |
| `внутримышечно` | в/м, вм, внутримышечное, i.m., im |
| `внутривенно` | в/в, вв, внутривенное, инфуз*, i.v., iv |
| `подкожно` | п/к, пк, подкожное, s.c., sc |
| `ректально` | ректальное, суппозитории (route hint) |
| `сублингвально` | под язык, сублингвальный |
| `офтальмологический` | глазн*, офтальм*, в глаза |
| `назальный` | назальн*, в нос, интраназальн* |
| `отологический` | ушн*, отолог*, в ухо |
| `инъекционное` | для инъекций, инъекционн* (без уточнения пути) |
| `не применимо` | hygiene_like / cosmetic_hygiene / not_applicable profile |

## `dosage_form` → `attr_dosage_form`

| Canonical | Synonyms / signals |
|-----------|--------------------|
| `таблетки` | табл., таб., таблетка*, п/о, п/плен/об. (без «жеват») |
| `таблетки жевательные` | жеват*, жевательн* |
| `капсулы` | капс., капсула* |
| `порошок` | пор., порош* |
| `гранулы` | гран., гранул* |
| `сироп` | сироп* |
| `суспензия` | сусп., суспенз* |
| `раствор` | р-р, раствор* (в т.ч. «раствор для …») |
| `лиофилизат` | лиоф* |
| `мазь` | мазь* |
| `крем` | крем* |
| `гель` | гель* |
| `спрей` | спрей* |
| `аэрозоль` | аэрозол* |
| `фильтр-пакеты` | ф/п, фильтр-пакет*, фиточай + Ф/П |
| `батончик` | батончик* |
| `смесь` | смесь* (смеси сухие и т.п.) |
| `пластырь` | пластыр*, plastyr |
| `капли` | капли, кап. |
| `не применимо` | hygiene / cosmetic / non-pharm form |

Forms outside the table (настойка, брикет, шприц, …) stay `null` unless policy forces `не применимо`.

## `age_segment` → `attr_age_segment`

| Canonical | Rules |
|-----------|--------|
| `взрослые` | «для взрослых», adults; default for drugs when adult-only wording |
| `дети` | детск*, для детей, возрастные диапазоны (мес/лет), infant formula ages |
| `универсальный` | вся семья / любой возраст; BAA fallback when no age signal |
| `не применимо` | pure tool/hygiene without age binding; profile not_applicable |

## `rx_otc` → `attr_rx_otc`

| Canonical | Synonyms |
|-----------|----------|
| `rx` | rx, рецептурный, рецептурное, по рецепту |
| `otc` | otc, без рецепта, безрецептурный |
| `не применимо` | non-drug (vitamin_or_baa, medical_device, cosmetic_hygiene, other) |

## Policy notes (v3 + rules patch)

- **drug:** map only from explicit raw/text signals; do not invent; Sem1 prefers mnn=null over brand-guessed INN; rx_otc ∈ {rx, otc}.
- **vitamin_or_baa:** oral forms → route often `перорально`; age null → `универсальный` if no kids/adults signal; nosology enum only; nutrient → mnn; `Комплекс` only without dominant nutrient; rx_otc=`не применимо`.
- **medical_device / hygiene_like:** route+form → `не применимо`; age from text or null/`не применимо`.
- **medical_device / clinical_like:** normalize route/form (шприц→route `инъекционное`; пластырь→`наружно`+`пластырь`); empty syringe/needle → kind medical_device.
- **cosmetic_hygiene:** route/form **applicable** when topical cue in text (крем→`крем`, наружно); not forced to `не применимо`. Gate: route/form for cosmetic (+ hygiene_like) are **non-critical**.
