# Final submission manifest

## Current release candidate: C300 + refresh fix + race fix (not submitted)

| | |
|---|---|
| Repository | https://github.com/Sahvendra7/signalpost-agent |
| Branch | `claude/c300-refresh-fix` (not `main`; `main` is an older tree, so name the commit) |
| **Release candidate commit** | The head of `claude/c300-refresh-fix` that adds this section (documentation only). Its full SHA is stated in the release report and the submission email; a commit cannot contain its own SHA. |
| **Code under test** | **`71fa494c2f2b774a6bdec4669577243429f7f36c`**. The candidate is code-identical to it: `git diff 71fa494 <candidate> -- src tests scripts pyproject.toml uv.lock` is empty. |
| Code lineage | C300 `6487205`, then the refresh fix `8fba893` (ported from `7a8ceba`), then the race fix `71fa494` (ported from `2e83f18`) |
| Install | `uv sync --locked` |
| Run (documented command; writes `<output>.viewer.html` too) | `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>` |
| Tests on `71fa494` | Full suite 6 of 6 runs passed, plus 3 of 3 in the clean room: 361 tests and 91 subtests each, 0 failures, 0 skipped |
| Clean room on `71fa494` | Fresh clone, empty uv cache, `uv sync --locked` OK; documented command OK, with the viewer written |
| 100-company check on `71fa494` | 100/100 `completed` in input order; 0 contract findings (3,997 hashes re-verified); 0 unsupported summary statements; viewer written; refresh with 0 events; no platform, Brave or NAV host |
| Default external cost / APIs | $0. Only the public Brønnøysund registry APIs and the companies' own websites. |
| LLM / Brave / NAV | Off / not used / not used |
| Details and known limitations | `docs/c300-refresh-fix.md` §0 |

No measurement ran on the documentation commit itself; all ran on `71fa494`.

## V1 (officially evaluated; historical)

> The rest of this manifest describes **V1**, the officially evaluated `submission-candidate-1` (`104c3c4`). That tag
> is unchanged. Revision 1 (code `a5e06ce`, docs commit `05d7566`) is described in `docs/revision-1-final.md` §6. The
> C300 revision (code `6487205`) is described in `docs/c300-revision.md` §G.

| | |
|---|---|
| Repository | https://github.com/Sahvendra7/signalpost-agent |
| V1 submission | The commit tagged `submission-candidate-1`. Its full SHA is given by `git rev-parse submission-candidate-1` and stated in the submission email. |
| Tag | `submission-candidate-1` |
| **Code under test** (all validation runs below) | `4f827ee7813db166b0c03dabec5c9d61da5b9a99` |
| Candidate relation | Code-identical to `4f827ee`; differs only in documentation. `git diff 4f827ee submission-candidate-1` touches only `docs/`, `measurements/` and `AGENTS.md` (a note for coding agents; not used by the run). |
| Smoke test | **100/100 terminal results** (live, 100 inputs, 100 envelopes, 100 `completed`, input order preserved, validation passed with 0 contract findings, 118.3 s). `measurements/final-validation-2026-10-03/live-100/` |
| Full-batch validation | **1,200/1,200 terminal results** (live, unseen companies, 1,200 `completed`, input order preserved, validation passed with 0 contract findings, 1,117.0 s). `measurements/final-validation-2026-10-03/live-1200/` |
| Refresh and timeout validation | 0 false changes across 3,998 facts. Timeout run (45 s deadline): 100/100 rows in 38.0 s. `measurements/final-validation-2026-10-03/README.md` |
| Peak memory | Not recorded on `4f827ee`. Last recorded: 222 MiB for 100 companies (`c5c6a32`) and 399 MiB for 1,200 companies (`403a9c1`). |
| Tests | **303 passed, 68 subtests passed** (`uv run --with pytest pytest -q`, clean room on `4f827ee`) |
| Default external cost | **$0** |
| Default external APIs | **None paid and none keyed.** The run uses only the public Brønnøysund registry APIs (NLOD 2.0) and the companies' own websites. |
| LLM | Disabled by default. The run command never loads it. |
| Brave | Unused. It is experiment code only and is not imported by the run path. |
| NAV | Optional and disabled by default. It is not in `DEFAULT_MODULES` and is not imported by the run path. |

No validation run was executed on the tagged commit itself. Every measurement above comes from `4f827ee`, which has the same code.

The commits after `4f827ee` (`78d1c2f`, `fae42d1`, `f02051c` and the tagged commit) are documentation-only. They added the
final-validation material, `AGENTS.md`, this manifest and the "final candidate / code under test" notes in the submission
documents. The candidate is named by its tag, not by SHA, because a commit cannot contain its own SHA.

## Install and run

```bash
uv sync --locked

uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>
```

## Commit references in the submission documents

| Commit | Meaning |
|---|---|
| `submission-candidate-1` | Final submission candidate. Code-identical to `4f827ee`; differs only in documentation. |
| `fae42d1` | Historical. Documentation reconciliation; added this manifest. Code-identical to `4f827ee`. |
| `f02051c` | Historical. Added `AGENTS.md` (a note for coding agents). No code. |
| `78d1c2f` | Historical. Added the final-validation measurements; earlier holder of the tag. Code-identical to `4f827ee`. |
| `4f827ee` | Code under test for the final validation (live 100, live 1,200, refresh, timeout and clean room). |
| `403a9c1` | Historical official-contract audit and its 1,200-company baseline. Code-identical to `c5c6a32`. |
| `c5c6a32` | Historical submission audit and smoke test (`docs/submission-audit.md`, `measurements/submission-smoke-2026-10-03/`). |
| `99d09d9` | Historical target of the first audit. Not submission-safe (unsafe outbound URL handling, fixed in `c5c6a32`). |

## Known limitations

These are copied from `docs/official-submission-checklist.md` ("Status after validity hardening" and rows 8 and 24).

**Blockers that need Builderr** (none can be resolved from the repository):

1. **Time budget.** The official time and resource budget is unpublished. The evaluator must set
   `SIGNALPOST_DEADLINE_SECONDS` to it, and the default is only a fail-safe.
2. **Frozen registry snapshot.** Its format and delivery are unconfirmed. The command accepts Brreg's gzip
   CSV, or none at all.
3. **Additive envelope fields.** It is unconfirmed whether the evaluator accepts or ignores these fields:
   `identity`, `company_status`, `company_summary`, `refresh`, `input_record`, `modules`, `area_coverage`.
4. **Area mapping.** The scoring mapping for `public_footprint` is unconfirmed (`docs/official-scoring-model.md`).

**Accepted limitations:**

- Wrong-company precision has only been audited by us.
- Per-site terms are not checked.
- There is no client-side Brreg throttle.
- DNS rebinding between the address check and the connection is not prevented.
- The 1,200-company viewer is 13.4 MB.
- Recall optimisation has not been started, by instruction.
- Running the same command again overwrites its own output paths. Use new paths with `--previous-profiles`.
- External coverage is low. On the live 1,200 run: verified websites 121, public footprint 77, hiring 1.
