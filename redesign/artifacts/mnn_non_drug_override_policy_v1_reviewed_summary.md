# mnn_non_drug_override_policy_v1_reviewed — human-reviewed freeze (M2.1)

**Status:** immutable offline freeze. **Not applied** to DB / snapshot / `attr_*` / `product_kind`.

## Preflight

- Labeled input: `redesign/artifacts/mnn_non_drug_override_policy_v1_human_review - mnn_non_drug_override_policy_v1_human_review.csv`
- sha256: `01452fa36d7b80de1cd5ae853400db924c6a96f2d55001edb2f82456aac70bc9`
- rows: **18** / distinct product_id: **18**
- approved labels checked: **13** (human non-drug confirmation on policy proposals)
- raw label vocab: `{'approve_bas': 3, 'BAS': 13, 'approve_drug': 1, '': 1}`

## Summary

| Metric | Count |
|--------|------:|
| applied **bas** | **12** |
| applied **other** | **1** |
| without applied proposal | **5** |
| excluded from future MNN queue | **13** |
| product_kind / attr_* / snapshot changed | **0 (none)** |

## Applied (13) — remove_from_future_mnn_human_queue

- `21387` → **bas** — ГЕПАВИЗИМ ФОСФОЛИПИДЫ+L-ОРИНИТИН+КУРКУМИН КАПС. ПО 495МГ №30 | ВТФ ООО | ВТФ ООО
- `18830` → **bas** — ИЗЖОГАНЕТ АНТАЦИДНЫЙ КОМПЛЕКС СО ВКУСОМ МЯТЫ ТАБЛ. 600МГ №40 | ГРИН САЙД ООО | Г
- `5322` → **bas** — ТАВОЛГА ВЯЗОЛИСТНАЯ (ЛАБАЗНИК) ТРАВА Ф/П 1,5Г №20 ХЕРБЕС | ХЕРБЕС ООО | ХЕРБЕС О
- `9197` → **other** — ПОМОГУША СИРОП ДЕТСКИЙ ДЛЯ ДЕТЕЙ С 3-Х ЛЕТ ПРОТИВОПРОСТУДНЫЙ 100МЛ | ЮГ ООО | ЮГ
- `18179` → **bas** — КАЛЬЦИЯ ГЛЮКОНАТ ЭКО ТАБЛ. ПО 500МГ №10 | ЭКОТЕКС ООО | ЭКОТЕКС ООО
- `75` → **bas** — САМБУКУС БУЗИНА ИММУНИТЕТ таб. массой 700мг N30 Грин сайд ООО | Грин Сайд ООО |
- `249` → **bas** — ОСТЕОМЕД таб. N60 Парафарм | Парафарм ООО | Парафарм ООО | N60
- `56` → **bas** — РИТОФЛЕКС МСМ таб. N60 Фармацевтическая Фабрика ООО | Фармацевтическая фабрика О
- `3763` → **bas** — ФАРМГРУПП НАСТОЙКА 5 ТРАВ УСПОКОИТЕЛЬНАЯ ФЛ. 250МЛ | ФАРМГРУПП ООО | ФАРМГРУПП О
- `8201` → **bas** — РЕПЕШОК ОБЫКНОВЕННЫЙ ТРАВА 50Г ЭВАЛАР | ЭВАЛАР ЗАО | ЭВАЛАР ЗАО
- `22548` → **bas** — ВЕЧЕРНЕЕ ВАЛЕРИАНА+МЯТА+МЕЛИССА ДРАЖЕ №50 ПАРАФАРМ | ПАРАФАРМ ООО | ПАРАФАРМ ООО
- `23695` → **bas** — БИОРИТМ АНТИСТРЕСС 24 ДЕНЬ/НОЧЬ ТАБЛ. П/О №32 | ЭВАЛАР ЗАО | ЭВАЛАР ЗАО
- `26319` → **bas** — АЛТАЙ ФИТОЧАЙ КИПРЕЯ ТРАВА Ф/П 1,5Г №20 | АЛТАЙСКИЙ КЕДР ООО | АЛТАЙСКИЙ КЕДР ОО

## Without applied proposal (5) — retain_in_human_queue

- `72` — status=`not_applied_no_policy_proposal` label=`approve_bas` — ФАРИНГАЛ таб. 650мг N10 Салута-М | Салута-М ООО | Салута-М ООО | N10
- `11272` — status=`not_applied_no_policy_proposal` label=`approve_bas` — НООТРОП КАПС. №48 | ВИС ООО | ВИС ООО
- `19198` — status=`not_applied_keep_drug` label=`approve_drug` — ЗВЕРОБОЯ ТРАВА 50Г ФИТОФАРМ | ФИТОФАРМ ООО | ФИТОФАРМ ООО
- `45` — status=`not_applied_no_policy_proposal` label=`approve_bas` — АКВИОН КОЖА ВОЛОСЫ НОГТИ таб. N60 ВТФ ООО | ВТФ ООО | ВТФ ООО | N60
- `9941` — status=`not_applied_unlabeled_or_insufficient` label=`∅` — ПАРОДОНТОЦИД ОПОЛАСКИВАТЕЛЬ ДЛЯ ПОЛОСТИ РТА 250МЛ | МОСКОВСКАЯ ФФ | МОСКОВСКАЯ Ф

## Field semantics (final_*)

- `text` — copy of `normalized_text`
- `final_proposed_product_kind` — `bas` / `other` / empty
- `final_override_source` — why freeze decision was made
- `final_override_status` — `applied` | `not_applied_*`
- `final_queue_action` — `remove_from_future_mnn_human_queue` | `retain_in_human_queue`

Rule: for applied rows, **final kind follows policy `proposed_product_kind`** (so `9197` stays `other` even if label cell says `BAS` as non-drug confirmation).

## Immutable artifact

- `redesign/artifacts/mnn_non_drug_override_policy_v1_reviewed.csv`
- sha256: `403b93b6b984a964e78eb90edcfdf03e73ad473e3b1ba92016abf5c549270f46`

## Explicit non-actions

- no DB writes / no classification_runs
- no `product_kind` / `product_type` / `attr_*` / snapshot updates
- no Sem / workflow / prod changes
- implementation contract prepared separately and **not applied**
