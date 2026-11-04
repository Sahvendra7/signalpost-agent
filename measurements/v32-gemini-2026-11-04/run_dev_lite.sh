#!/bin/bash
# Diagnostic runs on gemini-3.5-flash-lite (free tier), one at a time (the per-minute quota is per model):
# P2 on all of eval200 (dev), then P1/P3/P2-think/P4 on the fixed dev80 subset. Cached items are not re-requested.
cd "$(dirname "$0")/../.."
R=measurements/v32-gemini-2026-11-04/runs; D=measurements/v32-gemini-2026-11-04/datasets; M=gemini-3.5-flash-lite
go() { uv run python scripts/run_gemini_news_experiment.py --packets $D/eval200.packets.jsonl.gz --prompt $1 --model $M \
        --experiment-id $2-$1-$M --out $R/$2-$1-$M.jsonl --live --max-calls 450 --rpm 14 --workers 8 $3 2>&1 | grep -v UV_NATIVE | tail -30 > $R/$2-$1-$M.stdout.txt; }
go news-p2-evidence-v1 dev
for p in news-p1-binary-v1 news-p3-counter-v1 news-p2-evidence-think-v1 news-p4-twostage-v1; do go $p dev80 "--only $D/eval200.dev80.txt"; done
