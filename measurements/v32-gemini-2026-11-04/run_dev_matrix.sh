#!/bin/bash
# Diagnostic prompt/model matrix on eval200 (dev). Free tier; hard call caps per run. Usage: run_dev_matrix.sh JOB
cd "$(dirname "$0")/../.."
R=measurements/v32-gemini-2026-11-04/runs; D=measurements/v32-gemini-2026-11-04/datasets
run() { # set prompt model [extra]
  uv run python scripts/run_gemini_news_experiment.py --packets $D/$1.packets.jsonl.gz --prompt $2 --model $3 \
    --experiment-id dev-$1-$2-$3$5 --out $R/dev-$1-$2-$3$5.jsonl --live --max-calls 450 --rpm ${RPM:-14} --workers 4 $4 2>&1 | grep -v UV_NATIVE | tail -30 > $R/dev-$1-$2-$3$5.stdout.txt; }
case $1 in
  lite) for p in news-p2-evidence-v1 news-p1-binary-v1 news-p3-counter-v1 news-p4-twostage-v1 news-p2-evidence-think-v1; do run eval200 $p gemini-3.5-flash-lite; done ;;
  f36) run eval200 news-p2-evidence-v1 gemini-3.6-flash ;;
  f3p) run eval200 news-p2-evidence-v1 gemini-3-flash-preview ;;
  f38) run eval200 news-p2-evidence-v1 gemini-3.8-flash "--thinking LOW" "+low" ;;
esac
