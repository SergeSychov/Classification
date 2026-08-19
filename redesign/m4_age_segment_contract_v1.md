# M4.0 — Age segment contract v1

**Status:** DESIGN / AUDIT ONLY. Not applied. Not a routing gate.  
**Date:** 2026-08-19  
**Policy version:** `age_contract_v1`  
**Depends on:** Wave-500 identity enrichment `run_id=461`, human-review v2, M4.0 audit.  
**M3 RX/OTC:** remains `KEEP_RX_OTC_P2_SUPPORT_ONLY` / `DO_NOT_RUN_PHASE_A_YET`. Out of scope.

This document is the human-readable Age contract. Machine evidence model: [`m4_age_evidence_model_v1.json`](m4_age_evidence_model_v1.json). Future (not executed) validation: [`m4_age_future_validation_plan.md`](m4_age_future_validation_plan.md). Audit: [`artifacts/mnn_age_contract_audit_v1_summary.md`](artifacts/mnn_age_contract_audit_v1_summary.md).

---

## 0. Isolation

```text
Age is not used in routing today.
Age is not merged into attr_age_segment / snapshot.
This contract does not authorize retrieval, n8n, DB writes, or Sem merge.
Do not copy the RX/OTC workflow automatically.
```

| System | Relationship |
|--------|----------------|
| prod `classification-stage2-dev` | Untouched |
| `classification-stage2-hierarchy-dev` | Untouched |
| Sem / Sem0 / Sem1 / Norm attrs | Sem Age is baseline provenance only |
| `attr_age_segment` / `attr_*` / snapshot | No writes |
| `product_kind` / `product_type` | No writes |
| MNN identity enrichment | May be read; MNN acceptance ≠ Age acceptance |
| RX/OTC retrieval workflow | Independent; inactive; not reused here |
| M2 BAS/Other freeze (13 IDs) | Read-only `not_applicable` candidates |

---

## 1. Verified baseline (read-only)

From Wave-500 human review and M4.0 audit (actual count, not a target):

```text
MNN drugish accuracy: 82/83 = 98.8%
RX/OTC accuracy: 72/83 = 86.7%
Age accuracy: 59/83 = 71.1%
Age labeled errors: 24 (all label_age=incorrect)
Age not_labeled: 17 (non-drug / should_be_empty slice; not in this inventory)
M2 overlap in Age-error inventory: 0 / 13
```

Audit inventory: `redesign/artifacts/mnn_identity_enrichment_pass_review_age_errors_v1.csv`.

Headline from the offline audit (see summary for exact buckets):

- Skip/reuse paths often emit Age with **no saved product-specific evidence**.
- Identity enrichment often emits `универсальный` at high confidence while Sem baseline is `взрослые`.
- Saved titles/excerpts almost never contain an explicit Age phrase. GRLS URLs in this set are landings, not product records.
- Reviewer-note hints are **heuristic**, not structured ground truth.

No current Age value from the error inventory is accepted by this contract.

---

## 2. Canonical final semantic values

Only these values may be proposed as `final_age` / future `attr_age_segment` **after** a later approved evidence pass:

| Value | Meaning |
|-------|---------|
| `дети` | Product is children-only, or official text marks it as pediatric, or child-directed use is product-specific and adult use is not claimed |
| `взрослые` | Explicit adult restriction, or product-specific instruction does not allow pediatric use, or evidence clearly states adult-only |
| `универсальный` | Product-specific evidence allows both children and adults, or explicit pediatric lower threshold **plus** confirmed adult use |
| `unknown` | No product-specific Age evidence, generic MNN-only evidence, weak identity, ambiguous Age, “according to physician” without a range, or unresolved comparable-source conflict |
| `not_applicable` | Approved non-drug (M2 BAS/Other / hygiene) where Age is not needed for drug routing |
| `conflict` | Two comparable product-specific sources disagree, or form/strength/market conflict, or Sem vs retrieval conflict without a winner policy |

`unknown` is a **correct safe outcome**, not an error by itself.

---

## 3. Definition rules

### `дети`

Apply only if **one** of:

- the product is intended exclusively for a pediatric audience; **or**
- official / product-specific evidence marks the product as pediatric; **or**
- adult use is not claimed, and child-directed use is product-specific.

Do **not** assign `дети` only because pediatric dosages exist alongside adult use.

### `взрослые`

Apply only if **one** of:

- explicit restriction (“с 18 лет”, “только взрослым”); **or**
- product-specific instruction forbids / does not allow use in children; **or**
- evidence clearly states adult-only usage.

Do **not** assign `взрослые` only because Sem baseline is `взрослые`, or because children are not mentioned.

### `универсальный`

Apply only if **one** of:

- product-specific evidence allows use in children **and** adults; **or**
- explicit pediatric lower age threshold **and** adult use is confirmed; **or**
- the product is clearly applicable across child and adult populations, with the age condition captured (`age_min_years` / `age_max_years`).

Hard negatives:

```text
absence of age data != универсальный
absence of child warning != универсальный
```

### `unknown`

Apply if:

- no product-specific Age evidence;
- only generic drug / MNN evidence;
- source identity is insufficient;
- Age data are ambiguous;
- text says “according to physician” without an age range;
- a known source conflict cannot be resolved under this contract.

### `not_applicable`

Only for **approved** non-drug items:

- M2 approved BAS/Other IDs;
- hygiene / non-drug items if Age is not needed for drug routing.

Do **not** use `not_applicable` for a drug with missing Age evidence.

### `conflict`

Apply if:

- two comparable product-specific sources give incompatible Age rules;
- form / strength / market conflict;
- Sem vs retrieval/enrichment conflict **without** a winner policy.

This contract does **not** declare a current source winner.

---

## 4. Evidence-first policy (future; not executed)

Age must not be inferred from MNN success, Sem defaults, or missing child warnings.

```text
P1  official product-specific instruction OR GRLS product record
    with captured age_explicit_text and identity A/B
P2  RLS/Vidal/pharmacy product card — supporting only;
    cannot set final Age by itself
P3  search snippet / generic MNN / GRLS landing — discovery only
```

Acceptance (future, not applied now):

- product-specific or brand+form-specific identity grade A/B;
- explicit Age text captured (`age_explicit_text`);
- `age_min_years` / `age_max_years` filled when a numeric threshold exists;
- no unresolved comparable-source conflict;
- MNN acceptance does **not** auto-accept Age.

Reject / keep `unknown`:

- generic MNN / molecule page as sole source;
- Sem baseline alone;
- previous enrichment reuse without stored Age evidence;
- skip_catalog / skip_strong_input_mnn without Age evidence;
- GRLS landing URL;
- LLM research_summary without a fetched product-specific excerpt;
- identity C/D.

Winner policy is **not** locked. Until a winner policy exists, Sem vs enrichment disagreement → `conflict` or `unknown`, never silent overwrite.

---

## 5. Human notes

Free-text `label_notes` are **not** structured truth.

Allowed heuristic parse (M4.0):

```text
универсальн → универсальный
взросл     → взрослые
детск      → дети
unknown / неизвест → unknown
```

One unambiguous class → `explicit_label_note`.  
Contradictory markers → null / `ambiguous_label_note`.  
No marker → null / `not_available`.

Do not extract expected Age from medical knowledge. Do not write inferred Age to the DB.

---

## 6. Explicitly not claimed

- No Age retrieval / web / LLM / n8n workflow in M4.0
- No PostgreSQL / snapshot / `attr_*` writes
- No correction of the 24 error rows
- No RX/OTC Phase A
- No declaration that RLS/Vidal/Sem/enrichment is the Age source of truth
