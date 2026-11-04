#!/bin/bash
# Second diagnostic set: P2 on all eval200b candidates (V3.1 freeze-2 arm f2 = release output), gemini-3.5-flash-lite.
cd "$(dirname "$0")/../.."
while kill -0 ${1:-0} 2>/dev/null; do sleep 10; done
R=measurements/v32-gemini-2026-11-04/runs; D=measurements/v32-gemini-2026-11-04/datasets; M=gemini-3.5-flash-lite
uv run python scripts/run_gemini_news_experiment.py --packets $D/eval200b.packets.jsonl.gz --prompt news-p2-evidence-v1 --model $M \
  --experiment-id diag-eval200b-news-p2-evidence-v1-$M --out $R/diag-eval200b-news-p2-evidence-v1-$M.jsonl --live --max-calls 360 --rpm 14 --workers 10 \
  2>&1 | grep -v UV_NATIVE | tail -30 > $R/diag-eval200b-news-p2-evidence-v1-$M.stdout.txt
