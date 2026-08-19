# M4 — future Age validation plan (not executed)

**Status:** plan only. Do **not** run retrieval, n8n, LLM, HTTP, or DB writes in M4.0.  
**Policy version:** `age_contract_v1`  
**Canon:** [`m4_age_segment_contract_v1.md`](m4_age_segment_contract_v1.md) · [`m4_age_evidence_model_v1.json`](m4_age_evidence_model_v1.json)  
**M3 RX/OTC:** `KEEP_RX_OTC_P2_SUPPORT_ONLY` / `DO_NOT_RUN_PHASE_A_YET`. Do not start RX/OTC Phase A from this plan.

This plan proposes a later controlled Age check. It does **not** authorize execution.

---

## 0. Principle

```text
No general web retrieval until an official / product-specific Age evidence
route is designed and approved.
```

Do **not** copy the RX/OTC workflow (`rx-otc-product-retrieval-dev`) automatically.

First question for any later Age pass (still not executed here):

> Can **already stored** official/product-specific instruction evidence support
> extraction of `age_min_years` / `age_max_years` / `age_explicit_text`?

If saved titles/excerpts cannot support that extraction — as M4.0 found for
this error inventory — the next design step is an Age-specific official
instruction route, not a generic search loop and not a clone of M3 P2 pharmacy cards.

Unresolved / `unknown` is acceptable and preferable to an unsupported segment.

---

## 1. Safety gates (mandatory if a later phase is approved)

```text
- human review of every Age decision in the batch;
- no snapshot / attr_age_segment / attr_* / product_kind writes;
- unknown is a valid outcome;
- current Sem / enrichment Age is provenance, not a winner;
- M2 approved non-drug IDs are not_applicable unless testing that policy separately;
- prod Stage 2 and hierarchy-dev untouched;
- no RX/OTC research artifacts as Age evidence;
- no * * * * * HTTP/LLM cron.
```

---

## 2. Phase A — current Age error rows (proposed)

**Population:** all actual Age-error rows from

`redesign/artifacts/mnn_identity_enrichment_pass_review_age_errors_v1.csv`

M4.0 actual count = **24** unique `product_id` (expected 24; use actual if they diverge).

**Goal:** apply the Age contract + evidence model to known failures.  
**Not a correction merge.** Do not accept the current pipeline Age.

**Exclude from Phase A drug-Age precision (unless a separate not_applicable test):**

- M2 approved non-drug IDs: `56, 75, 249, 3763, 5322, 8201, 9197, 18179, 18830, 21387, 22548, 23695, 26319`
- M4.0 overlap with that list: **0**

**Human review file already prepared (labels empty):**

`redesign/artifacts/mnn_age_contract_audit_v1_human_review.csv`

Columns to fill later: `label_age_contract`, `label_age_contract_notes`.  
Do not prefill them.

---

## 3. Phase B — blind sample (proposed, not drawn)

Stratify a future blind sample by:

**`final_age_method`**

- `identity_enrichment`
- `previous_enrichment`
- `sem_baseline`

**predicted segment**

- `дети`
- `взрослые`
- `универсальный`
- `unknown`

Exclude from the Phase B draw:

```text
- M2 approved non-drug IDs, unless testing not_applicable separately;
- already labeled Age error rows (the Phase A 24) from the blind sample;
- RX/OTC research artifacts as Age evidence / as the sampling frame;
- items without usable identity text.
```

Sample size, seed, and exact counts per stratum are **not** locked here.

---

## 4. What a later retrieval may look like (design sketch only)

Only after an official Age evidence route is approved:

1. Reuse **existing** instruction URLs / selected_evidence for the SKU (no new search if a product-specific instruction URL is already stored).
2. Extract `age_explicit_text`, `age_min_years`, `age_max_years` from the fetched body — not from the LLM research_summary.
3. If no official instruction is stored, **stop** or queue for an approved P1 instruction/GRLS product-record route. Do not fall back to generic web search as Age truth.
4. P2 RLS/Vidal/pharmacy may support identity, not `final_age`.
5. Form/strength mismatch → `conflict` or `unknown`, not a silent segment.

This sketch is not a workflow spec and not permission to create n8n nodes.

---

## 5. Proposed success criteria (not accepted)

These are **candidates for later agreement**, not gates that have been passed:

| Candidate metric | Candidate bar | Status |
|---|---|---|
| Phase A: no accepted Age without P1 explicit text | 100% of accepted rows | proposed |
| Phase A: `unknown` preferred over unsupported `универсальный` / `взрослые` | qualitative | proposed |
| Phase A: conflict rows not silently resolved | 0 silent winners | proposed |
| Phase B: Age accuracy vs structured human contract labels | TBD; not copied from 71.1% baseline | proposed |
| False `универсальный` when evidence is absent | 0 on labeled P1-eligible rows | proposed |
| M2 `not_applicable` precision (separate test) | 13/13 IDs | proposed |
| No `attr_age_segment` merge | until explicit approval | locked for now |

The Wave-500 Age accuracy 59/83 is a **baseline of the current pipeline**, not a success bar for a future evidence pass.

---

## 6. Explicit non-goals

- Do not run Phase A or Phase B in M4.0
- Do not create/edit/deploy/execute an Age n8n workflow
- Do not clone `rx-otc-product-retrieval-dev`
- Do not use Brandquad / pharmacy majority vote as Age P1
- Do not enable error-workflow autoresume
- Do not git commit/push as part of this plan
