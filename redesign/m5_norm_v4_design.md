# M5.0 — Norm v4 offline text normalization design

**Status:** OFFLINE EXPERIMENT ONLY. Not applied to the live Norm node.  
**Date:** 2026-08-19  
**Policy version:** `norm_v4_experiment_m5_0`  
**Depends on:** Wave-500 identity enrichment `run_id=461`, human-review v2 (N=100), text-quality v1.  
**M3 RX/OTC:** remains `KEEP_RX_OTC_P2_SUPPORT_ONLY` / `DO_NOT_RUN_PHASE_A_YET`. Out of scope.  
**M4 Age:** remains audit-only. Out of scope.

This document is the human-readable policy. Experiment script: [`scripts/mnn_norm_v4_experiment.py`](../scripts/mnn_norm_v4_experiment.py). Future (not executed) n8n placement: [`m5_norm_v4_future_n8n_plan.md`](m5_norm_v4_future_n8n_plan.md).

---

## 0. Isolation

```text
Do not overwrite current normalized_text.
Do not modify Norm — Normalize Product.
Do not infer drug/non-drug, RX/OTC, Age, category, or MNN.
Do not write attr_*, snapshots, product_kind, PostgreSQL, or n8n.
```

| System | Relationship |
|--------|----------------|
| prod `classification-stage2-dev` | Untouched |
| `classification-stage2-hierarchy-dev` | Untouched; current B3 Norm stays `product_norm_v1` |
| `Norm — Normalize Product` | Read-only reference; v4 is a parallel experiment |
| Sem / Sem0 / Sem1 / Norm attrs | Untouched |
| `attr_*` / snapshot / `product_kind` | No writes |
| Current `normalized_text` | Copied into outputs; never replaced |

---

## 1. Problem

Human-review v2 (N=100) text-quality baseline:

- manufacturer-like repeated tail segments: **100/100**
- last two `|` segments equal: **86/100**
- duplicate pack tokens: **14/100**

Noisy `normalized_text` overloads review, enrichment query, and identity matching. Example:

```text
ЭПЛЕРЕНОН-ТЕВА 25мг N30 таб. покрытые пленочной оболочкой
Тева фармасьютикал воркс прайвэт Лимитед Компани |
Тева фармасьютикал воркс прайвэт Лимитед Компани |
Тева фармасьютикал воркс прайвэт Лимитед Компани | N30
```

---

## 2. Three projections (new fields only)

### A. `normalized_text_full_v4`

Audit-preserving display. Keeps source-case brand, descriptive form, strength, pack, one manufacturer. Deduplicates repeated manufacturer/pack segments. Never drops clinical identity silently — leftovers go to extras or a warning.

Target shape:

```text
ЭПЛЕРЕНОН-ТЕВА; таблетки, покрытые пленочной оболочкой; 25 мг; N30; производитель: …
```

### B. `product_identity_text_v4`

Compact identity-gate / source-matching text. Display-normalized brand. Canonical form. `[missing_*]` placeholders when a field is absent.

```text
brand; dosage_form; strength; pack; manufacturer
```

Brand is never replaced by MNN.

### C. `enrichment_query_text_v4`

Compact retrieval query **without** manufacturer. Manufacturer lives in `enrichment_query_disambiguator_v4` only.

```text
brand_or_product_name dosage_form strength pack
```

---

## 3. Parser rules (deterministic)

- Split on `|`. Classify tail segments as pack-only vs manufacturer.
- Deduplicate manufacturers with case-insensitive + legal-form folding. Near-duplicates (`ООО` vs bare name, punctuation, `Пвт.Лтд.` vs `пвт. Лтд`) collapse to the longest/legal variant.
- Distinct manufacturers are **not** collapsed. Flag `manufacturer_conflict` and keep all, joined with ` / `.
- Slash-separated MAH/site lists in one segment (`ДЕЛФАРМ/ХОФФМАНН/СЕНЕКСИ`) stay as one string + `manufacturer_multi_entity`.
- Pack: `N30` / `№30` / `No30` → `N30`. Cycle packs `№21+7` → `N21+7`. Flask/tube quantity is pack when no `N##` exists. Vial volume next to a concentration + `N##` stays `volume_or_fill_v4`.
- Strength: `150МГ` → `150 мг`; `0,05%` → `0.05%`; `100мг/мл` → `100 мг/мл`; combos keep ` + `. No dose-equivalence math.
- Form vocabulary: таблетки, капсулы, раствор, крем, мазь, гель, спрей, лак, капли, сироп, суспензия, порошок, суппозитории, фильтр-пакеты, трава, настойка, unknown. Uncertain raw form is preserved in `dosage_form_raw_v4` / display.
- Brand = head before the first form/strength/pack marker. Brand-line leftovers that do **not** match the pipe manufacturer stay in the brand (`Ацикловир Авексима`). Matching remnants are manufacturer, not brand.

Flagged rows are not auto-fixed.

---

## 4. What this experiment does not do

- Replace live `normalized_text`
- Change B3 `normProductText` / `product_norm_v1`
- Feed Sem, identity gate, or enrichment
- Propose RX/OTC, Age, MNN, or product_kind

---

## 5. Next after review

1. Human labels on `mnn_norm_v4_experiment_human_review.csv`
2. If accepted: parallel v4 fields in hierarchy-dev log-only (see future n8n plan)
3. No production overwrite until explicit approval
