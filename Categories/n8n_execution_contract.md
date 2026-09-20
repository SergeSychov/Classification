# n8n execution contract — sequential chunks, one live run

Canon for **all** n8n executions in this project: Stage 2, hierarchy-dev, ShortList, enrichment, bakeoff, ops bots.

Related: `Categories/stage2_workflow_contract.md`, `scripts/n8n_executions.py`.

---

## Why

LLM stages use Merge `combineByPosition` and run **all items in the batch in parallel**. A single N=100 hang (Sem0/Sem1) and stacked cron executions (`agent-balance-bot` every minute) drove CPU to ~200% and put the host into standby.

---

## Rules

1. **One live execution per workflow.** Do not POST a webhook / `n8n execute` / activate a second run while the same workflow has status `running`, `waiting`, or `new`.
2. **Chunk size ≤ 10** for any path that fans items into LangChain Agent + Merge LLM (hierarchy Sem0/Sem1, Stage 2 P1/2A/2B/Judge). Default smoke size remains **5**.
3. **Next chunk only after the previous execution is terminal** (`success` / `error` / `crashed` / `canceled`). No overlapping chunks, no fire-and-forget waves.
4. **Stop zombies.** An execution older than **30 minutes** still in `running`/`waiting` must be stopped via `POST /api/v1/executions/{id}/stop` before starting a new one. Helpers: `scripts/n8n_executions.py`.
5. **No polling crons that do HTTP/LLM work every minute.** Schedule real work at the needed wall-clock time (or on an explicit command). Minute-tick “check if it’s 09:00” is forbidden — it stacks executions when Merge/HTTP hang.
6. **Do not enable error-workflow autoresume** (`drug-mnn-enrichment-autoresume` pattern) while the n8n task runner is unhealthy. Autoresume after `runner became unresponsive` multiplies load.
7. **Do not list executions with `status=new`** on this n8n — the filter is ignored and returns the last 50 runs of any status. Do not call `/executions?includeData=true` from inside a workflow. Watchdogs: `status=running` only, or just `executionTimeout`.
8. **LLM provider healthcheck before every Stage 2 chunk.** Each Stage 2 / `run_workflow.py` execution must probe providers **once at chunk start** (sub-workflow `classification-llm-healthcheck`) before Load batch / LLM fan-out. Primary = DeepSeek (LangChain Agent path, same as P1/2A/2B). On fail → failover to **Qwen via Polza** (same credential/model family as Judge). Output fields: `llm_provider` ∈ {`deepseek`,`qwen`}, `ok` bool, `error`. If both fail → abort the chunk (do not start P1). Routing of P1/2A/2B Agents follows `llm_provider` for that chunk. Do not skip the probe between sequential chunks. Details: `Categories/stage2_workflow_contract.md` § LLM provider healthcheck, `Categories/llm_provider_healthcheck.md`.

---

## Runners

| Script | Must |
|--------|------|
| `scripts/run_workflow.py` | clamp `batch_size`, wait until idle, then `--wait` |
| `scripts/run_hierarchy_workflow.py` | same |
| `scripts/wave100_chunked_run.py` | sequential chunks; stop leftovers; wait per chunk |
| `scripts/run_batch_1000_resilient.py` | `CHUNK=5`; wait each ShortList/Stage2 exec |
| `n8n execute` inside the live container | Public API has no `/run`. CLI must use `N8N_RUNNERS_BROKER_PORT` ≠ 5679 (e.g. 15679); otherwise the task broker collides with the running instance. CLI ignores pinData. |

Webhook body `batch_size` in workflows is still a safety cap; runners must not rely on it alone.

---

## Hierarchy / Stage 2 waves

Use the chunked runner, not a single `batch_size=100`/`500`:

```bash
python3 scripts/wave100_chunked_run.py \
  --ids-file redesign/artifacts/sem_wave100_allowlist.json \
  --chunk-size 10 \
  --seed <seed> \
  --out redesign/artifacts/sem_wave100_report.csv
```

Single-chunk smoke:

```bash
python3 scripts/run_hierarchy_workflow.py --batch-size 5 --wait
python3 scripts/run_workflow.py --batch-size 5 --wait
```
