# Batch deadline and streaming output

Builderr has not published the official time budget. The values below are a fail-safe default, not a
claim about the official budget. The evaluator (or anyone running the command) should set the deadline
to the real budget minus a safety margin.

| Setting | Flag | Environment | Default |
| --- | --- | --- | --- |
| Batch wall-clock deadline | `--deadline-seconds` | `SIGNALPOST_DEADLINE_SECONDS` | 2,700 s. This leaves headroom over the measured 1,200-company run. `0` disables the deadline. |
| Grace window | `--grace-seconds` | `SIGNALPOST_GRACE_SECONDS` | 60 s |

## Behaviour (`pipeline.run_batch`)

1. **Degrade.** When the observed per-company runtime projects past the deadline, companies not yet started
   get official-registry research only. Website discovery is skipped, and the module is marked
   `source_error` with error `deadline_degraded`.
2. **Stop new work.** Inside the last `grace_seconds`, no new company starts. Those rows get envelopes with
   `deadline_exceeded`, and any bulk-snapshot identity is kept.
3. **Hard stop.** At the deadline, the batch stops waiting. Each company still in flight is salvaged with the
   official facts already fetched (its profile is copied) and marked `deadline_exceeded`.
4. **Signals.** `SIGTERM` and `SIGINT` act as an immediate hard stop: every remaining row is emitted, and
   the report's `stop_reason` is `interrupted`.

Every input row always gets exactly one terminal envelope, in input order. A company's failure is
isolated to its own row. The report's `deadline` block records:

- `deadline_seconds`;
- `grace_seconds`;
- `stop_reason`;
- `companies_degraded_to_official_only`;
- `companies_not_started`;
- `companies_salvaged_at_hard_stop`.

## Streaming

Each envelope and profile is appended to `--output` and `--profiles-output` as soon as its company is
terminal. Each line is written, flushed and fsynced on its own (`streaming.JsonlStream`), so a run killed
at any point keeps every completed company. At the end, both files are rewritten atomically in input order
(temporary file, fsync, rename). `--previous-profiles` is read before any output file is truncated, so the
same path can be used for both.

Tests: `tests/test_deadline_streaming.py`. They include:

- real-process `SIGKILL` during the first 10 rows, in the middle and near the end;
- `SIGTERM`;
- deadline configuration through the environment.
