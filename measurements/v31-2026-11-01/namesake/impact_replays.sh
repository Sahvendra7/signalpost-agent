#!/bin/bash
S=SCRATCH
cd /home/user/signalpost-agent
for s in smoke100 midsize40 fresh60 fresh60b diag80 eval120 eval200 eval200b; do
  out=$S/m/ns-$s; rm -rf $out; mkdir -p $out
  ( .venv/bin/python scripts/replay_run.py --captured-profiles $S/m/base-$s/profiles.jsonl --captured-snapshots $S/m/base-$s/snapshots \
      --organisations $S/m/$s.jsonl --output $out/envelopes.jsonl --profiles-output $out/profiles.jsonl --report $out/report.json \
      --snapshot-dir $out/snapshots --run-id ns-$s --no-viewer --no-history > $out/stdout.txt 2> $out/stderr.txt; echo "exit $?" >> $out/stdout.txt ) &
done
wait
