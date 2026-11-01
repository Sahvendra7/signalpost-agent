# V3 behaviour-change log

Every deliberate change of published behaviour relative to the baseline `ff3b515` is listed here. Each entry names
the rule, the reason (the defect it fixes) and any earlier test assertion it replaces. See the design in
`docs/superpowers/specs/2026-11-01-signalpost-v3-design.md`.

## Phase 0 — groundwork (no change to published facts)

- **Every envelope carries `run.code_version`, and so does the run report.** Fields: `source_sha256`,
  `package_version`, `git_commit`, `git_dirty`. The field is additive. Envelopes without it still validate. A
  malformed value produces the contract finding `invalid_code_version`.
- **New tooling.** `scripts/replay_run.py` with `norway_company_agent/replay.py` replays captured runs. The audit kit
  is `scripts/audit_kit.py` with `norway_company_agent/audit.py`. Regression fixtures for 16 companies are in
  `tests/fixtures/v3/`.
