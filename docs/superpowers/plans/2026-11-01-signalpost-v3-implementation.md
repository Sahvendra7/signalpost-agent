# Signalpost V3 — implementation plan

Design: `docs/superpowers/specs/2026-11-01-signalpost-v3-design.md`. All section references (§B…) point there.

Branch `claude/awesome-sagan-m2lppu`, starting at `ff3b515`. Local commits only; nothing is pushed until the owner has
reviewed the changes.

Conventions:
- Run tests with `uv run --with pytest pytest -q`.
- Measurement work lives in `/tmp/…/scratchpad/m/`. Committed results go under `measurements/v3-2026-11-01/`.
- Every deliberate behaviour change is listed in `docs/v3-changelog.md`, together with the test assertion it replaces.

## Phase 0 — Baseline and groundwork

| Step | Files | Detail | Test |
|---|---|---|---|
| 0.1 | (git) | Fast-forward the branch to `ff3b515`; verify it is clean | `git log -1` = `ff3b515` |
| 0.2 | scratchpad | Baseline live runs from a pristine `git archive ff3b515` tree, with snapshots, for midsize40, fresh60 and smoke100. fresh60 outputs are **not inspected** | `stdout.txt` exit 0, 0 contract findings |
| 0.3 | `src/norway_company_agent/provenance.py` (new) | `code_version(root=None) -> dict`, cached. Fields: `source_sha256`, `package_version`, `git_commit`, `git_dirty` (fixed-argv `subprocess.run`, no shell, timeout 5, `.git` must exist; errors → null) | `tests/test_v3_provenance.py`: deterministic hash; a hash change when a src file changes (tmp copy); no `.git` → nulls; git present → 40-hex commit |
| 0.4 | `pipeline.py` (`run_batch` adds `run.code_version` to each envelope through `_research_envelope` and `batch_report`), `contract.py` (optional shape check) | Additive | contract test: envelope with and without `code_version` validates; malformed → finding `invalid_code_version` |
| 0.5 | `scripts/replay_run.py` (new), `tests/helpers/replay.py` (new) | `replay_run.py --profiles P --snapshots S --input I --output … --run-id …` builds the manifest in memory (the same logic as `build_fixtures.py`; that logic moves into `tests/helpers/replay.py::manifest_from_run`, and `build_fixtures.py` imports it) and calls `cli.main` with injected `fetcher`, `site_fetcher`, `website_fetcher` and `resolver`. Unknown URLs → 404, as the C12 replay does | Replaying the baseline twice gives identical claims; replaying the C300 fixture reproduces `test_c300` results |
| 0.6 | `tests/fixtures/v3/<org>/` (new) | Captured from the baseline runs with `build_fixtures.py --into tests/fixtures/v3`. Defect cases: 983181732 Tyin, 995596970 Bergknapp, 980932834 Bartec, 937843860 BioMar, 995159406 BK Bygg, 993231150 Bergen Rørteknikk, 996605833 Betonmast Oslo, 980995151 BDT Viken, 933164896 Best Work, 975387011 Crux, 984560443 Bjelland, 995726742 Bemex. Positive controls: 875606662 Kilis Hockey, 919378875 Grønsand, 936269044 Birralee, 916303122 Beredt. The existing c300/c12 fixtures cover 911771098 and Granne | Each manifest's note names its defect or control |
| 0.7 | `tests/test_v3_regressions.py` (new) | One test per §1 defect row, written red first, replaying fixtures through `run_batch`; positive-control tests green | Red on the baseline for defects; green for controls |
| 0.8 | `src/norway_company_agent/audit.py` (new), `scripts/audit_kit.py` (new) | `units(envelope)`, `sample(...)`, `wilson(c, n)`, `score(...)`, `render_checklist(...)` (§B9) | `tests/test_v3_audit.py`: Wilson values against known numbers; blind shuffle hides the arm; diff includes every changed unit; score refuses unlabelled rows; retention arithmetic |
| 0.9 | `docs/v3-changelog.md` (new) | Starts the behaviour-change log | — |

**Commit:** "V3 phase 0: code version, replay tooling, regression fixtures, audit kit".

**Acceptance:**
- Full suite green, apart from the new red defect tests. Those are marked `expectedFailure` until their phase lands, so
  the suite stays green and each defect flips to a pass in its phase.
- `code_version` appears in envelopes and the report.

## Phase 1 — Entity resolution and social accuracy

| Step | Files | Interface |
|---|---|---|
| 1.1 | `src/norway_company_agent/attribution/__init__.py`, `decision.py` | `Decision(accepted, code, basis, signals=())` |
| 1.2 | `attribution/names.py` | `LegalName(name, municipality=None, post_town=None)`: `.tokens`, `.compact`, `.phrase_re`, `.brands`, `.qualifiers`, `.domain_derived(label) -> bool`. `handle_of(platform, url) -> str`. `handle_relation(legal, platform, url) -> Relation(kind, rest)`. Constants `NEUTRAL`, `DISTINGUISHING`, `GENERIC_BRANDS`, `COUNTIES`, `REGIONS` |
| 1.3 | `attribution/operator.py` | `stated_org_numbers(text) -> list[(org, span)]`; `SiteOperator(kind, code, basis, signals, operator_org)`; `assess_operator(profile, site_url, website_value, pages, feeds=None, identity_class=None) -> SiteOperator` (§B5) |
| 1.4 | `attribution/social.py` | `decide_profile(legal, relation, operator, *, domain_brand, org_sameas) -> Decision` (table in §B4) |
| 1.5 | `site_facts.py` | `extract_site_facts(profile, pages, feeds=None, operator=None)`. Computes the operator if `None`; `social_identity` is replaced by `attribution.social`; records `attribution` on profiles; `SiteFacts.operator` |
| 1.6 | `site_research.py` | `_enrich` passes `website_value` and `identity_class` for the operator; `apply_site_facts` keeps the manager logic and adds an `other_entity` hold (profiles, jobs and careers page held; news only `item_names_entity`); stores `operator` in the site record |
| 1.7 | `claims.py` | Social claims gain `attribution: {code, basis}`; the website claim gains `site_role`/`operated_by` from the site record when present |
| 1.8 | `synthesis.py` | Public footprint: "operated by X (org nr)" or "a group/brand site" in plain words, citing the website claim |
| 1.9 | tests | `tests/test_v3_names.py` (relation table: ≥ 30 cases, including every handle seen in the diagnosis); `tests/test_v3_operator.py` (org-number extraction with grouped digits, mod11, imprint context; each operator kind; a holding-footer false-positive guard); the fixture regressions flip to pass |

**Behaviour changes (logged):**
- `test_revision1.py::test_domain_name_must_begin_or_end_the_handle`: `handballnorge` for "BALLSPORT DRIFT AS"
  becomes ambiguous. Assertion replaced, with the reason.
- Any `sameAs`-only acceptance now requires a name-compatible handle.

**Acceptance:**
- Tyin profiles 3 → 0, website kept with `site_role` and `operated_by`.
- Bergknapp: Grasrota 3 → 0, own 3 kept.
- Bartec group handles → 0.
- BioMar: `@BioMarGroup` held, `biomarnorge` kept.
- Grønsand 2 kept; Birralee kept; the 911771098 C300 tests pass.
- Full suite green.

**Commit:** "V3 phase 1: attribution package — site operator, handle relations, social decisions".

## Phase 2 — News accuracy

| Step | Files | Detail |
|---|---|---|
| 2.1 | `site_facts.py` | `feed_items` returns `categories`; `html_items` picks `<time>` per §B6 (published preferred, updated ignored); the item `ctx` carries `feed_url` and `is_main_feed` |
| 2.2 | `attribution/news.py` | `NON_ARTICLE_SEGMENTS`, `DEFAULT_POSTS`, `PROJECT_CATEGORIES`, `classify_item(item, page, ctx) -> Decision`, `burst_keys(items) -> set`, `subject_of(item, legal, page_text) -> "THIS"|"SIBLING"|"UNSTATED"` |
| 2.3 | `site_facts.extract_site_facts` | After `validate_activity`, apply `classify_item`, then the subject policy for the operator kind; record rejections by code; keep `candidate_keys` and `rejected` for Phase 5 |
| 2.4 | `site_research.apply_site_facts` | Manager and other_entity news policy unchanged in effect (the subject THIS replaces the manager-only path, using the same `item_names_entity` scope) |
| 2.5 | tests | `tests/test_v3_news.py`: each rejection code with a minimal page; `<time class=updated>` first → published chosen; plain-slug WordPress feed item kept; burst of 10 within 3 minutes rejected, 3 kept; the Betonmast category subject; fixtures: BK Bygg 0, Bergen Rørteknikk 0, BDT and Best Work "Hello world" 0, Crux `.jpg`/contact 0, Bjelland portfolio and category 0, Bergknapp `/prosjekter/` 0, Bartec group 0, Betonmast only THIS. Controls: 911771098 posts (C300 test), Kilis 11, Birralee, Beredt articles kept |

**Behaviour changes logged:** existing tests asserting homepage `<article><time>` cards with non-news URLs are reviewed
one by one; only cards that fail §B6 change.

**Commit:** "V3 phase 2: item-level news classification, published dates, subject".

## Phase 3 — Job accuracy

| Step | Files | Detail |
|---|---|---|
| 3.1 | `site_facts.py` | `parse_deadline(value)` (≤ 18 months ahead); `job_postings` reads `validThrough` through `parse_deadline` and captures `hiringOrganization.name`; `job_listings` captures the employer label and the deadline through `allow_future` (already) |
| 3.2 | `attribution/jobs.py` | `currency(job, run_date) -> (state, basis)`; `employer(job, legal, operator, is_recruiter) -> Decision`; `decide_job(job, page, legal, operator, is_recruiter, run_date) -> Decision`; generic-title extensions |
| 3.3 | `site_facts.extract_site_facts` | Jobs go through `decide_job`; a JSON-LD JobPosting on a news or archive page is rejected; the run date is injectable (`now=`) for tests |
| 3.4 | `site_research._enrich` | `CAREER_HINTS` becomes segment and whole-word matching; the careers page must pass `is_careers_page` and must not be in the service vocabulary (§B7) |
| 3.5 | `claims.py`, `synthesis.py` | The job claim carries `currency: {state, basis}` and `attribution`; `not_available` reasons name the held codes; summary wording for the careers page and for `recently_posted` |
| 3.6 | tests | `tests/test_v3_jobs.py`: expired out; future `validThrough` kept with its value; the 2019 posting out; another `hiringOrganization` out; the target as `hiringOrganization` on a recruiter site kept; unstated employer on a recruiter site held; JobPosting on a news page out; listing with a passed deadline out; undated listing → `currency_unknown`; posted 10 days ago with no expiry → `recently_posted`; Bemex fixture; Best Work and Beredt careers-page fixtures; the Granne test unchanged |

**Commit:** "V3 phase 3: job currency, employer resolution, careers page".

## Phase 4 — Measurement gate

1. Freeze the rules: commit hash H.
2. Replay the baseline (`ff3b515` tree) and V3 (H) on the captured midsize40 and smoke100 runs, with
   `scripts/replay_run.py`.
3. Run `audit_kit sample --envelopes v3 --baseline base` per set, arms blind; label every unit (assistant, blind);
   score.
4. Examine every lost correct unit. If a rule is unjustified, fix it, re-freeze and repeat **on the dev sets only**.
5. Run the held-out evaluation **once**: replay fresh60 through the baseline and the frozen V3; label blind; score.
   Report whatever results.
6. Write `docs/v3-accuracy.md` and `measurements/v3-2026-11-01/` (inputs with SHA-256, replay outputs gzipped, labels
   CSV, `audit-results.json`/`.md`).

**Acceptance:** the §B13 gates. If a gate fails on held-out data, it is reported as failed, together with the cause and
the follow-up. It is not hidden.

## Phase 5 — Evidence history and audit reporting

| Step | Files | Detail |
|---|---|---|
| 5.1 | `src/norway_company_agent/history.py` (new) | `write_run(history_dir, run_id, envelopes, profiles, report, complete) -> Path` (temp dir + manifest last + `os.replace`); `prune(history_dir, keep)`; `load_baselines(history_dir, orgs) -> {org: (envelope, run_meta)}`; `read_envelopes(path)` |
| 5.2 | `cli.py` | `--previous-envelopes`, `--history-dir`, `--no-history`, `--history-keep`, `--audit-results`. History is written after the report is durable and before the viewer; it never fails the run (errors go to `report.history.reason`) |
| 5.3 | `pipeline.py` | `run_batch(..., previous_envelopes=None)`, passed to `_research_envelope`; there the refresh uses `claim_changes_published` when a baseline envelope exists, else the existing path |
| 5.4 | `refresh.py` | `claim_changes_published(baseline_claims, baseline_evidence, current_claims, current_evidence, *, site_record, carried, unverified)` produces added, changed, removed, retracted, not_rechecked, unverified and unavailable (§B8). `stamp_first_seen(current_claims, baseline_claims, run_id, now, has_baseline)` |
| 5.5 | `site_facts.py`, `site_research.py` | `candidate_keys`, `rejected` and `pages_read` stored in the site record (capped) |
| 5.6 | `contract.py` | Optional validation: `change_type` in the allowed set; `first_seen_at` ISO when present |
| 5.7 | `pipeline.batch_report` | `code_version`, `new_items`, `checks` (gate codes), `manual_audit` |
| 5.8 | tests | `tests/test_v3_history.py`: atomic write (kill simulated: a temp dir is never a baseline); prune keeps the newest two complete runs and never touches unmarked dirs; per-org baseline skips the org's partial envelope. `tests/test_v3_changes.py`: Revision 1-style envelope with the WordPress LinkedIn → `retracted` with a rule code; Tyin baseline → V3 gives 3 `retracted`; item gone from a re-read page → `removed`; page not read → `not_rechecked`; outage → `unavailable` only; re-run on the same data → 0 events; `first_seen` carried; `is_new` only with a baseline. The existing refresh tests stay green |

**Commit:** "V3 phase 5: run history, published-envelope changes, retractions, first-seen, report blocks".

## Phase 6 — Viewer

| Step | Files | Detail |
|---|---|---|
| 6.1 | `viewer.py` | `LABELS` table; projection adds `attribution`, `first_seen`, `is_new`, `currency`, `held` (ambiguous profiles and held items with codes, from envelope claims and `attribution` notes), `site_role`; `render_viewer(envelopes, report, *, title, app=None)` |
| 6.2 | `viewer.py` TEMPLATE | Trust panel; evidence `<dialog>`; What's New tab; not-attributed section; phone comparison cards (CSS grid at ≤ 700 px, sticky chips); news show-10/show-all; app links (search, snapshot) |
| 6.3 | tests | `tests/test_viewer.py` extended; headless Chromium (existing harness) at 1366×820 and 390×844: open, inspector, What's New, compare 2 and 4 on phone with no horizontal scroll, no page errors, no network; `innerHTML` absent; size ≤ +20% per company on smoke100 |

**Commit:** "V3 phase 6: viewer — trust panel, evidence inspector, What's New, phone comparison, plain labels".

## Phase 7 — Local search application

| Step | Files | Detail |
|---|---|---|
| 7.1 | `app/__init__.py`, `app/security.py` | `valid_org`, `valid_job_id`, `valid_sha`, `classify_query(q) -> ("number"|"name", normalised) | raises BadRequest`, `check_host(host, port)`, `check_post(headers, token, origin)`, `RateLimiter(rate, per)` |
| 7.2 | `app/store.py` | `Store(data_dir, imports=[...], snapshot_dirs=[...])`: `.search(q)`, `.latest(org)`, `.runs(org)`, `.add_research(org, run_id, envelope, profile)`, `.snapshot_path(sha)`, `.all_latest()` |
| 7.3 | `app/registry_search.py` | `RegistrySearch(fetcher=fetch_json, bulk=None)`: `.search(q) -> list[{org, name, form, municipality, deleted}]`, with a cache |
| 7.4 | `app/research.py` | `ResearchManager(store, run=run_batch, max_live=2, queue=20, deadline=120)`: `.submit(org) -> job`, `.get(id)`, `.cancel(id)`; stage derivation from the progress profile |
| 7.5 | `pipeline.run_batch` | Optional `progress` dict parameter (additive; default internal) |
| 7.6 | `app/pages.py`, `app/server.py`, `scripts/serve.py` | §B11 routes, §B12 controls |
| 7.7 | tests | `tests/test_v3_app_security.py` (Host 421, missing or wrong token 403, cross-origin 403, URL-like query 400 with no outbound call, traversal 400/404, unindexed snapshot 404, snapshot headers, body > 4 KB 413, rate limit 429, research slots honoured with slow fake research). `tests/test_v3_app.py` (offline end-to-end with C300/v3 fixture fetchers: search local, search registry (fake), research → completed, partial (fake site failure), failed (unknown org 404), company page renders the viewer, compare, What's New, cancel). Headless browser flow on desktop and phone |
| 7.8 | docs | `docs/search-app.md`; README "Search a company" section |

**Commit:** "V3 phase 7: local search application with on-demand research".

## Phase 8 — Release validation

1. Full suite 5× (plus 1 clean-room run in a fresh clone with an empty uv cache, `uv sync --locked`).
2. Live V3 smoke100 with host audit (no platform hosts), and a refresh against it (0 false events). Live reproductions:
   911771098, 983181732, and Bergknapp, Bartec, BK Bygg.
3. App: live search by name and number; on-demand research of a company outside the dataset; desktop and phone
   screenshots.
4. Cost and dependency audit: `git diff ff3b515 -- pyproject.toml uv.lock` is empty; report cost $0; LLM not imported
   (`sys.modules` check).
5. Docs: README, `OUTPUT_CONTRACT.md` additive fields, `docs/v3-changelog.md`, `docs/v3-accuracy.md`,
   `docs/search-app.md`, `HANDOFF.md`, `docs/final-submission-manifest.md` (V3 candidate section).

**Commit:** "V3 release validation: measurements, docs, manifest".

## Rollback

- Each phase is its own commit series; `git revert` a phase's commits to undo it.
- The contract is additive, so earlier consumers keep working.
- `ff3b515` remains the previous candidate on `claude/c300-refresh-fix`.

## Positive controls (must stay published)

| Company | What must stay |
|---|---|
| 911771098 | 20 blog posts and the website |
| Kilis Hockey | 11 feed posts |
| Grønsand | 2 profiles and 15 posts |
| Birralee | profiles and posts |
| Beredt | its own profiles and dated articles |
| Bergknapp | its own 3 profiles |
| BioMar | `biomarnorge` |
| Granne | careers page plus honest `not_available` hiring |
| C300 / Revision 1 tests | all of them, unchanged unless logged |
