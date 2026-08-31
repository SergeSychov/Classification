# MNN tool-search bakeoff summary

- prompt_version: `mnn_tool_search_v1`
- wall_sec: **5405**
- serper_calls_total: **1222**

## Per model

| model | n | found | coverage | search_used_rate | p50 ms | p95 ms | total_tokens | vs_catalog exact+norm | vs_polza agree |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen3.8-max | 224 | 50 | 0.2232 | 1.0 | 40446.0 | 131344.7 | 403099 | 36 | 0.1944 |
| qwen3.7-max | 224 | 125 | 0.558 | 1.0 | 47547.5 | 82206.6 | 436479 | 92 | 0.4792 |
| qwen3.7-flash | 224 | 107 | 0.4777 | 1.0 | 38646.0 | 69091.2 | 640354 | 45 | 0.2847 |
| deepseek-v4-pro | 224 | 129 | 0.5759 | 1.0 | 5857.0 | 64340.2 | 196055 | 91 | 0.4583 |

## DeepSeek balance

- before: `{"is_available": true, "balance_infos": [{"currency": "USD", "total_balance": "6.75", "granted_balance": "0.00", "topped_up_balance": "6.75"}]}`
- after: `{"error": "<urlopen error Tunnel connection failed: 403 Forbidden>"}`

## Notes

- Qwen cost: sum `usage` tokens in per-model CSV / summary `tokens` (no DashScope balance API on API key).
- Search confirmation: `search_used=1` when model issued web_search tool call.
- Input prompt uses only `normalized_text` (no brand/form/dosage).
