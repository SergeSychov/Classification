# mnn_non_drug_override_policy_v1 — offline BAS/Other override proposals

**Status:** proposed / offline only. Not a DB update. No product_kind/product_type/attr_* writes.

## 1. Preflight

- inputs: `['redesign/artifacts/mnn_identity_enrichment_pass_review_non_drug_null_mnn_v1.csv', 'redesign/artifacts/mnn_identity_enrichment_pass_review_metrics_v1.md', 'redesign/artifacts/mnn_identity_enrichment_pass_results.csv', 'redesign/artifacts/mnn_identity_enrichment_pass_human_review_v2 - mnn_identity_enrichment_pass_human_review_v2.csv', 'redesign/artifacts/mnn_identity_enrichment_pass_research_context.csv']`
- non_drug candidates: **18** (distinct product_id=18)
- human-review v2 rows: 100
- results rows: 184; research_context: 104
- **No new evidence was collected** (no SearXNG / LLM / webhook).

## 2. Candidate distribution

- proposed_product_kind: `{'null': 5, 'bas': 12, 'other': 1}`
- decisions: `{'conflict_requires_review': 1, 'propose_bas_override': 12, 'propose_other_override': 1, 'insufficient_evidence': 3, 'keep_current_no_override': 1}`
- evidence grades: `{'D': 3, 'A': 7, 'B': 6, 'C': 2}`
- identity grades: `{'C': 4, 'A': 4, 'B': 9, 'unknown': 1}`
- auto_eligible: `{'false': 11, 'true': 7}`
- review_required: `{'true': 11, 'false': 7}`
- queue_action: `{'retain_in_human_queue': 5, 'remove_from_future_mnn_human_queue': 7, 'send_to_kind_review_queue': 6}`
- observed_category: `{'Drug': 2, 'BAS': 13, 'Other': 2, 'none': 1}`

## 3. Queue reduction estimate (this 18-row subset only)

- current candidates: **18**
- auto-removable (future MNN human queue): **7**
- kind-review queue: **6**
- retained in MNN human queue: **5**
- excluded special case **19198** (Зверобоя): not counted toward BAS/Other reduction

## 4. Decision examples

### Auto-eligible

- **21387** — ГЕПАВИЗИМ ФОСФОЛИПИДЫ+L-ОРИНИТИН+КУРКУМИН КАПС. ПО 495МГ №30 | ВТФ ООО | ВТФ ООО
  category=BAS; proposal=bas; E=A/I=A; AUTO: Category=BAS, evidence=A/ok + BAS/Other + urls + strong identity + should_be_empty; identity=A/name+secondary match tokens=['ГЕПАВИЗИМ', 'ФОСФОЛИПИДЫ+L-ОРИНИТИН+КУРКУМИН', '4
- **18830** — ИЗЖОГАНЕТ АНТАЦИДНЫЙ КОМПЛЕКС СО ВКУСОМ МЯТЫ ТАБЛ. 600МГ №40 | ГРИН САЙД ООО | Г
  category=BAS; proposal=bas; E=A/I=B; AUTO: Category=BAS, evidence=A/ok + BAS/Other + urls + strong identity + should_be_empty; identity=B/name+one secondary tokens=['ИЗЖОГАНЕТ', 'АНТАЦИДНЫЙ', 'КОМПЛЕКС', 'ВКУСОМ']; la
- **9197** — ПОМОГУША СИРОП ДЕТСКИЙ ДЛЯ ДЕТЕЙ С 3-Х ЛЕТ ПРОТИВОПРОСТУДНЫЙ 100МЛ | ЮГ ООО | ЮГ
  category=Other; proposal=other; E=A/I=B; AUTO: Category=Other, evidence=A/ok + BAS/Other + urls + strong identity + should_be_empty; identity=B/name+one secondary tokens=['ПОМОГУША', 'ДЕТСКИЙ', 'ДЕТЕЙ', 'ПРОТИВОПРОСТУДНЫЙ
- **18179** — КАЛЬЦИЯ ГЛЮКОНАТ ЭКО ТАБЛ. ПО 500МГ №10 | ЭКОТЕКС ООО | ЭКОТЕКС ООО
  category=BAS; proposal=bas; E=A/I=B; AUTO: Category=BAS, evidence=A/ok + BAS/Other + urls + strong identity + should_be_empty; identity=B/name+one secondary tokens=['КАЛЬЦИЯ', 'ГЛЮКОНАТ', 'ЭКО']; label_mnn=should_be_e
- **249** — ОСТЕОМЕД таб. N60 Парафарм | Парафарм ООО | Парафарм ООО | N60
  category=BAS; proposal=bas; E=A/I=B; AUTO: Category=BAS, evidence=A/ok + BAS/Other + urls + strong identity + should_be_empty; identity=B/name+one secondary tokens=['ОСТЕОМЕД']; label_mnn=should_be_empty; non-drug cla

### Review-required (kind queue)

- **5322** — ТАВОЛГА ВЯЗОЛИСТНАЯ (ЛАБАЗНИК) ТРАВА Ф/П 1,5Г №20 ХЕРБЕС | ХЕРБЕС ООО | ХЕРБЕС О
  category=BAS; proposal=bas; E=B/I=B; REVIEW-STRONG: Category=BAS; herbal/phytoproduct ambiguity; evidence_grade=B; identity=B/strong name tokens only=['ТАВОЛГА', 'ВЯЗОЛИСТНАЯ', 'ЛАБАЗНИК']; evidence=ok + BAS/Other + u
- **75** — САМБУКУС БУЗИНА ИММУНИТЕТ таб. массой 700мг N30 Грин сайд ООО | Грин Сайд ООО |
  category=BAS; proposal=bas; E=B/I=A; REVIEW-STRONG: Category=BAS; herbal/phytoproduct ambiguity; evidence_grade=B; identity=A/name+secondary match tokens=['САМБУКУС', 'БУЗИНА', 'ИММУНИТЕТ', 'ГРИН']; evidence=ok + BAS/
- **3763** — ФАРМГРУПП НАСТОЙКА 5 ТРАВ УСПОКОИТЕЛЬНАЯ ФЛ. 250МЛ | ФАРМГРУПП ООО | ФАРМГРУПП О
  category=BAS; proposal=bas; E=B/I=A; REVIEW-STRONG: Category=BAS; herbal/phytoproduct ambiguity; evidence_grade=B; identity=A/name+secondary match tokens=['ФАРМГРУПП', 'ТРАВ', 'УСПОКОИТЕЛЬНАЯ', '250МЛ']; evidence=ok +
- **8201** — РЕПЕШОК ОБЫКНОВЕННЫЙ ТРАВА 50Г ЭВАЛАР | ЭВАЛАР ЗАО | ЭВАЛАР ЗАО
  category=BAS; proposal=bas; E=B/I=B; REVIEW-STRONG: Category=BAS; herbal/phytoproduct ambiguity; evidence_grade=B; identity=B/strong name tokens only=['РЕПЕШОК', 'ОБЫКНОВЕННЫЙ']; evidence=ok + BAS/Other + urls + adequ
- **22548** — ВЕЧЕРНЕЕ ВАЛЕРИАНА+МЯТА+МЕЛИССА ДРАЖЕ №50 ПАРАФАРМ | ПАРАФАРМ ООО | ПАРАФАРМ ООО
  category=BAS; proposal=bas; E=B/I=B; REVIEW-STRONG: Category=BAS; herbal/phytoproduct ambiguity; evidence_grade=B; identity=B/strong name tokens only=['ВЕЧЕРНЕЕ', 'ВАЛЕРИАНА+МЯТА+МЕЛИССА']; evidence=ok + BAS/Other + u

### Special case: Зверобоя трава Фитофарм (19198)

- text: ЗВЕРОБОЯ ТРАВА 50Г ФИТОФАРМ | ФИТОФАРМ ООО | ФИТОФАРМ ООО
- observed category: Drug
- decision: `keep_current_no_override`
- queue: `retain_in_human_queue`
- mnn action: `manual_mnn_review`
- reason: SPECIAL: Drug + ok_partial + empty MNN; human label_mnn=incorrect (Drug/OTC/взрослый). Not BAS/Other. identity=partial name tokens=['ЗВЕРОБОЯ']

## 5. Risks / limitations

- Review sample is not a random population estimate.
- Offline proposal is **not** a DB/`attr_*`/`product_kind` update.
- No new research was collected.
- Herbal/phytoproduct ambiguity can look like BAS or Drug.
- Automatic queue removal requires future explicit policy approval.
- Category BAS/Other can be wrong if identity is weak (see retained/conflicts).

## 6. Explicit non-actions

- no DB writes / no classification_runs
- no LLM / SearXNG / webhook
- no prod / Sem / snapshot / attr_* / product_type / product_kind changes
- no workflow changes / no git commit-push
- inputs unmodified
