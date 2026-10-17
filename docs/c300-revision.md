# C300 revision: diagnosis, fixes and release check

**Not submitted and not scored.** Builderr's C300 directional row for this entry (received 2026-10-17) is
56.85/100: recall 26.18/50, precision/evidence 28.27/30, synthesis 2.40/12, UX 0/8. Builderr calls it directional,
not an official qualification result, says C300 uses stricter evidence treatment, and asks for revised commits
before October 18. Nothing here predicts a score; every number below is a local engineering measurement.

| | Commit |
| --- | --- |
| V1 (C12: 57.87, synthesis 12/12, UX 8/8) | `104c3c45d9aef303d3112749a44de5aaf38bca8e`, tag `submission-candidate-1` |
| Revision 1, submitted by the owner | `05d7566cbdf0c2b5324194d28ffbfe718f902521` (code `a5e06ce`) |
| GitHub default branch `main` | `5575d0cae299bdeeb6b1c1914c2b1e5e8eb091be` (an older tree, see A1) |
| C300 revision, main code commit | `7492f3274e85b1d4408d848f05e901dbef2e7de7` |
| **C300 revision final code** | **`648720516ced747412817ecf1c38ce1de75296da`** (`7492f32` plus the report written before the viewer) |
| C300 revision candidate | the head of `claude/awesome-sagan-m2lppu` that adds this document; code-identical to `6487205` |

## A. Diagnosis of the C300 feedback

Builderr's feedback consists of the four scores and one named defect (section D). No C300 output, run id or
processed commit is available in this repository, its GitHub issues or pull requests, or this environment.

### A1. Which version Builderr processed: not determinable from the available metadata

What is known:

- The owner submitted `05d7566` (the head of `claude/awesome-sagan-m2lppu` at C300 time).
- The repository's **default branch is `main` at `5575d0c`**. It is based on `af85bf8` (2026-10-03) and has
  **no `synthesis.py`, no `viewer.py` and no Revision 1 code**. A live run of `main` on 2026-10-17 emits envelopes
  without `company_summary`. A runner that clones the repository URL without checking out the named commit gets
  this tree, which has neither the summary nor the viewer.
- The named WordPress/LinkedIn defect does **not** tell the versions apart. Live on 2026-10-17, V1 (`104c3c4`), `main`
  (`5575d0c`) and Revision 1 (`05d7566`) all publish WordPress.com's LinkedIn page for 911771098. V1 and `main`
  publish `websites.social_profile` `{"platform": "linkedin", "url": "https://linkedin.com/company/wordpress"}`.
  Revision 1 publishes `public_activity.social_profile` `https://www.linkedin.com/company/wordpress`.
- Recall rose from 8.87 (C12) to 26.18 (C300). That is consistent with Revision 1's exact social URLs and dated news
  being scored (V1's scored 0 at C12). But the C300 batch and pool differ from C12, so this is a hypothesis.

Conclusion: either `05d7566` or `main` could have been processed. Section G gives the owner the two actions that
remove the ambiguity.

### A2. Synthesis 2.40/12

Confirmed in our own output (Revision 1 code `a5e06ce`, identical to `05d7566`, live on 1,200 unseen companies on
2026-10-06, re-read):

| Finding | Measure |
| --- | --- |
| "What changed" unanswered | 1,200/1,200 summaries said "Not assessed: no previous run was supplied". An official run passes no previous profiles. |
| Changes that the evidence supports, but unstated | 1,087/1,200 companies have two consecutive twelve-month periods with figures in the accounts register; the summary never compared them |
| Uncited statements | 3,484 of 22,911 statements cited no claim (every "What remains unknown" line among them) |
| Employee count mislabelled | 1,025 summaries listed the employee count under "Checked, nothing found". For 250 of those companies the registry says a count is registered (`harRegistrertAntallAnsatte=true`) but does not publish it. |
| No conclusion for richer profiles | 132 non-sparse companies had no overview at all; "what it does" was only a Norwegian verbatim quote |
| A wrong-company fact inside the summary | 911771098: "Profiles linked from the verified website: facebook …/WordPresscom/; instagram …/wordpressdotcom/; linkedin …/company/wordpress" (section D) |
| Latest-year wording | "Latest annual accounts year registered: X" came from the registry field without a check against the figures. 3/1,200 companies show 2024 figures under "latest 2025". With an older frozen bulk snapshot the wording would call an older year latest. |

Not found:

- No stale period was selected: the figures shown were always the newest period by end date.
- No dates or amounts were absent from the cited claims (0 checker findings).
- No trend wording.

`synthesis.py` is essentially unchanged between V1 (12/12 at C12) and Revision 1. The drop is therefore not a
regression in our code. It coincides with stricter treatment or a different artefact (A1). How Builderr weighs each
item above is not published.

### A3. UX 0/8, although a viewer exists

Confirmed:

- **The documented command never produced the viewer.** `--viewer-output` was optional and absent from the command in
  the README and the submission manifest. An evaluator that runs the documented command gets
  envelopes, profiles and a report, and no HTML.
- `main` (A1) contains no viewer code.
- The viewer had **no way to compare companies**. Builderr's UX definition is "find, compare and verify company
  information on desktop and mobile".

Hypothesis: C12 credited the viewer from the repository and documentation, while C300 judges only what the run
exposes. This is unconfirmed.

### A4. Present in the evaluated artefact?

| | `05d7566` (submitted) | `main` (default branch) |
| --- | --- | --- |
| `company_summary` in every envelope | yes | **no** |
| Viewer code | yes | **no** |
| Viewer produced by the documented command | **no** | no |

## B–D. What changed (`7492f32`, `6487205`)

### D. The WordPress/LinkedIn misattribution (HANS JØRGEN SANDNES AS, 911771098)

Trace (Revision 1, live 2026-10-17, bytes kept in `tests/fixtures/c300/911771098/`):

1. The registry `hjemmeside` is `hjsandnes.wordpress.com`. The site is verified as REGISTRY_LINKED: the legal name
   is on the homepage. That is correct.
2. The blog's footer links `https://wordpress.com/?ref=footer_custom_svg` ("Lag et nettsted eller blogg på
   WordPress.com"). wordpress.com is the blog's registrable domain, and the label holds a news hint ("blogg"), so the
   link was fetched as the site's news page.
3. That page is WordPress.com's homepage. Its JSON-LD Organization (`url https://wordpress.com/`) was taken for "the
   verified site's own Organization structured data", because its URL is on the same registrable domain.
4. Its `sameAs` became three claims (score 0.95, evidence: the wordpress.com page):
   - `https://www.linkedin.com/company/wordpress`;
   - `https://www.facebook.com/WordPresscom/`;
   - `https://www.instagram.com/wordpressdotcom/`.

   The claims cite the right bytes, but they belong to the wrong company.

Root cause: the site's scope was its registrable domain. A site on another subdomain (a hosting platform's tenant)
does not own that domain. In the public universe, 595 of 44,855 registry websites are on such a subdomain, for
example 183 on barnehage.no, 71 on bbl.no, 11 on wordpress.com and 4 each on wixsite.com and blogspot.com.

Fix (`site_facts.in_site_scope`, used at three levels):

- **Fetching:** enrichment (feeds, news, careers, sitemap entries, article pages) stays inside the verified site, so
  wordpress.com is no longer requested.
- **Extraction:** pages outside the site contribute no fact (counted as `page:outside_verified_site`). An Organization
  node owns the site only if its URL is on the site. A subdomain site gets the shared-site gate: only legal-name
  handles, no domain-name rule, no owner structured data, and no articles on other hosts.
- **Claims:** a stored or carried-forward record publishes no fact from a page outside the site, so a refresh cannot
  republish the Revision 1 claims.

A social profile is now published only when all of the following hold. The identity gate itself is not weakened:

- it is an actual link or `sameAs` value;
- its host is Facebook, Instagram, LinkedIn or YouTube;
- it is on a page of the verified website itself;
- the link is the exact linked URL (unchanged since Revision 1);
- its handle carries the legal name, or the site's own Organization data lists it, or (for a site on its own domain
  only) the domain name begins or ends the handle.

A WordPress page, title, slug, share link or text that mentions LinkedIn is not a profile (pinned by a test).

Live on `6487205` (2026-10-17), 911771098 still has its verified website and its 20 dated posts. Its social profile
is `ambiguous`: the blog's 5 own Facebook links are not corroborated. wordpress.com was not contacted, and none of the
three URLs occurs in the envelope.

Effect elsewhere: none measured. The 1,600 companies of the earlier local runs and the 100-company smoke set have no
subdomain-hosted verified site, so their output is unchanged by this rule.

### B. Deterministic synthesis (`deterministic_template_v2`, no LLM)

- **At a glance** (new first section) is a few cited sentences:
  - what the entity is (legal form in English, place, founding date);
  - what it does (its registered words and industry);
  - the most recent figures with their reporting period;
  - the employee count, or that it is unknown;
  - the verified footprint.
- **Most recent period:**
  - selected by period end for each account type;
  - checked against the registry's own last-submitted year, so an older year is never called latest;
  - when the registry names a newer year than the figures, that is stated and listed as unknown;
  - contradictory figures for one metric and period are not reported, and are listed as unknown.
- **What changed:**
  - against a previous run, when one is given (now citing the current fact);
  - against the immediately preceding period, only when both are consecutive twelve-month periods in one currency;
    revenue, operating result, net result and equity are compared one by one with both values cited, using
    "higher", "lower" or "unchanged" and no trend or growth wording;
  - incomparable periods are named and not compared;
  - the registry's dated last change of roles is reported, with a note that the registry does not say what changed;
  - with none of these, nothing is said to have changed.
- **Unknowns:**
  - every unknown statement cites the non-available claims it reports;
  - field names are written as plain labels;
  - attributions held back (`not_applicable`) are explained;
  - the employee-count reason states the registry's `harRegistrertAntallAnsatte`, and the count is "unknown, not
    zero". Only a stated 0 is shown as 0.

### C. UX

- **The documented command now writes the viewer** next to `--output` (`<name>.viewer.html`). Its path is in the
  report (`viewer`) and in the printed summary, and `--no-viewer` skips it. It is written after the envelopes,
  profiles and report are durable, and never fails a run.
- **Viewer:**
  - side-by-side comparison of up to four companies, each cell linking its source with the retrieval date;
  - facts grouped into identity, financials, leadership, locations, and website and public activity;
  - deep links `#org=` and `#compare=`;
  - sort by name, revenue or number of facts;
  - previous/next and arrow-key navigation, a source-failure filter and flagged failed sources;
  - summary first, with the identity anchor below it.
- The page stays self-contained: CSP `default-src 'none'`, `textContent` only, no network.
- A viewer of the live 100-company smoke run is committed:
  `measurements/c300-revision-2026-10-17/final-100/envelopes.viewer.html` (1.38 MB). A reviewer can open it from the
  repository without running anything, and no personal hosting is involved.

## F. Validation

### Tests

- Focused: `tests/test_c300.py` has 17 tests and 8 subtests. 5 of its 7 social-identity tests fail on `05d7566`; the
  other 2 pin behaviour that was already correct.
- Full suite on `6487205`: **356 passed, 91 subtests passed**, up from 339 / 83.
- **Intermittent failure, not explained.** 3 of 57 full-suite runs of the new code each had one failure, and no error
  message was captured:
  - `test_deadline_streaming::test_sigterm_writes_every_row_in_input_order`, on `7492f32`;
  - a single unnamed subtest, on `7492f32`;
  - a single unnamed subtest in the clean-room run below, on `240f91c`.

  Each was the first suite run after a cold start: right after code edits, after the live runs, and in a fresh clone
  with an empty uv cache. None reproduced in the 54 other full runs (30 of them in a loop under concurrent load), in
  25 loops of the deadline/streaming, viewer and C300 modules, or in 18 isolated runs of the SIGTERM test.
  `05d7566` passed 40 of 40 full runs. The subtest-based tests that depend on timing are the existing SIGKILL test
  and the new headless-browser test. It cannot be ruled out that the new tests (two Chromium sessions, CLI
  subprocesses) or the default viewer make a cold-start timing failure more likely. No product behaviour was found
  to differ between runs.
- **Clean room:** a fresh clone of `240f91c` with an empty uv cache. `uv sync --locked` succeeded. Test runs: the
  first had 356 passed and 1 subtest failed (above); the next 33 had 356 passed and 91 subtests passed. The
  documented command on 3 companies exited 0, validation passed, and the run wrote `envelopes.viewer.html`.

| Required regression | Test (`tests/test_c300.py`) |
| --- | --- |
| Null employee count vs zero | `test_null_employee_count_is_unknown_never_zero` (3 null variants; a stated 0 stays 0) |
| FY2024 vs FY2025 | `test_fy2024_versus_fy2025_financials` |
| Latest-period selection | `test_most_recent_period_is_selected_and_an_older_year_is_never_latest` |
| Contradictory trend evidence | `test_contradictory_trend_evidence_is_not_a_trend` (up-then-down years; duplicate conflicting figures) |
| Unsupported conclusions | `test_no_conclusion_from_incomparable_periods`, `test_every_statement_is_supported_by_its_cited_claims` |
| Missing previous snapshot | `test_missing_previous_snapshot` |
| WordPress/LinkedIn (captured evidence) | `WordPressLinkedInRegression` (3 tests on the exact bytes) and `SiteScopeRules` (4) |
| Viewer on the documented command | `ViewerExposure` (CLI default, `--no-viewer`, comparison cells, headless Chromium desktop and phone) |

### Synthesis statements against the retained evidence

`tests/helpers/summary_check.py` checks each statement:

- every date, NOK amount and organisation number must occur in a claim the statement cites;
- the cited claim and evidence ids must exist in the envelope, and must be exactly the evidence of the cited claims;
- no trend or growth wording outside verbatim quotes.

| Set | Envelopes | Statements | Unsupported |
| --- | --- | --- | --- |
| Live 100, `6487205` | 100 | 2,586 | **0** |
| Live refresh 100, `6487205` | 100 | 2,586 | **0** |
| Live 911771098, `6487205` | 1 | 29 | **0** |
| Live 100 and its refresh, `7492f32` | 200 | 5,171 | **0** |
| Revision 1 live envelopes (1,200 + 400) re-summarised with the new synthesis | 1,600 | 41,437 | **0** |
| Measured V1-era envelopes (200), in the test suite | 200 | — | 0 |

### Live runs, same day, same command

The documented command, unchanged: no viewer flag, 8 workers, no `--bulk`, snapshots on, host audit. Input: the
committed 100-company smoke set, SHA-256 `80eb79e6…`. Raw reports are in `measurements/c300-revision-2026-10-17/`.

| | Revision 1 `05d7566` | Final `6487205` | Refresh of `6487205` |
| --- | --- | --- | --- |
| Envelopes / input order / terminal | 100 / yes / 100 completed | 100 / yes / 100 completed | 100 / yes / 100 completed |
| Validation; contract findings with every snapshot hash re-verified | passed; 0 (3,997 evidence entries) | passed; 0 (3,997) | passed; 0 (3,997) |
| Runtime / requests / third-party cost | 127.6 s / 769 / $0 | 122.3 s / 768 / $0 | 119.7 s / 770 / $0 |
| Websites / public footprint / hiring | 14 / 10 / 0 | 14 / 10 / 0 | 14 / 10 / 0 |
| Site-derived facts (website, profiles, news, jobs, careers) differing from Revision 1 | — | **0 companies** | — |
| Summaries with a period comparison / periods named not comparable | 0 / 0 | 90 / 3 | 90 / 3 |
| Employee count stated as unknown / shown as 0 | 0 / 0 | 84 / 0 | 84 / 0 |
| Viewer written by the documented command | no | yes, 1.38 MB | yes, 1.38 MB |
| Platform, Brave, NAV or wordpress.com hosts contacted | none | none | none |
| Change events against the previous run | — | — | **0** |

The runs went in this order on one machine: Revision 1, then `7492f32` (100, refresh, 911771098), then `6487205`. A test
loop ran at the same time as the `6487205` runs.
The `7492f32` runs (`new-*`) had one difference from Revision 1: 929336038 SJØLOFTET, whose robots.txt was unreachable
during that run. A re-run minutes later (`new-929336038-recheck/`) and the `6487205` run both publish the same Facebook
profile and careers page as Revision 1. That difference was live drift, not the change. It also surfaced the
pre-existing outage limitation listed under G.

A refresh across the upgrade, computed offline with `6487205`, takes Revision 1's profiles as the previous run. It
yields **0 events** against the `6487205` run, and only the two Sjøloftet "removed" events against the `7492f32` run
(`cross-version-refresh.json`).

### Preserved

- Company discovery is untouched: no change to candidate selection or the identity classification, and identity pages
  are fetched as before.
- The manager-content rule is unchanged. Brave and NAV are not added. The LLM stays off.
- One result per input, safe URL fetching (no platform host in any run), streaming and deadline behaviour,
  reporting-period provenance on every figure, and evidence hashes are all unchanged and re-verified above.

## G. Release

| Item | Value |
| --- | --- |
| Candidate code | `648720516ced747412817ecf1c38ce1de75296da` on `claude/awesome-sagan-m2lppu` (code commits `7492f32`, `6487205`); the docs/measurements commit on top is code-identical |
| Code changed | `src/norway_company_agent/{site_facts,site_research,claims,synthesis,viewer,cli}.py` |
| Tests added or changed | `tests/test_c300.py`, `tests/helpers/summary_check.py`, `tests/helpers/c12_replay.py`, `tests/test_synthesis.py`, `tests/fixtures/c300/911771098/`, `tests/fixtures/c12/build_fixtures.py` (`--into`) |
| Docs | this file, `docs/company-summary.md`, `docs/viewer.md`, `README.md`, `HANDOFF.md`, `docs/final-submission-manifest.md` (pointer) |
| Run command | unchanged: `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>`. It now also writes `out/envelopes.viewer.html`. |
| Dependencies | unchanged (`uv.lock`, `pyproject.toml`) |

**Before submitting (owner):**

1. Name the exact commit in the revision submission.
2. Make `claude/awesome-sagan-m2lppu` the GitHub default branch, or fast-forward `main` to the candidate. Otherwise
   a runner that clones the URL gets `5575d0c`, which has no summary or viewer (A1). This was not done here: it
   changes a branch other than the working branch.
3. Optionally mention the viewer path and the committed sample viewer in the submission email.

### Known limitations

- Which tree C300 processed is unknown (A1). The rubric behind synthesis and UX is unpublished, so the fixes address
  the confirmed defects, not a known scoring formula.
- Pre-existing, unchanged: when a registry-linked site's robots.txt is unreachable, the site record is still
  "available" with no page read. Its site-fact families then read "checked, nothing found", and a refresh reports
  "removed" rather than "unavailable". Seen once in about 1,700 company runs (Sjøloftet above). Left for a separate
  change to keep this revision small.
- A subdomain-hosted company site (for example `firma.wordpress.com`) can now publish a profile only through the
  legal-name gate. This is stricter by design; no measured company is affected.
- The 1,200-company run was not repeated on the new code. The last 1,200-company measurement is Revision 1's. The changed
  code paths were checked offline on all 1,600 Revision 1 envelopes (summary checker; the viewer rendered without
  error) and live on the 100.
- The viewer is about 20% larger than the last measured one (V1's 1.13 MB for 100 companies), because of the comparison
  cells and summary sections: 1.38 MB for 100 companies, and 16.2 MB for the 1,200 envelopes, which load in 1.2 s (desktop) and 1.5 s (phone) in headless Chromium.
