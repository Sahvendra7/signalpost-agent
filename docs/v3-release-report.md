# Signalpost V3 — release report

**Status.** Implemented and validated locally on 2026-11-01. **Not pushed, not submitted, not scored by Builderr.**
All accuracy figures are local engineering measurements, labelled `assistant_blind`. They are not Builderr scores.

**Code under test:** `dc96260d76aa089bc07e41382763832cb17d5ad5`, on branch `claude/awesome-sagan-m2lppu`, based on the
previously submitted `ff3b515`. The release candidate is the documentation commit that adds this report. It is
code-identical to `dc96260`. Its SHA is given in the hand-over message, because a commit cannot contain its own SHA.

## 1. Final specification

`docs/superpowers/specs/2026-11-01-signalpost-v3-design.md`:
- **Part A** — the independent review: 24 findings, DR-1 to DR-24.
- **Part B** — the final design, §B1 to §B15. It covers invariants I1–I10, the attribution package, news, jobs,
  history, audit, viewer, app, security and measurement.

## 2. Final plan

`docs/superpowers/plans/2026-11-01-signalpost-v3-implementation.md` covers phases 0–8, with files, interfaces, tests,
positive controls and rollback. Every deviation from the plan is logged in `docs/v3-changelog.md`.

## 3. Architecture and data flow

```
input rows ─► run_batch ─► research_company ─► official registry modules (unchanged)
                                   │
                                   └─► website discovery (unchanged) ─► site research ─► site_facts.extract_site_facts
                                                                                            │
         attribution/ (V3): one decision per question ─────────────────────────────────────┘
           names.py     legal name ↔ handle / domain relation (EXACT, EXACT_NEUTRAL, BRAND, EXTENDS, OTHER_ENTITY, UNRELATED)
           operator.py  who runs the site (self / manager / platform / section / other_entity / group_or_brand)
           social.py    publish or hold a profile, given relation × operator
           news.py      is this an article (item gate), is it news (taxonomy, bursts, evergreen, publisher), whose (subject)
           jobs.py      is it current (open / recently_posted / expired / undated), whose (employer)
                                   │
claims_from_profile (+ attribution, currency, site_role, first_seen) ─► envelope (+ run.code_version)
                                   │
refresh: baseline = --previous-envelopes │ run history (envelope + profile of the same run) │ --previous-profiles
   carry_forward (outages keep last value) → claim_changes → refine_removals (retracted / not_rechecked / removed)
   → refine_additions (first_observed) → stamp_first_seen (is_new only against a read baseline)
                                   │
streaming JSONL ─► report (+ code_version, baseline, new_items, checks, manual_audit, history) ─► viewer.html
                                   └─► history/<run>/ (atomic; manifest last; prune keeps newest two complete runs)

Local app (app/): ThreadingHTTPServer on 127.0.0.1 ─ security.py (Host / token / Origin / limits) ─ store.py (index of imported +
researched envelopes) ─ registry_search.py (one fixed Brreg endpoint or --bulk) ─ research.py (run_batch for 1 row, ≤2 live
threads incl. orphans, queue 20, 120 s) ─ viewer documents rendered by render_viewer(app=…)
```

Measurement tooling:
- `replay.py` / `scripts/replay_run.py` — replay captured bytes through any tree;
- `audit.py` / `scripts/audit_kit.py` — blind sampling, labelling checklist, Wilson-interval scoring;
- `provenance.py` — `code_version`.

## 4. Files changed (`git diff --stat ff3b515..HEAD`)

**New modules:**
- `src/norway_company_agent/attribution/` — `names`, `operator`, `social`, `news`, `jobs`, `decision`;
- `src/norway_company_agent/app/` — `security`, `store`, `registry_search`, `research`, `pages`, `server`;
- `history.py`, `provenance.py`, `replay.py`, `audit.py`;
- `scripts/serve.py`, `scripts/replay_run.py`, `scripts/audit_kit.py`.

**Modified:** `site_facts.py`, `site_research.py`, `claims.py`, `synthesis.py`, `refresh.py`, `pipeline.py`,
`contract.py`, `cli.py` and `viewer.py`.

**Tests:**
- New:
  - `tests/test_v3_*.py` (10 files, 113 tests);
  - `tests/helpers/app_harness.py`;
  - `tests/fixtures/v3/` (16 organisations).
- Deliberately changed, each logged in the changelog:
  - `tests/test_revision1.py` — two `sameAs` tests replaced; job dates made relative;
  - `tests/test_site_research.py` — relative dates;
  - `tests/test_c300.py` — phone comparison cards.

**Docs:**
- `docs/v3-changelog.md`, `docs/v3-accuracy.md`, `docs/search-app.md` and this report;
- `README.md`, `OUTPUT_CONTRACT.md`, `HANDOFF.md`, `docs/final-submission-manifest.md`;
- screenshots in `docs/screenshots/`.

**Measurements:** `measurements/v3-2026-11-01/` (accuracy) and `measurements/v3-release-2026-11-01/` (release runs).

In total: 44 source, script and test files, 4,977 insertions and 67 deletions. Everything else is fixtures,
measurements and docs.

## 5. Local commits (on `ff3b515`, oldest first)

| Commit | Content |
|---|---|
| `edba8f5` | Reviewed design specification and implementation plan |
| `49617b1` | Phase 0: code version stamping, replay tooling, audit kit, regression fixtures |
| `9c58a8d` | Phase 1: attribution package — site operator, handle relations, social decisions |
| `35d3ad8` | Phase 2: item-level news classification, publication dates, subject |
| `a852bb3` | Phase 3: job currency, employer resolution, careers pages |
| `ca34ef5` | Phase 4: dev-audit fixes |
| `c989cb2` | Replay: split captured profiles on newline only |
| `6efd3cd` | Phase 4: fixes from the first held-out evaluation |
| `b5199fe` | Phase 4: fixes after the second held-out evaluation |
| `54620e7` | Phase 4: accuracy measurement (including the failed gates) |
| `7a73d72` | Phase 5: run history, published-envelope baselines, retractions, first-seen, report blocks |
| `84734c3` | Phase 6: viewer — trust panel, evidence inspector, What's New, phone comparison, plain labels |
| `730ccfe` | Phase 7: local search application with on-demand research |
| `7903373` | Release validation: contract fields, handoff, README, release-run scripts |
| `7c2597f` | Pin the 911771098 blog control at 19 and log the false negative |
| `360f08c` | Release fix: `first_observed`; omitted measurement artefacts added |
| `907f42d` | Release fix: news absence reason states withheld candidates |
| `dc96260` | Release fix: the history baseline supplies its profiles (outage carry-forward); **code under test** |
| *(this commit)* | Final docs and release measurements; code-identical to `dc96260` |

## 6. Full test results

| Where | Code | Result |
|---|---|---|
| Working tree, 5 consecutive runs | `730ccfe` | 5 of 5: 468 passed, 172 subtests, 0 failed, 0 skipped |
| Working tree | `dc96260` | 474 passed, 172 subtests |
| Clean room (fresh clone, empty uv cache, `uv sync --locked`), 3 consecutive runs | `dc96260` | 3 of 3: 474 passed, 172 subtests |
| Baseline, for reference | `ff3b515` | 361 passed, 91 subtests |

V3 test files:

| File | Tests |
|---|---|
| `app` | 12 (+2 subtests) |
| `app_security` | 18 (+33) |
| `attribution` | 14 (+40) |
| `audit` | 4 |
| `history` | 11 |
| `jobs` | 11 (+4) |
| `news` | 16 |
| `provenance` | 4 |
| `regressions` | 19 |
| `viewer` | 4 (+2) |

## 7. Baseline versus V3

The method is in `docs/v3-accuracy.md`. In short:
- captured live bytes from `ff3b515` are replayed through both versions;
- every published unit is labelled (a census), blind to which version published it;
- precision has Wilson 95% intervals;
- retention (correct baseline units V3 keeps) is the recall proxy.

**Held-out result** — fresh60b, evaluated once, rules frozen at `6efd3cd`:

| Category | Base precision | V3 precision (95% CI) | V3 retention | Gate |
|---|---|---|---|---|
| Social | 83.8% | 100% (50/50; 92.9–100%) | 87.7% | passed |
| News | 73.2% | 85.0% (73.9–91.9%) | 98.1% | **failed** (< 90%) |
| Careers | 66.7% | 88.9% (n=9) | 80.0% | **failed** (small n) |
| Jobs | 1 published, wrong | 0 published | — | — |

V3 introduced 0 new errors. The first held-out set (fresh60, frozen at `ca34ef5`) failed: social retention 62.3% and
news precision 19.8%. It became a development set.

**Final rules, pooled over all four sets.** These are development data, not held-out:

| Category | Base | V3 | Errors removed / introduced |
|---|---|---|---|
| Social | 86.1% | 97.9% | 20 / 0 |
| News | 44.2% | 95.1% | 156 / 0 |
| Careers | 60.0% | 95.8% | 15 / 0 |

Replaying all four sets through `dc96260` publishes exactly these units.

**Live (`dc96260`, fixed 100):**
- 100/100 completed in 137.3 s with 762 requests. `ff3b515` took 132.8 s with 757 requests on the same input that
  morning (live web, so not a controlled comparison);
- $0;
- published site facts: website 14, social 12, news 30, careers 4.

## 8. Per-category precision and recall

The tables in §7 give precision with intervals, retention (the recall proxy), and errors removed and introduced.
- **True recall cannot be measured:** there is no ground truth of all profiles, articles and jobs.
- **Jobs cannot be measured:** the baseline published one advertisement in 300 companies, and it was wrong. Job
  behaviour is pinned by synthetic tests instead:
  - expired;
  - open;
  - recently posted;
  - undated;
  - another employer;
  - recruiter job board;
  - news archive;
  - shared site.

## 9. Affected-company results

Fixture replays, `tests/test_v3_regressions.py` (19 tests, all passing), and live runs on `dc96260` on 2026-11-01:

| Company | Builderr-reported problem | V3, live |
|---|---|---|
| 911771098 Hans Jørgen Sandnes AS | A WordPress LinkedIn page reported as the company's | The LinkedIn is not published (held as `ambiguous`). 19 blog posts kept (20 at `ff3b515`; "Du store verden" is lost to the second-person title rule, a logged false negative). The claim reproduces on `main` (`5575d0c`) and `05d7566`, not on `ff3b515`. |
| 983181732 Tyin Alpint AS | Tyin Filefjell's profiles attributed to it | 0 profiles (6 held). The site is marked `operated_by_other_company` (org. 930182451); jobs `not_applicable`. Against the old published envelopes, the 3 profiles are `retracted`, with the rule. |
| 995596970 Bergknapp AS | Grasrota via `sameAs` | Its own 3 profiles kept (Facebook, Instagram, LinkedIn); Grasrota not published. |
| 980932834 Bartec AS | Group profiles and magazine | 0 profiles; site `group_or_brand_site`; 37 group news entries withheld, and the reason says so. |
| 995159406 BK Bygg AS | 10 imported "project" posts as news | 0 news (bulk-entry burst); its own 2 profiles kept. |
| Jobs (3 of 5 wrong) | Expired, recruiter and other-employer jobs | `validThrough` is parsed correctly (it was inverted). Expired, undated, other-employer and recruiter-board jobs are held. Live sets publish no job ad, so no live job case was available. |
| News (22 of 111 wrong) | Project pages, default posts, listings, group news | Item gate, taxonomy, bursts, publisher and evergreen rules: 156 baseline errors removed, 0 introduced (pooled). |

Positive controls kept (fixture tests):
- Kilis Hockey: 10 news items;
- Birralee: 20;
- Grønsand: 15, plus 2 profiles;
- Beredt: 6 or more;
- Bergknapp: 3 profiles;
- BioMar: `biomarnorge`;
- careers pages: Birralee, Bjelland;
- all C300 and Revision 1 tests.

## 10. Security tests

`tests/test_v3_app_security.py` (18 tests, 33 subtests) and `tests/test_v3_app.py`. All pass:
- **Requests:**
  - Host header not loopback → 421;
  - POST without, or with a wrong, token / Origin / `Sec-Fetch-Site` → 403; non-JSON → 415; body over 4 KB → 413;
  - extra fields or a non-string org → 400; nothing starts.
- **Search input:** URL, domain, e-mail, path, scheme and drive inputs → 400 `url_not_allowed`, with **no registry
  call**. "A/S" names, "St.Olav" and initials are accepted. Bad check digits → 400.
- **Paths:** traversal, malformed job ids and hashes → 400/404; unindexed snapshot → 404; snapshot path outside the
  roots → 404.
- **Snapshots** are served as a `text/plain` attachment with `nosniff` and CSP `sandbox`. Verified live: the bytes hash
  to the cited content hash.
- **Limits:**
  - research slots ≤ 2, including orphaned threads;
  - queue overflow → 429;
  - research 10/min and search 30/min → 429;
  - 32 concurrent requests → 503;
  - a slow client is cut off within 10 s.
- **Other:**
  - 500 responses carry no traceback or internal text;
  - binding to a non-loopback address needs `--allow-remote`;
  - the app source has no `subprocess`, `os.system`, `eval` or `exec`;
  - the search page CSP uses script and style hashes (no `unsafe-inline`); no CSP violations in the headless runs.

## 11. Search app usage

```bash
uv sync --locked
uv run python scripts/serve.py --data-dir out/app \
  --envelopes out/envelopes.jsonl --snapshot-dir out/snapshots      # both optional; repeatable
# open http://127.0.0.1:8765/
```

How to use it:
- **Search** by name or organisation number.
- **Open a profile.** It is the viewer: *Inspect* on any fact, held-back items, unknowns, What's New.
- **Compare** 2–4 companies.
- **Research this company** for a company outside the dataset: about a minute, $0, LLM off. You see the stage and
  elapsed time and can *Cancel*. The result is completed, partial (failed sources named) or failed (with the reason).

Full guide: `docs/search-app.md`. Verified live: registry search, on-demand research of 983181732 (8 s, completed),
snapshot download.

## 12. Desktop and mobile UX

Headless Chromium at 1366×820 and 390×844 (`tests/test_v3_viewer.py`, `tests/test_v3_app.py::BrowserFlow`,
`tests/test_c300.py`). For both viewports:
- no page errors, no request leaving the page or app, no CSP violations;
- no horizontal page scroll in the list, profile, inspector, What's New, trust panel, or comparison of 2 and 4;
- the inspector opens and closes;
- the search → research → open → compare flow completes.

Screenshots (`docs/screenshots/`):
- `v3-viewer-*` — inspector, What's New, comparison of 4, on desktop and phone;
- `app-search-*` — running, done and local results;
- `app-live-*` — live Grønsand data: search and inspector with the captured-copy link.

## 13. Cost and dependency audit

| Check | Result |
|---|---|
| `git diff ff3b515 dc96260 -- pyproject.toml uv.lock` | empty: no new dependency |
| New imports | standard library plus the existing `bs4`. `requests` in `sys.modules` comes from the existing `tldextract`. |
| LLM | `norway_company_agent.llm` not imported in a default run; no LLM SDK loaded; no `llm` block in the report |
| Third-party cost | $0 in every live and replay run |
| Outbound hosts (live 100 + refresh) | 196 hosts: Brreg and company sites; 0 LinkedIn, Facebook, Instagram, YouTube, X or TikTok; no Brave, no NAV |
| App | standard library only; one fixed registry endpoint; no subprocess |

## 14. Remaining limitations and risks

1. **News precision gate failed on held-out data** (85.0%, below the 90% target). The post-fix 95.1% is measured on
   data the rules were tuned on. A third held-out evaluation has not been run.
2. **Labels are the assistant's**, not the owner's, although made blind to which version published each item. The
   owner can re-label with `scripts/audit_kit.py` (`--labeller-kind owner`).
3. **Jobs** cannot be measured from real data, because published advertisements are too rare.
4. **Known V3 errors:**
   - ASAK AS publishes ASAK MILJØSTEIN AS's profiles (telling them apart needs a registry lookup);
   - Ashtead's global LinkedIn;
   - some advice posts without advice-like titles.
5. **Known V3 false negatives:**
   - the second-person title rule (911771098: 19 of 20 posts; in the audit it removed 10 wrong and 3 correct items);
   - social retention 87.7% on held-out data.
6. **App re-check of imported companies.** A company imported with `--envelopes` has no stored profile, so a source
   outage on its first re-check can show as removed. Later re-checks are protected.
7. **`first_observed` depends on the site-research module state.** A partially read site (some pages failed) still
   counts as read.
8. **`main` is still the old `5575d0c`.** A runner that clones without a commit runs the tree with the WordPress
   LinkedIn bug. Name the commit in the submission.
9. **Website discovery is unchanged:** 14 of 100 have a verified website. Recall is bounded by it.
10. **The app is single-user and unauthenticated.** It is safe only on loopback.
11. The viewer is about 14 KB per company (1.4 MB for 100), as before.
12. **Process note.** The Phase 4 measurement artefacts were first committed without their inputs, envelopes and
    labels, because `.gitignore` excluded them. This was corrected in `360f08c`.

## 15. Recommended commit for the next Builderr revision

The documentation commit that adds this report, at the head of `claude/awesome-sagan-m2lppu`. It is code-identical to
`dc96260d76aa089bc07e41382763832cb17d5ad5`; its full SHA is in the hand-over message.

Before submitting:
- push the branch, after the owner's review;
- either name the exact commit in the submission, or make the branch the default;
- decide whether the failed news held-out gate (limitation 1) is acceptable.
