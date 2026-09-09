# M5.1 — Human review Norm v4.1: итог и verdict

Дата: 2026-09-09
Артефакт: `mnn_norm_v4_1_remediation_human_review` (N=50, offline, snapshot-off)

## 1. Метрики разметки

```text
reviewed_count = 50

identity_preserved:      yes 50 / no 0 / unclear 0
query_appropriate:       yes 50 / no 0 / unclear 0
manufacturer_correct:    yes 44 / no 0 / n_a 0 / unclear 6
pack_structure_correct:  yes 50 / no 0 / n_a 0 / unclear 0
product_name_role_correct: yes 50 / no 0 / n_a 0 / unclear 0

critical_fail_count = 0
minor_issue_count   = 0
unclear_count       = 6 (только manufacturer alias/role)
systemic_defect_types = none
regression_count_vs_m5_0 = 0
```

critical_error_rate = 0 / 50 = **0.0%**

Примечание: в исходной разметке в строке 45 (`ДЕКСАМЕТАЗОН-КРКА`) в полях identity/query стоит опечатка `yhes`; трактуется как `yes`, требует правки в источнике.

## 2. Покрытие стратов

| review_stratum_v4_1 | N | critical_fail |
|---|---:|---:|
| ordinary_successfully_remediated | 22 | 0 |
| multi_component_strength_pack | 6 | 0 |
| single_container_implicit_n1 | 6 | 0 |
| m50_label_uncertain | 5 | 0 |
| m50_label_no | 3 | 0 |
| dosage_form_vocab_policy | 3 | 0 |
| retained_multi_entity_manufacturer | 2 | 0 |
| pack_container_amount_count | 2 | 0 |
| manufacturer_prefix_recovery | 1 | 0 |

Все 4 строки с `m5_0_label_norm_v4_identity_preserved = no` получили в v4.1 `yes` — известные дефекты M5.0 подтверждённо закрыты независимым ревью.

## 3. Открытые наблюдения (не дефекты v4.1)

1. **6 строк `manufacturer_correct = unclear`** — иностранные производители в русской транслитерации:
   `Тева фармасьютикал воркс прайвэт Лимитед Компани`, `Тева Фармацевтические Предприятия Лтд.`,
   `ТЕВА ЧЕШСКИЕ ПРЕДПРИЯТИЯ С.Р.О.`, `УОТСОН ФАРМА ПРАЙВЭТ ЛИМИТЕД`, `МЕРКЛЕ ГМБХ`,
   `Уорлд медицин илач сан. ве тидж. Аш`.
   Во всех случаях производитель корректно отделён от товарной сущности; проблема относится к
   каноникализации юрлиц (`raw → legal entity → corporate group → entity role`), а не к нормализации.
   Выносится в отдельный трек **Manufacturer Entity Resolution / Alias Dictionary v1**.

2. **`product_id=54`, Гепарин** — `m5_1_resolution_status = partially_resolved`.
   В source отсутствует маркер «амп.», container намеренно не достроен. Классифицируется как
   `source_data_issue`, не как дефект v4.1.

## 4. Verdict

```text
verdict = accept_for_controlled_integration
```

Основание: нет критичных дефектов, нет регрессий относительно M5.0, нет повторяемого системного
типа ошибки; identity и query устойчиво корректны на всех девяти стратах.

Ограничения verdict:
- разрешена только подготовка отдельного design/apply plan для изолированного подключения в `classification-stage2-hierarchy-dev`;
- **не** разрешено: изменение Norm-ноды production `classification-stage2-dev`, перезапись `normalized_text`,
  запись в `attr_*`, snapshot или live routing;
- alias-каноникализация производителей вне scope Norm v4.1.

## 5. Следующие шаги

**P0 — Sem Wave-100 human rubric** (главный gate hierarchy-трека).
Разметить 100 строк по `mnn`, `dosage_form`, `administration_route`; посчитать `critical_error_rate`;
gate `< 15%`; зафиксировать `PASS` / `HOLD`. До этого B4 Direction/Need не открывать.

**P1 — гигиена артефакта M5.1.**
Исправить `yhes → yes` (строка 45); перевести 6 строк `manufacturer unclear` в `yes` с пометкой
`alias canonicalization out of scope`; сохранить как `mnn_norm_v4_1_remediation_reviewed_v1`,
исходный лист не перезаписывать.

**P2 — design note «Norm v4.1 controlled integration»** (не реализация).
Scope: только hierarchy-dev; parallel-поля `*_v4_1`; allowlist 10–15 товаров; snapshot-off;
критерии сравнения v4.1 vs текущий Norm; rollback к `WHERE false`.

**P3 — Manufacturer Entity Resolution / Alias Dictionary v1** (offline, параллельно).
Таблица `manufacturer_aliases`: `manufacturer_raw`, `legal_entity_canonical`, `legal_entity_canonical_en`,
`manufacturer_group_canonical`, `country_code`, `entity_role`, `match_method`, `match_confidence`,
`evidence_source`, `is_verified`. Заполнение только verified-парами; LLM/fuzzy — только `candidate`.

**Отложено без изменений:** RX/OTC M3.2c и Phase A, Age в routing, M2 queue exclusion для 13 ID,
Telegram HITL, любые изменения production Stage 2.
