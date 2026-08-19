# M3.2b.2 — RX/OTC evidence data contract v2

**Status:** implemented in runner + offline replay. Does not replace M3.1 design; patches the evidence serialization that M3.2b v1 mixed.
**contract_version:** `rx_otc_evidence_contract_v2`
**Date:** 2026-08-18
**Canon still:** [`m3_1_rx_otc_retriever_design.md`](m3_1_rx_otc_retriever_design.md), [`m3_1_rx_otc_retriever_contract.json`](m3_1_rx_otc_retriever_contract.json)

M3.1 already required `explicit_status_text` from captured source content. M3.2b v1 put search hits and fetched pages in one `validated_evidence[]` array (`from_fetch=false`, `http_status=null`). That made snippets look like evidence. This patch splits three layers.

Original M3.2b artifacts are **immutable**. Derived rebuild is `*_v2` only, offline.

---

## Defect

SKU 3065 policy was correct (P2 Vidal → `supported_only` / candidate `otc` / `final=null`). Serialization was not:

- 24 rows in `validated_evidence`
- 4 fetched (`from_fetch=true`, HTTP 200)
- 20 discovery hits stored as if they were evidence, sometimes with `explicit_status_text` copied from title/snippet

M3.2c cannot consume that mix.

---

## Three layers

### A. `discovery_hits`

Search/SERP only. May have `title` / `search_snippet` / `source_type_guess` / `source_tier_guess`.

Must **not** contain: `explicit_status_text`, `status_pattern`, `validation_passed`, `candidate_rx_otc_value`.
Does not enter conflict resolution. Is not evidence.

### B. `fetched_documents`

Only URLs that were actually fetched with a real HTTP status.

`from_fetch=true`. `http_status` is the transport status. Body lives in `page_text_excerpt` (and raw JSONL). Fetch failures go to `fetch_errors`, not `validated_evidence`.

### C. `validated_evidence`

Only rows derived from `fetched_documents`.

Hard invariants:

1. `from_fetch=true` on every item
2. `http_status` in 200–299 (non-2xx stays in `fetch_errors`)
3. `explicit_status_text` originates from that document’s `page_text_excerpt`, never from a discovery snippet/query/title alone
4. Discovery hits never set `candidate_rx_otc_value`
5. Discovery hits never set `validation_passed=true`
6. Only `validated_evidence` enters the conflict resolver
7. Only P1/P2 with explicit status may set `candidate_rx_otc_value`
8. P2 never sets `final_rx_otc_value`

Title/URL may be used for **identity** matching. They must not supply status text if the body has no status.

---

## Policy (unchanged)

| Tier | candidate | final |
|------|-----------|-------|
| P1 GRLS / official instruction, identity A/B, explicit status | may set | may set if no P1 conflict |
| P2 RLS/Vidal/pharmacy | may set | **never** |
| P3 generic MNN / landing / snippet | never | never |

M2-13 still excluded. Brand+form+strength query; never MNN-only while brand exists. Budgets unchanged (logical ≤8, fetch ≤4, transport retries ≤2/query).

---

## Replay

```bash
python3 scripts/run_rx_otc_m3_2b_one_item.py --replay-existing
```

- `network_disabled=true`; `http_get` raises if called
- does not overwrite original JSON/CSV/JSONL
- JSONL page excerpts are capped at 1500 chars; if a fetch-time status window was captured on a `from_fetch=true` v1 row and is missing from the truncated JSONL, it is prepended to `page_text_excerpt` as recovered **fetched body**, not as a search snippet

Live SearXNG is opt-in and currently refused (`--live` exits). Default path is replay-only.

---

## Data dictionary (v2 product JSON)

| Field | Layer | Notes |
|-------|-------|-------|
| `contract_version` | meta | `rx_otc_evidence_contract_v2` |
| `replay_mode` / `network_disabled` | meta | true for M3.2b.2 rebuild |
| `discovery_hits[]` | A | SERP metadata only |
| `fetched_documents[]` | B | HTTP 2xx pages |
| `validated_evidence[]` | C | parsed from B only |
| `fetch_errors[]` | transport | non-2xx / fetch exception |
| `candidate_rx_otc_value` | product | from C; P2 allowed |
| `final_rx_otc_value` | product | P1 only |
| `validation` | meta | invariant flags for M3.2c gates |

---

## Tests

`scripts/test_rx_otc_m3_2b_evidence_contract_v2.py` — offline A/B/C/D fixtures. Must pass before writing `*_v2` artifacts.

---

Isolation: no n8n, no PostgreSQL, no snapshot/`attr_*`/`product_kind`, no commit.
