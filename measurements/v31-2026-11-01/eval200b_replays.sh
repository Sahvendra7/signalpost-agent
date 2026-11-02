#!/bin/bash
S=/tmp/claude-0/-home-user-signalpost-agent/3e43140a-eb25-5545-aa91-a0fabc1c685e/scratchpad
PY=/home/user/signalpost-agent/.venv/bin/python
IN=/home/user/signalpost-agent/measurements/v31-2026-11-01/inputs/eval200b.jsonl
run() { name=$1 tree=$2 EXTRA=$3; out=$S/m/$name-eval200b; rm -rf $out; mkdir -p $out
  ( cd $tree && $PY scripts/replay_run.py --captured-profiles $S/m/base-eval200b/profiles.jsonl --captured-snapshots $S/m/base-eval200b/snapshots \
      --organisations $IN --output $out/envelopes.jsonl --profiles-output $out/profiles.jsonl --report $out/report.json \
      --snapshot-dir $out/snapshots --run-id $name-eval200b --no-viewer $EXTRA > $out/stdout.txt 2> $out/stderr.txt; echo "exit $?" >> $out/stdout.txt ) ; }
run rbase $S/base-tree &
run c2 $S/tree-7b8fc69 --no-history &
run f1 $S/tree-v31 --no-history &
run f2 $S/tree-f2 --no-history &
wait
