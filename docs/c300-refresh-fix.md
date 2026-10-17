# C300 release candidate: refresh fix and race fix

**Not submitted.** No score is claimed. Every number below is a local measurement made on 2026-10-17.

| | Commit |
| --- | --- |
| C300 code under test (base) | `648720516ced747412817ecf1c38ce1de75296da` |
| C300 candidate and its documentation (base of this branch) | `369fccd13eda73014b8f6a8888c67a5c4e6a3b5f` |
| Refresh fix, as developed on older Revision 1 code | `7a8cebac99d9e06b5e610f1e5967365be44a592c` (branch `claude/pensive-wright-kh4sz8`) |
| Refresh-fix code (§1–§4) | `8fba8933d55e2630091b4da3ac25acc714a83cec`; its candidate `7879be3f79e691593b85e0c6e59fe7637c77b557` is **superseded** |
| Race fix, as developed | `2e83f18ba8b81892414e4602d052b4ba21432b8d` (branch `claude/c300-refresh-fix-test-races`) |
| **Final code under test** (§0) | **`71fa494c2f2b774a6bdec4669577243429f7f36c`**: `8fba893` plus the race fix |
| **Final release candidate** | The head of `claude/c300-refresh-fix` that adds this section. It is code-identical to `71fa494`: `git diff 71fa494 HEAD -- src tests scripts pyproject.toml uv.lock` is empty. Its full SHA is recorded in the release report; a commit cannot contain its own SHA. |

`main` (`5575d0c`) and the V1 tag `submission-candidate-1` (`104c3c4`) are untouched. No Gemini configuration or
instruction file is in the candidate.

**Where each measurement ran.** §0 ran on `71fa494`. §1–§4 ran on `8fba893` and are kept as the record of the refresh
fix. None ran on the documentation commit itself, which differs from `71fa494` only in `docs/`, `measurements/` and
`HANDOFF.md`.

## 0. Final release: the race fix integrated (code `71fa494`)

### Changes

Only `cli.py`, `pipeline.py` and `tests/test_deadline_streaming.py` changed. The source is identical to `2e83f18`.
Relative to `8fba893`, `src/` differs only in `cli.py` (+3/−2) and `pipeline.py` (+2).

| Change | Effect |
| --- | --- |
| `cli.on_result` | Each company's profile is appended and fsynced **before** its result line. A process killed between the two writes can no longer leave a published result without its profile. After a kill, the profiles file can at most hold one more company than the results file, and `--resume` then reuses that profile. |
| `run_batch` | When a stop request (SIGTERM) arrives while the main loop is inside `wait()`, the remaining workers return "not started" and the queue drains before the loop looks again. The report then records `stop_reason: "interrupted"` instead of falling back to `grace_window`. This applies only when some company was actually not started. The envelopes were already correct. |
| `StreamOrderTests` (from `2e83f18`) | Runs the CLI in a subprocess and checks that every profile is written before its result line |
| `test_stop_that_drains_the_queue_while_the_loop_waits_is_reported_as_interrupted` (new) | Reproduces the stop race on every run: the patched `wait()` sets the stop and returns only once the queue is drained. This is the only addition beyond `2e83f18`, because the stop race otherwise had only a timing-dependent test. |

### Focused regressions: unfixed (`7879be3`) against fixed (`71fa494`)

Measurements are in `measurements/c300-release-2026-10-17/`. The stress runs ran interleaved, an unfixed run then a
fixed run, under identical conditions. Each run's stdout, stderr and exit code are kept, and a run without a pytest
summary would have counted as a failure (none occurred).

| Check | Unfixed `7879be3` | Fixed `71fa494` |
| --- | --- | --- |
| Deterministic: profile before result line (`StreamOrderTests`) | **fails** (`1 not less than 0`) | passes |
| Deterministic: stop that drains the queue during `wait()` | **fails** (`'grace_window' != 'interrupted'`) | passes; 15 of 15 repeats |
| SIGKILL test, fsync slowed by 30 ms, 20 runs | **20 failed** (`2 not greater than or equal to 3`: a result without its profile) | 20 passed |
| SIGTERM test under CPU load (8 busy loops on 4 CPUs), 30 runs | **1 failed** (`'grace_window' != 'interrupted'`), 29 passed | 30 passed |

1 against 0 in 30 load runs is weak evidence on its own. The deterministic test is what proves the stop fix.

### Final validation on `71fa494`, in the requested order

| # | Step | Result |
| --- | --- | --- |
| 1 | `tests/test_deadline_streaming.py` | 10 passed, 3 subtests passed |
| 2 | `tests/test_refresh_semantics.py` | 12 passed (includes the three outage and refresh regressions) |
| 3 | Full suite, complete output and JUnit kept, 6 runs (2 cold, 4 warm) | **6 of 6 passed**: 361 tests and 91 subtests (452 JUnit cases), 0 failures, 0 errors, 0 skipped. The headless-Chromium tests ran. |
| 4 | Fresh `git clone` of the branch at `71fa494`, empty `UV_CACHE_DIR`, `uv sync --locked` | Install OK. Full suite **3 of 3 passed**, including the first (cold) run. The documented command on 3 companies exited 0, validation passed, and it wrote the viewer. |
| 5 | Documented command (via `run_final.sh`: 8 workers, no `--bulk`, snapshots, host audit) on the fixed 100 (SHA-256 `80eb79e6…`), its refresh with `--previous-profiles`, and 911771098 | See below |
| 6 | Evidence validation (`analyse.py`: contract, every snapshot hash, summary support, hosts, viewer), offline refresh replay, result/profile consistency, secret scan | See below |

| | 100 | Refresh of the 100 | 911771098 (WordPress case) |
| --- | --- | --- | --- |
| Terminal results / input order | 100 `completed` / yes | 100 `completed` / yes | 1 `completed` / yes |
| Results / profiles; every result has its profile; duplicates | 100 / 100; yes; none | 100 / 100; yes; none | 1 / 1; yes; none |
| Validation; contract findings with every snapshot hash re-verified | passed; 0 (3,997) | passed; 0 (3,997) | passed; 0 (62) |
| Summary statements / unsupported | 2,586 / **0** | 2,586 / **0** | 29 / **0** |
| Period comparisons / not comparable / employee count unknown / shown as 0 | 90 / 3 / 84 / 0 | 90 / 3 / 84 / 0 | 1 / 0 / 1 / 0 |
| Viewer written by the documented command | yes | yes | yes |
| Change events | — | **0** | — |
| Runtime / requests / cost | 130.4 s / 769 / $0 | 127.4 s / 770 / $0 | 7.2 s / 16 / $0 |
| Platform, Brave, NAV or wordpress.com hosts | none | none | none |
| stderr | empty | empty | empty |

- **WordPress/LinkedIn stays rejected.** 911771098 keeps its verified website and 20 dated posts. Its social profile is
  `ambiguous`, and no WordPress.com profile URL appears in the envelope.
- **Site facts against the previous candidate's run (`8fba893`):** identical for 99 of 100 companies. The difference
  is 929336038 Sjøloftet, whose site answered in this run but had an outage in that one (§3). It now has the same
  Facebook profile and careers page as C300.
- **Outages keep old facts.** The live refresh had no outage to observe (0 events). The behaviour is covered by the
  three refresh regression tests (step 2) and was seen live on `8fba893` (§3).
- **Offline refresh replay** (`scripts/run_refresh_replay.py`): 2 of 2 expected changes, 0 false, idempotent,
  `qualification_passed: true`.
- **Secrets:** no hit in the repository tree or in any file the agent writes (envelopes, profiles, reports, viewers,
  logs). The only pattern hits were inside 7 snapshot files, which are byte-exact copies of third-party public pages
  (e.g. a site's own client-side map key). Snapshots are not committed. No Brave, NAV or LLM variable is set.
- **The 1,200-company batch was not re-run.** The race fix changes only the order of two writes and one report label
  after a stop, and the 100-company run showed no defect or runtime concern.

### Known limitations

- **No official score.** Builderr's pool, matching rules, runtime budget and registry snapshot format are not
  published (`docs/official-scoring-model.md`). The deadline default (2,700 s) is a fail-safe; the evaluator must set
  `SIGNALPOST_DEADLINE_SECONDS`.
- **External coverage remains low.** On the fixed 100: websites 14, public footprint 10, hiring 0. Website discovery
  was deliberately not changed.
- **Live drift.** Company sites change between runs (Sjøloftet above). Single-run site facts can differ from any earlier
  run.
- **Row-level code after SIGTERM.** Companies not started because of a stop request carry the error code
  `deadline_exceeded` with the note "deadline: company not researched before the batch deadline". Only the report's `stop_reason` says `interrupted`. This
  is pre-existing, and was left unchanged to keep the release narrow.
- **After a SIGKILL,** the profiles file may hold one company more than the results file. This is by design now; the
  reverse can no longer happen.
- **Snapshots** contain whatever the captured public pages contain, including those sites' own client-side keys.
- **Test environment.** The headless-viewer tests need `node` and a global `playwright`; without them they are skipped,
  not failed.

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
- The refresh fix does not touch either path and **does not resolve them**. They remained in `8fba893`; §0 fixes them in `71fa494`.
- No test was removed, skipped or weakened.

**The optional fix** (`2e83f18`, not in the candidate) has two parts:

- the CLI writes each profile before its envelope;
- `run_batch` records `interrupted` when a stop request drained the queue.

It adds one subprocess test (`StreamOrderTests`, which fails on the candidate). It passed 12 of 12 full-suite runs (3
cold, 9 warm; 360 tests and 91 subtests). A first version of that test called the CLI in-process. The CLI can `os._exit` when other threads are alive, which ended pytest silently with exit code 0 partway through the suite. Those 9 runs were discarded. The test now runs the CLI in a subprocess, and `tests/suite_run.sh` reports any run without a pytest summary or JUnit file as TRUNCATED. The optional fix changes no output of a normal run. After a kill it changes only which file
gets the last line, and after a SIGTERM only the report label. The owner decided to include it (§0).
