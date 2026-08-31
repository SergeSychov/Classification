# M5.1 — Norm v4.1 offline remediation (design)

**Status:** DONE (offline / audit-only). Not accepted for hierarchy-dev or n8n rollout.  
**Date:** 2026-08-20  
**Policy:** `norm_v4_1_offline_pack_and_retrieval_remediation`

M5.0 (`norm_v4_experiment_m5_0`) remains the historical baseline. This task does **not** overwrite M5.0 scripts, artifacts, or v4 fields.

Human-reviewed M5.0 sample is a required input: `redesign/artifacts/mnn_norm_v4_experiment_human_reviewed.csv`. Blank labels are not treated as `yes`.

---

## 1. Why M5.0 is not rolled out

1. `enrichment_query_text_v4` omits manufacturer. Several drug SKUs are not distinguishable for retrieval. Manufacturer is already in `enrichment_query_disambiguator_v4`; retrieval needs a **composite** of both.
2. `pack_v4` mixes consumer-unit count (`N5`), container (`ампула`/`флакон`/`туба`), and unit amount (`5 мл` / `15 г`). Container and amount were dropped from several queries.
3. Critical role error: manufacturer prefix in the product head was assigned as brand. Canonical case: `product_id=3763` (`Фармгрупп` vs remainder `5 трав успокоительная`).

---

## 2. Spec example IDs vs real product_ids

Section 4.2 examples numbered 1–4 and 6–9 do **not** exist in the Wave-500 N=100 universe (except the listed `3763`). Regression uses the real IDs:

| Spec example | Real `product_id` | Product |
|--------------|-------------------|---------|
| 1 Гепарин | **54** | `5000 ЕД/мл` + `5 мл` + `N5`; **no** `амп.` in source → container `unknown` |
| 2 Элькар | **844** | `фл. 25 мл` → флакон, 25 мл, implicit N1 |
| 3 Экзоролфинлак | **1053** | `фл. 2,5 мл` → флакон, 2.5 мл |
| 4 Хилак Форте | **2348** | `фл. 100 мл`; no strength invented |
| 3763 Фармгрупп | **3763** | prefix recovery; brand ≠ Фармгрупп |
| 6 Транексамовая кислота | **4487** | `амп. 5 мл №10` |
| 7 Термикон спрей | **4922** | `фл. 30 г` |
| 8 Термикон крем | **4924** | `туба 15 г` |
| 9 Римасопт ВМ | **8055** | `фл. 5 мл №1` + multi-component strength |

`product_id=8` (Хайлефлокс) is included in the M5.1 human-review sample because 9.4 listed it; it is **not** spec example 8.

Acceptance notes that copy-pasted the wrong volume (844/1053/4924) are scored against **actual** `normalized_text`, not the note.

---

## 3. Parallel v4.1 fields only

M5.0 columns are copied unchanged, including `normalized_text` and all `*_v4` projections.

New policy adds:

- Retrieval: `enrichment_query_text_v4_1` (no manufacturer) + `enrichment_query_disambiguator_v4_1` + `enrichment_retrieval_text_v4_1` = query + `, ` + disambiguator when disambiguator is non-empty.
- Pack structure: `container_type_raw/v4_1`, `unit_content_amount_v4_1`, `pack_unit_count_v4_1`, `pack_structure_raw/v4_1`, `pack_parse_status_v4_1`.
- Name-role: `product_name_raw_v4_1`, `manufacturer_prefix_raw_v4_1`, `product_name_remainder_raw_v4_1`, recovery status/warnings.
- Form vocabulary follow-up: `гранулы`, `драже`, `ополаскиватель` are canonical when source supports them. Do **not** map гранулы→порошок or драже→таблетки.

`pack_v4` is not the sole truth for v4.1. Strength stays concentration (`5000 ЕД/мл`, `%`, `мг/мл`); unit amount is per-container volume/mass.

Container `фл` is matched only as `фл.` / `флакон` / `фл-кап` (not the substring inside `РИТОФЛЕКС`). `картридж` maps to canonical `контейнер` with a warning; query keeps the source marker `картридж`. Ampoule is **not** inferred for Гепарин (54): source has no `амп.` marker.

Implicit `N1` only when a single explicit container is present and no `N/№/No` count exists (`implicit_single_unit_count`).

---

## 4. Review findings as acceptance input

Imported M5.0 labels are stored unmutated (`label_norm_v4_*` / `m5_0_label_*`) plus machine-readable `review_findings_v4_1`.

Every M5.0 `no`/`uncertain` gets `m5_1_resolution_status`:

| Status | Meaning |
|--------|---------|
| resolved | v4.1 output satisfies the specific labeled issue (against actual source) |
| partially_resolved | part of the issue fixed; remainder blocked by source evidence |
| still_open | labeled defect not demonstrated in v4.1 output |
| not_applicable | no M5.0 defect (yes/yes, or unlabeled / not in the 50-sample) |

A new field existing is not enough to claim resolved.

---

## 5. What this remediation does not do

- Web / SearXNG / HTTP / browser / LLM
- n8n edit, import, execute, deploy
- Change `Norm — Normalize Product` or `normalized_text`
- PostgreSQL / `classification_runs` / `product_classification*` / `attr_*` / semantic_attrs
- Snapshot / product_kind / product_type / prod / Sem
- M3 RX/OTC or M4 Age artifacts
- Overwrite any M5.0 file
- git commit / push

```text
offline reviewed remediation only;
no web/LLM/DB/n8n;
no attr/snapshot/product_kind/prod/Sem changes;
no commit/push.
```

---

## 6. Next after M5.1 human review

1. Labels on `mnn_norm_v4_1_remediation_human_review.csv` (`label_norm_v4_1_*`).
2. Inspect exceptions (Гепарин container-absent, herbal 50 г / mouthwash 250 мл partial, Farmgrupp prefix flag).
3. If accepted later: **parallel** v4.1 fields in hierarchy-dev log-only — see `m5_norm_v4_1_future_n8n_plan.md`.
4. No production overwrite until explicit approval. M5.0 remains not-accepted for live wiring.
