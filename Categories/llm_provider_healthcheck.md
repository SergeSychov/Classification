# LLM provider healthcheck

Canon companion: `Categories/n8n_execution_contract.md` (rule 8), `Categories/stage2_workflow_contract.md` §8.

## Workflow

| | |
|--|--|
| Name | `classification-llm-healthcheck` |
| Id file | `workflows/classification-llm-healthcheck.id` |
| Triggers | Execute Workflow (from Stage 2), webhook `POST /webhook/classification-llm-healthcheck` |

## Behaviour

1. Minimal DeepSeek LangChain Agent probe (`deepseek-v4-flash`, credential `DeepSeek account`) — **same path as Stage 2 P1/2A/2B**, not HTTP-only.
2. On fail (403 geo / auth / empty) → minimal Qwen Agent via Polza (`qwen/qwen3.5-flash-02-23@reasoning_effort=none`, `Polza account`).
3. Output item:

```json
{
  "ok": true,
  "llm_provider": "deepseek|qwen",
  "model": "...",
  "error": null,
  "deepseek_ok": false,
  "qwen_ok": true,
  "probed_at": "ISO-8601"
}
```

If both fail: `ok=false`, `llm_provider=none`, `error` with both reasons — Stage 2 `Run — Apply LLM Provider` throws and aborts the chunk.

## When

- **Once per Stage 2 execution / chunk**, after `Run — Init Constants`, before `Load — Select Batch`.
- `scripts/run_workflow.py` does not call the probe separately: Stage 2 embeds it. Still wait until Stage 2 (and nested healthcheck) are idle before the next chunk.

## Ops note (2026-09-20)

Live AdminVPS: DeepSeek **HTTP** chat/completions can return 200 while LangChain `lmChatDeepSeek` / Agent returns **403 Country, region, or territory not supported**. Healthcheck deliberately uses the Agent path so Stage 2 does not select a provider it cannot call.
