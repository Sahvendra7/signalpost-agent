#!/bin/bash
# Completion of the pre-registered V3.2 runs on the corrected packets (after the aid-misalignment fix), free tier.
# One job per (key, model) pair; each run has a hard call cap and stops at the first daily-quota 429. Cached responses
# are never re-requested. Usage: run_completion.sh grid|final31|final35|diag35|primary PROMPT_ID
cd "$(dirname "$0")/../.."
R=measurements/v32-gemini-2026-11-04/runs; D=measurements/v32-gemini-2026-11-04/datasets
go() { # set prompt model key expid [extra]
  uv run python scripts/run_gemini_news_experiment.py --packets $D/$1.packets.jsonl.gz --prompt $2 --model $3 --key-env $4 \
    --experiment-id $5 --out $R/$5.jsonl --live --max-calls ${MAXC:-450} --rpm 12 --workers 6 $6 2>&1 | grep -v UV_NATIVE | tail -30 > $R/$5.stdout.txt; }
case $1 in
  grid) for p in news-p1-binary-v1 news-p2-evidence-v1 news-p3-counter-v1 news-p2-evidence-think-v1 news-p4-twostage-v1; do
          MAXC=170 go eval200 $p gemini-3.1-flash-lite GEMINI_API_KEY_1 dev80v2-$p-gemini-3.1-flash-lite "--only $D/eval200.dev80.txt"; done ;;
  final31) MAXC=345 go evalg250 news-p2-evidence-v1 gemini-3.1-flash-lite ${2:-GEMINI_API_KEY} final-evalg250-news-p2-evidence-v1-gemini-3.1-flash-lite ;;
  final35) MAXC=345 go evalg250 news-p2-evidence-v1 gemini-3.5-flash-lite GEMINI_API_KEY_2 final-evalg250-news-p2-evidence-v1-gemini-3.5-flash-lite ;;
  diag35) MAXC=360 go eval200b news-p2-evidence-v1 gemini-3.5-flash-lite ${2:-GEMINI_API_KEY} diagv2-eval200b-news-p2-evidence-v1-gemini-3.5-flash-lite ;;
  primary) MAXC=${MAXC:-345} go evalg250 $2 gemini-3.1-flash-lite ${3:-GEMINI_API_KEY_2} final-evalg250-$2-gemini-3.1-flash-lite ;;
esac
