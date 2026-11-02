#!/bin/bash
SP=/tmp/claude-0/-home-user-signalpost-agent/3e43140a-eb25-5545-aa91-a0fabc1c685e/scratchpad
cd /home/user/signalpost-agent
for policy in "$@"; do
  for s in smoke100 midsize40 fresh60 fresh60b diag80 eval120 eval200; do
    out=$SP/m/p-$policy-$s; rm -rf $out; mkdir -p $out
    ( .venv/bin/python $SP/v31/replay_policy.py $policy --captured-profiles $SP/m/base-$s/profiles.jsonl --captured-snapshots $SP/m/base-$s/snapshots \
      --organisations $SP/m/$s.jsonl --output $out/envelopes.jsonl --profiles-output $out/profiles.jsonl --report $out/report.json \
      --snapshot-dir $out/snapshots --run-id p-$policy-$s --no-viewer --no-history > $out/stdout.txt 2> $out/stderr.txt; echo "exit $?" >> $out/stdout.txt ) &
  done
  wait
done
