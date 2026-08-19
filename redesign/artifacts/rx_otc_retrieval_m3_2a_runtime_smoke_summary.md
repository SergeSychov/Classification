# M3.2a RX/OTC retrieval n8n runtime smoke

**Workflow:** `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`)
**active:** `False`
**workflow_version:** `rx_otc_retrieval_dev_v1`
**mode:** `m3_2a_stub`
**execute:** `n8n execute --id` with `N8N_RUNNERS_BROKER_PORT=15679`. CLI ignores pinData; each case injected into `In — Normalize Input` then git export restored. Workflow stayed inactive.

## Results

| Case | ok | execution_id | key fields |
|------|----|--------------|------------|
| A | True | 42679 | m2=pass outcome=unresolved error=E_SOURCE_NOT_FOUND |
| B | True | 42680 | m2=exclude outcome=not_applicable error=E_M2_NON_DRUG |
| C | True | 42681 | m2=None outcome=rejected error=E_INPUT_IDENTITY |

A issues: []
B issues: []
C issues: []

Production webhook while inactive: HTTP 404 (expected 404).

## Isolation

- prod Stage 2 unchanged: True (`2026-07-19T19:50:02.799Z`)
- hierarchy-dev unchanged: True (`2026-08-13T07:48:03.215Z`)
- no DB run_id (null / none_no_db_in_m3_2a)
- no attr/snapshot/product_kind writes
- workflow left **inactive**
- no git commit/push
