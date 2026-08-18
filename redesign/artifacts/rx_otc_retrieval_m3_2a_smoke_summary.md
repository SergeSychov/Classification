# M3.2a RX/OTC retrieval skeleton smoke

**Workflow:** `rx-otc-product-retrieval-dev` (`UqssZ24Jr7Qk9ef4`)
**active:** `false`
**workflow_version:** `rx_otc_retrieval_dev_v1`
**mode:** `m3_2a_stub`

## Forbidden-node check

ok=True
node_count=32
no HTTP / no LLM / no Postgres / no external connectors.

## How smokes were run

n8n 2.27 Public API has no `POST /workflows/{id}/run`.
CLI `n8n execute` inside the running container hits task-broker port 5679 already in use.
Production webhook while inactive: **HTTP 404** (expected; workflow stays inactive).

Smokes A/B/C replayed the **exported** workflow Code/IF chain (`workflows/rx-otc-product-retrieval-dev.json`) with mocked `$input` — same jsCode as on n8n.

## Results

| Case | ok | key fields |
|------|----|------------|
| A eligible 3065 | True | m2=pass outcome=unresolved brand=ФЛУКОНАЗОЛ-OBL form=капсулы strength=150 мг pack=N4 q1/q2/q3=3/3/2 executed=0 |
| B exclude 9197 | True | m2=exclude outcome=not_applicable error=E_M2_NON_DRUG q_ran={'q1': False, 'q2': False, 'q3': False} |
| C invalid 999999 | True | input_validation_passed=False outcome=rejected error=E_INPUT_IDENTITY q_ran={'q1': False, 'q2': False, 'q3': False} |

## Isolation

- prod Stage 2 unchanged (`BaBjEPi78taRj2G5` updatedAt 2026-07-19T19:50:02.799Z)
- hierarchy-dev unchanged (`o8sugljHYuUs7IEC` updatedAt 2026-08-13T07:48:03.215Z)
- no DB writes / no `classification_runs` / `run_id=null`
- no attr / snapshot / product_kind changes
- no git commit/push
- workflow left **inactive**
