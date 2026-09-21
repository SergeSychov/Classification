# LLM failover DeepSeek → Qwen (Stage 2)

Дата: 2026-09-20  
Агент: `bc-4958a021-decb-5b4e-bf96-5ede95fcb5db`  
Связано: [`ops-readiness-stage-b.md`](ops-readiness-stage-b.md)

## Текущий статус

Recheck 2026-09-20 (`bc-27e99269…`): DeepSeek **Agent DOWN** (403 geo), HTTP **200**, healthcheck → **`llm_provider=qwen`**. Failover по-прежнему актуален. Evidence: Agent Store `internal/deepseek-recheck.md` (не в этом snapshot; см. Drive `internal-evidence` в [`google-drive-project-mirror.md`](google-drive-project-mirror.md)).

## Зачем

Live Stage 2 на AdminVPS: LangChain DeepSeek Agent → **403 geo**. HTTP DeepSeek может отвечать 200 — для Stage 2 это не достаточно.

## Решение (в контракте)

1. Субворкфлоу `classification-llm-healthcheck` — probe DeepSeek Agent, иначе Qwen/Polza.
2. Перед каждым chunk Stage 2: `Run — LLM Healthcheck` → `Run — Apply LLM Provider`.
3. P1/2A/2B: `Provider Switch` → DeepSeek Agent или `*— AI Agent Qwen` + `*— Polza`.
4. Канон: `Categories/n8n_execution_contract.md` rule 8, `Categories/llm_provider_healthcheck.md`.

## Live ids

| Workflow | Id | Active |
|----------|-----|--------|
| classification-llm-healthcheck | `AS3d7jZXevM1K3n5` | yes (publish/activate) |
| classification-stage2-dev | `BaBjEPi78taRj2G5` | yes (pushed) |

Webhook probe: `POST /webhook/classification-llm-healthcheck`

## Smoke после failover

3× `run_workflow.py --batch-size 5`: n8n exec `42907`/`42909`/`42911` → **success**, `llm_provider=qwen`. Details: Agent Store `internal/llm-failover-smoke.md` (не в snapshot).

## Пользователю (если нужно вручную)

- Убедиться, что `classification-llm-healthcheck` **Active + Published** в n8n UI.
- После merge PR — `push_workflow.py` уже применён на live в этом run; при расхождении: pull/push Stage 2.
- Hierarchy live / пороги 0.40/0.60 не трогались.
- Известный gap: Fin barrier иногда не закрывает `classification_runs` (ops-close); не блокер LLM path.
