# C300 candidate with the refresh fix

**Not submitted.** No score is claimed. Every number below is a local measurement made on 2026-10-17.

| | Commit |
| --- | --- |
| C300 code under test (base) | `648720516ced747412817ecf1c38ce1de75296da` |
| C300 candidate and its documentation (base of this branch) | `369fccd13eda73014b8f6a8888c67a5c4e6a3b5f` |
| Refresh fix, as developed on older Revision 1 code | `7a8cebac99d9e06b5e610f1e5967365be44a592c` (branch `claude/pensive-wright-kh4sz8`) |
| **Code under test** | **`8fba8933d55e2630091b4da3ac25acc714a83cec`** |
| **Candidate** | The head of `claude/c300-refresh-fix` that adds this document. It is code-identical to `8fba893`: `git diff 8fba893 HEAD -- src tests scripts pyproject.toml uv.lock` is empty. |
| Optional, not in the candidate | `2e83f18ba8b81892414e4602d052b4ba21432b8d` (branch `claude/c300-refresh-fix-test-races`): fixes the two races behind the intermittent test failures (§4) |

`main` and the V1 tag `submission-candidate-1` are untouched.

## 1. What was ported, and how

`7a8ceba` was based on Revision 1 (`05d7566`). Its code, docs and test hunks were applied to `369fccd` as a patch.

- None of the hunks overlap a C300 change. Only the `claims.py` hunk moved, by 7 lines.
- Relative to the C300 code `6487205`, only these files differ in `src/`: `claims.py` (+4/−2), `pipeline.py` (+3) and
  `site_research.py` (+5/−3).
- `synthesis.py`, `viewer.py`, `site_facts.py`, `cli.py`, `site_identity.py` and `refresh.py` are byte-identical to
  C300.
- **Not ported:** `.gemini/settings.json` and `GEMINI.md`, the only other changes on that branch. They configure
  another coding agent and are not part of the submitted agent.

| Change | Effect |
| --- | --- |
| `site_research.research_company_site` | When the v1 registry gate verified the website, but the site stage cannot read it (robots.txt unreachable, HTTP or transport error, DNS, budget), the result is `unreadable`, not `verified`. A budget stop there keeps `unreadable`, so it is not mislabeled `budget_exhausted`. |
| `pipeline._site_research` | `unreadable` becomes a `source_error` record. Its note names the state, e.g. "Registry-linked website could not be checked in this run (robots_unreachable); no page was read". |
| `claims._site_research_claims` | A failed or blocked site stage gives the site families (social profile, news item, job posting) `failed` claims, also when the v1 gate published the website. Before, they were `not_available`: "Verified website checked; …", although nothing was checked. The `official_website` claim from the v1 gate is unchanged. |
| `refresh` | Unchanged. `source_error` is already an outage status, so the last supported site facts are carried forward. The result is one `unavailable` event and no `removed` events. |
| `docs/refresh-semantics.md` | Describes the case. |

**Why an unreadable site here is an outage.** The registry branch runs only when the v1 gate fetched and published
the site in the same run, and that gate respects robots. A failure in the site stage moments later is therefore
specific to this run. A site that is really gone or disallowed is handled by the v1 website module itself.

## 2. Regression tests

| Case | Test | On unfixed C300 (`369fccd` source) | On the candidate |
| --- | --- | --- | --- |
| 1. A good website check stores the supported values. 2. An outage alone gives `failed` site facts and an unchanged website claim; a refresh during the outage carries every prior value, with one `unavailable` event and no `removed` | `test_refresh_semantics::…::test_unreadable_registry_linked_site_is_an_outage_not_a_change` (ported) | **fails** (`'available' != 'source_error'`) | passes |
| The site stage reports `unreadable` (robots 503, and budget 0) and the pipeline record is `source_error` | `test_site_research::…::test_unreadable_registry_verified_site_is_an_outage` (ported) | **fails** (`'verified' != 'unreadable'`) | passes |
| 3. The source answers normally again: unchanged facts give no event; genuine changes give exactly one event each (one `added` news item, one `removed` posting), with no duplicates; a repeat run gives no events | `test_refresh_semantics::…::test_site_returning_after_an_outage_reports_only_genuine_changes_once` (new) | **fails**: the outage run already reports `removed` | passes |

Logs: `measurements/c300-refresh-fix-2026-10-17/tests/regression-tests-on-*.log`.

## 3. Live validation (the documented command, unchanged)

The runs used C300's own `measurements/c300-revision-2026-10-17/run_final.sh` (8 workers, no `--bulk`, snapshots,
host audit) on a clean worktree of `8fba893`. The input is the fixed 100-company smoke set, SHA-256 `80eb79e6…`.
Analysis used C300's `analyse.py`, with C300's committed final-100 envelopes (`6487205`, also live on 2026-10-17) as
the baseline.

| | 100 | Refresh of the 100 (`--previous-profiles`) | 911771098 (WordPress case) |
| --- | --- | --- | --- |
| Envelopes / input order / terminal | 100 / yes / 100 `completed` | 100 / yes / 100 `completed` | 1 / yes / `completed` |
| Validation; contract findings with every snapshot hash re-verified | passed; 0 (3,993 entries) | passed; 0 (3,997) | passed; 0 (62) |
| Summary method; statements; unsupported | `deterministic_template_v2`; 2,585; **0** | same; 2,587; **0** | same; 29; **0** |
| Period comparisons / periods not compared / employee count stated as unknown / shown as 0 | 90 / 3 / 84 / 0 | 90 / 3 / 84 / 0 | 1 / 0 / 1 / 0 |
| Viewer written by the documented command | yes | yes | yes |
| Runtime / requests / cost | 124.7 s / 765 / $0 | 126.9 s / 772 / $0 | 7.0 s / 16 / $0 |
| Change events | — | 2 `added`, 0 `removed` | — |
| Platform, Brave, NAV or wordpress.com hosts | none | none | none |

- **WordPress regression still fixed.** 911771098 keeps its verified website and 20 dated posts. Its social profile is
  `ambiguous`, and no WordPress.com profile URL appears in the envelope.
- **Site-derived facts against C300:** identical for 99 of 100 companies.
- **The one difference, 929336038 Sjøloftet, is the fix at work.** In the first run its registry-linked site returned
  an HTTP error, so no page was read.
  - The candidate published `failed` site facts ("Registry-linked website could not be checked in this run
    (http_error)"), and the summary lists them under "Could not be checked". C300 would have published
    `not_available` ("Verified website checked; …").
  - In the refresh run the site answered, and its Facebook profile and careers page appear as the 2 `added` events.
    These are genuine additions relative to a run where they were unknown.
  - No `removed` events were reported. The reverse sequence (a good run, then an outage) cannot be forced live; the
    regression tests cover it.
- **Offline refresh replay** (`scripts/run_refresh_replay.py`, README fixture): 2 of 2 expected changes, 0 false, the
  re-run idempotent, `qualification_passed: true`.

The 1,200-company batch was not re-run. The change touches only the site stage's outage path, and the 100-company run
showed no runtime concern (124.7 s against C300's 122.3 s).

## 4. Tests, clean room and the intermittent failure

**Clean room.** A fresh `git clone` of `claude/c300-refresh-fix`, with an empty `UV_CACHE_DIR`:

- `uv sync --locked` succeeded.
- The documented command on 3 companies exited 0, validation passed, and the run wrote the viewer.
- The first test run had **1 failure** (below). The next two passed.

**Full suite on the candidate code:** 22 runs, each with output, tracebacks and a JUnit report kept
(`tests/full-suite-runs.txt`):

- the first run after the code edit;
- 3 clean-room runs;
- 6 cold runs (`__pycache__` and the tldextract cache removed);
- 12 warm runs.

**20 passed** (359 tests and 91 subtests, 0 skipped, so the headless-Chromium tests ran). **2 failed, one test
each**, and both failures are explained:

| Run | Failing test | Assertion | Root cause |
| --- | --- | --- | --- |
| Clean room, first (cold) run | `test_deadline_streaming::ProcessKillTests::test_sigkill_early_middle_and_late_keeps_completed_results`, subtest `[near end]` | `54 not greater than or equal to 55` (profiles vs envelopes) | The CLI fsyncs each envelope **before** its profile. A SIGKILL between the two writes leaves one envelope without its profile. Slow I/O, as on a cold start, widens the window. |
| Warm run 11 | `test_deadline_streaming::ProcessKillTests::test_sigterm_writes_every_row_in_input_order` | `'grace_window' != 'interrupted'` (`report.deadline.stop_reason`) | After SIGTERM, the remaining workers return "not started" and can drain the queue while the main loop is inside `wait()`. The loop then exits without recording the stop, and the report falls back to `grace_window`. The envelopes are correct; only the report label is wrong. |

These match C300's three unexplained failures: two unnamed single subtests and this named SIGTERM test. The stress
experiments (`tests/stress-experiments.txt`):

| Experiment | Failures |
| --- | --- |
| Candidate, SIGKILL test: normal / fsync slowed by 30 ms | 0/20 / **20/20** (same assertion) |
| Candidate, SIGTERM test: cold `__pycache__` / slowed fsync / CPU load | 0/10 / 0/10 / **2/10** (same assertion) |
| `05d7566` (before C300), SIGKILL with slowed fsync / SIGTERM under CPU load | **10/10** / **2/20** |
| Optional fix `2e83f18`, SIGKILL with slowed fsync / SIGTERM under CPU load | **0/20** / **0/20** (candidate control in the same session: 2/20) |

**Conclusions:**

- Both races predate C300.
- The refresh fix does not touch either path and **does not resolve them**. They remain in the candidate.
- No test was removed, skipped or weakened.

**The optional fix** (`2e83f18`, not in the candidate) has two parts:

- the CLI writes each profile before its envelope;
- `run_batch` records `interrupted` when a stop request drained the queue.

It adds one subprocess test (`StreamOrderTests`, which fails on the candidate). It passed 12 of 12 full-suite runs (3
cold, 9 warm; 360 tests and 91 subtests). A first version of that test called the CLI in-process. The CLI can `os._exit` when other threads are alive, which ended pytest silently with exit code 0 partway through the suite. Those 9 runs were discarded. The test now runs the CLI in a subprocess, and `tests/suite_run.sh` reports any run without a pytest summary or JUnit file as TRUNCATED. The optional fix changes no output of a normal run. After a kill it changes only which file
gets the last line, and after a SIGTERM only the report label. Including it is the owner's decision.
