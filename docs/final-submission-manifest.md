# Final submission manifest

## V3.1 candidate 2 — candidate 1 plus the foreign-namesake entity correction (not submitted, not scored)

| | |
|---|---|
| Branch | `claude/awesome-sagan-m2lppu` (local; not pushed) |
| Tag | `v3.1-candidate-2` (local) on the docs and measurements commit on top of `334a085` |
| **Code under test** | **`334a085`**. Later commits change only documentation and measurements; `git diff 334a085 v3.1-candidate-2 -- src tests scripts pyproject.toml uv.lock` is empty. |
| Previous candidate | `v3.1-candidate-1` (`00e644a`, code `0e4c426`), unchanged and reproducible |
| What changed | `attribution/names.py` and `attribution/operator.py` only: a handle ending in a foreign legal form the company's own name lacks names another entity; a site naming the company's name under a foreign legal form, and never this company, is a group or brand site. News rules unchanged. See `docs/v31-release-report.md` §10. |
| Impact on captured bytes | On 8 sets (860 organisations), the only change from `0e4c426` is LOGSCOM AS: 2 incorrect profiles withheld. No labelled-correct profile is lost. |
| Tests | 533 passed and 175 subtests, in the working tree and in the clean room |
| Live check (2026-11-04) | 100/100 `completed`; 0 contract findings (3,995 hashes re-checked); $0; no LLM; no social-platform host. The refresh kept last values on 2 outage events. The 8 reproduction companies are as intended. Published site facts are identical in count to `0e4c426`'s live run. |
| **Independent accuracy** | As for candidate 1: eval200b outputs are identical under `334a085`. News 80.2%: the 90% target is NOT met. Social 100% (68/68). |

## V3.1 candidate 1 — news classification accuracy remediation (not submitted, not scored)

| | |
|---|---|
| Branch | `claude/awesome-sagan-m2lppu` (local; not pushed) |
| Tag | `v3.1-candidate-1` (local) on the final docs and measurements commit |
| **Code under test** | **`0e4c426986885c2661b5e55946deae0f0f046429`**. Later commits change only documentation and measurements; `git diff 0e4c426 v3.1-candidate-1 -- src tests scripts pyproject.toml uv.lock` is empty. |
| Previous candidate | `v3-candidate-2` (code `7b8fc69`), unchanged and reproducible |
| What changed | `docs/v31-news-analysis.md`, `docs/v31-release-report.md`: content-anchored news with recorded attribution, the registry-group site rule, site-wide text never naming an item's company |
| Tests | 526 passed and 172 subtests, in the working tree and in 3 of 3 clean-room runs |
| Live check (2026-11-02) | 100/100 `completed`; 0 contract findings (3,993 hashes re-checked); $0; no LLM; no social-platform host. The refresh baseline was the published envelopes, with 2 outage events that kept their last values. The 8 reproduction companies are as intended. |
| **Independent accuracy** (new sample eval200b, scored once, `assistant_blind`) | **News 80.2% (105/131, CI 72.5–86.1): the 90% target is NOT met.** News retention 70.6%. Social 100% (68/68, CI 94.7–100). Careers page 7/7. Job ads: not validated. |

## V3 candidate 2 — after the pre-release remediation pass (not submitted, not scored)

| | |
|---|---|
| Branch | `claude/awesome-sagan-m2lppu` (local; not pushed) |
| **Code under test** | **`7b8fc69d10aed1a3677b2646bd44c49db7ae78d8`**. Later commits change only documentation and measurements; `git diff 7b8fc69 <candidate> -- src tests scripts pyproject.toml uv.lock` is empty. |
| Previous candidate | `v3-candidate-1` (local tag on `4549f3a`; code `dc96260`), kept unchanged and reproducible |
| What changed | `docs/v3-remediation.md`: ASAK and Ashtead, careers paths, imported-envelope outages, the reader-addressing rule, feed sections, default posts, slugified A/S |
| Tests | 487 passed and 172 subtests, in the working tree and in 3 of 3 clean-room runs |
| Live check | 100/100 `completed`; 0 contract findings; refresh with no removals, additions or retractions, and 2 correct "last value kept" outage events |
| **Independent accuracy** (new random sample eval120, scored once, `assistant_blind`) | Social 93.0% (CI 81.4–97.6). **News 25.6% (CI 14.6–41.1): the 90% target is NOT met.** Careers page 4/4 (CI 51–100: too few to establish the target). Job ads: none decidable. |

## V3 candidate 1 (superseded by candidate 2; not submitted)

| | |
|---|---|
| Repository | https://github.com/Sahvendra7/signalpost-agent |
| Branch | `claude/awesome-sagan-m2lppu`, branched from the previously submitted `ff3b515` (not `main`; `main` is the older `5575d0c`, so name the commit). |
| **Release candidate commit** | The head of `claude/awesome-sagan-m2lppu` that adds this section (documentation and measurements only). Its full SHA is stated in the release report; a commit cannot contain its own SHA. |
| **Code under test** | **`dc96260d76aa089bc07e41382763832cb17d5ad5`**. `git diff dc96260 <candidate> -- src tests scripts pyproject.toml uv.lock` is empty. |
| Install | `uv sync --locked` (dependencies identical to `ff3b515`: `git diff ff3b515 dc96260 -- pyproject.toml uv.lock` is empty) |
| Run (documented command, unchanged) | `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>` |
| Tests on `dc96260` | 474 passed and 172 subtests in each run: 1 run in the working tree, plus 3 of 3 in the clean room. Earlier code (`730ccfe`) passed 5 of 5 runs of 468. |
| Clean room on `dc96260` | Fresh clone, empty uv cache, `uv sync --locked` OK; documented command exit 0, with the viewer and history written (`measurements/v3-release-2026-11-01/cleanroom/`) |
| 100-company check on `dc96260` | 100/100 `completed` in input order; 0 contract findings (3,994 hashes re-verified); 0 unsupported summary statements; no platform host contacted; $0. Refresh through the run history: **0 change events**, baseline `published_envelope` for 100/100. `measurements/v3-release-2026-11-01/` |
| Reproductions (live, `dc96260`) | 911771098, Tyin Alpint, Bergknapp, Bartec, BK Bygg — see `docs/v3-release-report.md` §9 |
| Accuracy | `docs/v3-accuracy.md`. Local measurements labelled `assistant_blind`, not Builderr scores. The second held-out news gate failed (85.0% against 90%). Replaying all four measured sets through `dc96260` publishes exactly the measured units. |
| Default external cost / APIs | $0. Only the public Brønnøysund registry APIs and the companies' own websites. |
| LLM / Brave / NAV | Off (not imported) / not used / not used |


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
