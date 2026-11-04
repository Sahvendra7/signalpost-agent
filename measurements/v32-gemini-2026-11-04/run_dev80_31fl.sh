#!/bin/bash
# Prompt comparison on dev80 with gemini-3.1-flash-lite (separate free-tier quota), diagnostic only.
cd "$(dirname "$0")/../.."
R=measurements/v32-gemini-2026-11-04/runs; D=measurements/v32-gemini-2026-11-04/datasets; M=gemini-3.1-flash-lite
for p in news-p1-binary-v1 news-p3-counter-v1 news-p2-evidence-think-v1 news-p4-twostage-v1; do
  uv run python scripts/run_gemini_news_experiment.py --packets $D/eval200.packets.jsonl.gz --only $D/eval200.dev80.txt --prompt $p --model $M \
    --experiment-id dev80-$p-$M --out $R/dev80-$p-$M.jsonl --live --max-calls 170 --rpm 12 --workers 6 2>&1 | grep -v UV_NATIVE | tail -30 > $R/dev80-$p-$M.stdout.txt
done
