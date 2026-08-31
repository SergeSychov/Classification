#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="redesign/artifacts/mnn_tool_search_bakeoff_run.log"
CHUNK="${CHUNK:-10}"
WORKERS="${WORKERS:-2}"
TIMEOUT="${TIMEOUT:-120}"

lines() { wc -l < "$1" 2>/dev/null || echo 0; }

echo "=== chunked bakeoff start $(date -u +%Y-%m-%dT%H:%M:%SZ) chunk=$CHUNK ===" >>"$LOG"

for i in $(seq 1 100); do
  before_q8=$(lines redesign/artifacts/mnn_tool_search_qwen3_8_max.csv)
  before_ds=$(lines redesign/artifacts/mnn_tool_search_deepseek_v4_pro.csv)
  echo "=== pass $i $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
  PYTHONUNBUFFERED=1 python3 scripts/mnn_tool_search_bakeoff.py \
    --workers "$WORKERS" \
    --timeout "$TIMEOUT" \
    --limit "$CHUNK" >>"$LOG" 2>&1 || echo "python exit $?" | tee -a "$LOG"
  q8=$(lines redesign/artifacts/mnn_tool_search_qwen3_8_max.csv)
  q7m=$(lines redesign/artifacts/mnn_tool_search_qwen3_7_max.csv)
  q7f=$(lines redesign/artifacts/mnn_tool_search_qwen3_7_flash.csv)
  ds=$(lines redesign/artifacts/mnn_tool_search_deepseek_v4_pro.csv)
  echo "lines q8=$q8 q7m=$q7m q7f=$q7f ds=$ds" | tee -a "$LOG"
  if [[ "$q8" -ge 225 && "$q7m" -ge 225 && "$q7f" -ge 225 && "$ds" -ge 225 ]]; then
    echo "=== ALL COMPLETE $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
    break
  fi
  pending=$(python3 - <<'PY'
import csv
import scripts.mnn_tool_search_bakeoff as b
rows=list(csv.DictReader(b.DEFAULT_INPUT.open(encoding='utf-8')))
total=0
for m in b.MODELS:
  done=b.load_done_ids(b.out_paths(m['slug'])[0])
  total += sum(1 for r in rows if (r.get('product_id') or '') not in done)
print(total)
PY
)
  echo "pending=$pending" | tee -a "$LOG"
  if [[ "$pending" -eq 0 ]]; then
    echo "=== ALL COMPLETE (pending0) ===" | tee -a "$LOG"
    break
  fi
done
