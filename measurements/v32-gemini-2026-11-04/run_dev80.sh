#!/bin/bash
# Prompt comparison on the fixed dev80 subset of eval200 (diagnostic), gemini-3.5-flash-lite, free tier, capped.
cd "$(dirname "$0")/../.."
R=measurements/v32-gemini-2026-11-04/runs; D=measurements/v32-gemini-2026-11-04/datasets
for p in news-p1-binary-v1 news-p3-counter-v1 news-p2-evidence-think-v1 news-p4-twostage-v1; do
  uv run python scripts/run_gemini_news_experiment.py --packets $D/eval200.packets.jsonl.gz --only $D/eval200.dev80.txt --prompt $p \
    --model gemini-3.5-flash-lite --experiment-id dev80-$p-gemini-3.5-flash-lite --out $R/dev80-$p-gemini-3.5-flash-lite.jsonl \
    --live --max-calls 170 --rpm 14 --workers 4 2>&1 | grep -v UV_NATIVE | tail -30 > $R/dev80-$p-gemini-3.5-flash-lite.stdout.txt
done
