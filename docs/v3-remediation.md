# V3 pre-release remediation pass (2026-11-01)

Baseline: `v3-candidate-1` (local tag on `4549f3a`; code `dc96260`), unchanged and reproducible.

## R1, R2 — ASAK AS and ASHTEAD TECHNOLOGY AS (social)

**Reproduced** from the captured fresh60 bytes, which are now the fixtures `tests/fixtures/v3/961592097`,
`980281310` and `995284766`. fresh60 has been a development set since the first held-out evaluation.

| Company | Published at `dc96260` | Cause |
|---|---|---|
| ASAK AS (961592097) | `facebook.com/asakmiljostein`, `instagram.com/asak_miljostein` | The handle is "asak" plus "miljøstein" (`EXTENDS`), accepted on asak.no, which is named after the company. asak.no is shared with ASAK MILJØSTEIN AS (980281310) and itself writes "Asak Miljøstein AS". |
| ASHTEAD TECHNOLOGY AS (995284766) | `linkedin.com/company/ashtead-technology` | The registry website is a page of the global group's `ashtead-technology.com` (operator `section`). An exact-name handle was accepted on shared sites, but the group bears the same name. |

**Two general rules** in `attribution/social.py`, fed by `site_facts.extract_site_facts`:

1. `handle_names_other_company_on_site`.
   - A `BRAND` or `EXTENDS` handle is held when it spells, exactly, a company name that the website itself writes with a
     legal form ("Asak Miljøstein AS"), and that name is not the target's. `names.named_entities` reads such names
     from the captured pages.
   - The other company keeps its profiles: ASAK MILJØSTEIN AS's are `handle_exact`.
2. `group_name_handle_on_{section|group_or_brand}_site`.
   - On a site run by a larger organisation (`section` or `group_or_brand`) whose registered domain is named exactly
     like the company, a bare exact-name handle (no legal form, no Norway marker) is held: it is the organisation's
     account.
   - `biomar-norge` and `bergknapp-as`-style handles are unaffected.
   - Platform-hosted sites (`platform`) are excluded, because a tenant's exact-name handle there is its own.

**Effect on every published social unit in the four existing sets** (replay, `dc96260` against the working tree):

| Set | Lost | Gained |
|---|---|---|
| fresh60 | 2 ASAK profiles, 1 Ashtead LinkedIn (all labelled incorrect) | 0 |
| midsize40 | `instagram.com/beredtinkludering` | 0 |
| smoke100 | — | — |
| fresh60b (consumed held-out; measured only, not tuned on) | — | — |

**Label correction.** The Beredt profile had been labelled "correct, own sub-brand". It belongs to BEREDT INKLUDERING
AS (934470222), a separately registered company that beredt.no itself calls one of "to selskaper" (two companies). The
dev-audit label is corrected, with this evidence, in
`measurements/v3-remediation-2026-11-01/label-corrections.csv`. The control in
`test_v3_regressions.py::SocialAttribution::test_controls_keep_their_profiles` is updated to match.

**Tests:**
- `test_v3_regressions.py::SocialAttribution::test_asak_does_not_take_the_profiles_of_asak_miljostein` — ASAK held,
  ASAK MILJØSTEIN keeps both;
- `test_v3_regressions.py::SocialAttribution::test_ashtead_norwegian_as_does_not_take_the_global_linkedin`.

## R5 — first re-check of an imported envelope during a source outage

**Cause.** Outage carry-forward needs the previous *profile*. An envelope imported into the app, or given as
`--previous-envelopes` alone, has none. A source that failed in the re-check therefore turned the published values
into `removed` events.

**Change.** `refresh.carry_forward_from_envelope`, used only when the baseline is a published envelope without a
profile:
- For each source that failed in this run (`source_error`, `blocked`, `not_fetched`, missing, or site research not
  re-checkable because the website module failed) **and** completed in the baseline, the baseline's available claims
  from that source are kept, with their evidence entries, marked `carried_forward` and with `last_verified_at`.
- This run's non-available claims for those fields are dropped.
- The module state is `carried_forward`, and one `unavailable` event is emitted per source.
- Only values the baseline published are kept; nothing is invented.
- When a profile exists, the profile path is used as before.

**Tests.** Both fail without the fix:
- `test_v3_app.py::ImportedRecheckOutage` — an imported company, re-checked while the website and site research are
  down: no `removed`, `unavailable` present, website and news retained, contract valid.
- `test_v3_history.py::EnvelopeOnlyBaseline` — `--previous-envelopes` alone through an outage: only `unavailable`, and
  the same published facts.

A guard test checks that a source that does answer still reports real removals.

## R4 — careers (held-out fresh60b, exact counts)

These are careers *pages*. A careers page is a company's page about working there; a **job advertisement** is a single
vacancy. Job advertisements are a separate category: on fresh60b the baseline published 1 (incorrect: an
applicant-tracking system's list of all adverts, `candidate.webcruiter.com`), and V3 published 0. So **job-ad precision
cannot be measured on fresh60b** (0 published), and none of the figures below are job-ad accuracy.

**Careers pages, V3 at the freeze (`6efd3cd`), evaluated once.** 12 published: 8 correct, 1 incorrect, 3 unsure.

| Unit | Label |
|---|---|
| Granitor Electro `/jobbe-i-granitor-electro`, Grenland Brann og Redning `/jobb-hos-oss/`, Grong Sparebank `/Jobb-hos-oss`, Alf I. Larsen `/ledige-stillinger`, Bauta Regnskap `/jobbe-hos-oss/`, Green Mountain `/about-us/careers/`, Granavolden `/om-oss/jobbe-hos-oss/`, Basis.no `/company/careers` | correct (8) |
| **Barneombudet `/for-barn-og-unge/dine-rettigheter/penger-og-jobb`** | **incorrect**: a children's-rights page about money and work |
| GMC Yard, GMC Power & Automation (`gmc.no/om-oss/karriere`, shared by group companies); Gratangen kommune `/jobbe-og-bo` ("work and live") | unsure (3) |

- **Precision:** 8 / 9 decided = 88.9%, Wilson 95% CI 56.5–98.0%.
- **Retention** (recall proxy): 8 of the baseline's 10 correct pages = 80.0%.
  - Grane kommune was lost by a bug fixed in `b5199fe`: a municipal `/tjenester/` path was taken as a service page.
  - GMV `/karriere` was lost because V3 requires the careers page to have been read, and it was not.
    - In replay, the baseline capture never fetched it: the old code published the link unread.
    - In a live check on 2026-11-01, the page was also not read in the run (10 requests; no recorded error).
    - V3 keeps the rule "never call an unread page a careers page", so this is a recall loss, not a precision error.

**Weakness behind the one error.** `CAREER_PATH` accepted any dash-prefixed path segment ending in a generic job word
(`(?:[\w-]*-)?jobb`), so "penger-og-jobb" ("money and work") matched.

**Change.**
- Generic job words (`jobb`, `jobbe`, `jobs`, `stilling(er)`, `rekruttering`, `vacancy`) count only at the **start** of
  a segment.
- Unambiguous careers phrases may close a longer segment: `ledige-stillinger`, `utlyste-stillinger`, `ledige-jobber`,
  `ledig-stilling`, `karriere`, `career(s)`, `vacancies`, `open-positions`, `join-us`, `work-with-us`.

**Effect, replayed on all four sets:**
- fresh60b: Barneombudet's page is no longer published.
- smoke100, midsize40, fresh60: no change.
  - `utlyste-stillinger` was briefly lost on fresh60 (dev) until the phrase list included it.

**Independence caveat.** This change was motivated by analysing a held-out error, so fresh60b careers figures after it
(9 / 9 decided at the current code) are **not** independent evidence. The independent careers figure is the new
evaluation sample (R3/R7).

**Tests:** `test_v3_jobs.py::CareersPathSegments` (topic pages rejected; real careers paths kept).

## R6 — 911771098 "Du store verden" and the reader-addressing rule

**Exact effect of the blanket rule.** "Any second-person word in a title" was added in `6efd3cd`. Recounted on titles
only (the earlier count matched against the whole unit value, including the URL), across all labelled news units, it
removed:

| Label | Count |
|---|---|
| incorrect | 10 (dev 1, fresh60 7, fresh60b 2) |
| correct | 3 (Bjelland "Få med deg …", Barneombudet "Her finner du …", Grenland Brann "Hva gjør du hvis … Øvelse NØP …") |
| unsure | 1 |

It also removed "Du store verden" (911771098), which is not in a labelled set.

**Context-aware rule** (`attribution/news.READER_ADDRESS`). A second-person word marks marketing or advice only in
these constructions:
- **possessive:** `din`, `ditt`, `dine`, `your`;
- **offer to the reader:** `for`, `til`, `gir`, `gi`, `tilbyr`, `hjelper`, `lar` + `deg`/`dere`/`you`;
- **modal:** `du kan`, `kan du`, `dere må`, `you can`, and similar;
- **`slik … du/dere`.**

A bare pronoun, an idiom or an interjection is not enough. `deres` is excluded, because it also means "their".

**Result:**
- All 10 labelled errors stay excluded; this is tested title by title.
- Replayed on the four sets, the change **adds** only Bjelland "Få med deg flere nyhetssaker på Facebook" (correct,
  midsize40) and Grenland Brann's exercise notice (correct, fresh60b), and **removes nothing**.
- 911771098 publishes all 20 posts again, as at `ff3b515`.

**Independence caveat.** The ten errors include the two from fresh60b, because the owner asked that the new rule not
re-admit them. fresh60b news is therefore not independent for this rule; see the new evaluation sample.

**Tests:**
- `test_v3_news.py::ReaderAddressing` — the ten stay out; bare pronouns and interjections stay in;
- `test_v3_regressions.py::NewsClassification::test_911771098_blog_control` — now 20, including "Du store verden".

## R3 — news: held-out analysis, diagnostic set, independent evaluation

### 1. The consumed held-out set (fresh60b): individual false positives, analysed and not tuned on

At the freeze it was scored on (`6efd3cd`), V3 published 78 news units on fresh60b: 51 correct, 9 incorrect and 18
unsure, so precision was 51 / 60 = 85.0%.

| Errors | Weakness | Status |
|---|---|---|
| 7 | Beatus Cras "Prosjekt: …" project descriptions published as posts | Fixed earlier by the project-title rule (`b5199fe`, after that evaluation); not independent |
| 2 | Grafton: WordPress theme demo posts, all created in the same second | Fixed earlier by the same-second rule (`b5199fe`); not independent |

The 18 unsure units point to two open weaknesses:
- **group news on a shared group site** — GMC companies sharing `gmc.no`; Green Mountain's UK and global units;
- **public-body advice, campaigns and features** — the fire service's safety advice, product features.

No rule was fitted to fresh60b in this pass. The only remediation changes that touch fresh60b units are R4
(Barneombudet) and R6 (the two reader-addressing titles), and both are flagged as not independent.

### 2. Diagnostic set (diag80) and the frozen rules

**Sample.** 80 companies were drawn at random (seed 20261111) from the public company universe: a registered website,
not bankrupt or being wound up, and never used in any earlier set or fixture. They were captured live through
`ff3b515` on 2026-11-01. `measurements/v3-remediation-2026-11-01/inputs/` holds the inputs and their SHA-256 sums.

**Labelling.** Blind census of both arms, labelled `assistant_blind`.

**Errors V3 still made before the fixes** (13 news, 1 social):

| Errors | Weakness | Fix |
|---|---|---|
| 10 | The site's RSS feed carries every page type, not only its news section: `/kunnskap-og-forskning/`, `/de-gode-eksemplene/`, `/tips-og-rad/`, `/min-historie/`, and regional event-offer pages. | `feed_item_outside_news_section`: when the site has a news section (two or more items under `/nyheter/`, `/aktuelt/`, `/blogg/` …), a feed item two or more levels deep in another section is not news. Root-level posts and dated addresses are not affected. |
| 1 | The Danish/Swedish default post "Hej verden!". | Added to the default-post list. |
| 1 (social) | `linkedin.com/company/board-assure-a-s` was taken for BOARD COMPANY NORGE AS. A slugified "A/S" (`a-s`) was not recognised as a legal form. | `handle_of` normalises `a-s`, `a.s` and `a_s` to `as`, so the handle names another company (`OTHER_ENTITY`). |
| 1 | Job advertisement page published as news (Sabi "Restaurantsjef"). | Not fixed: a single case. |
| 1 | Static welcome text from 2011 (Kellners). | Not fixed: a single case. |

A development-set error was fixed the same way: an advice question after a topic prefix ("Vindusvask for bedrifter:
Hvor ofte bør …"). See the `95904f0` commit.

**Effect, replayed on all sets.** On diag80 the fixes removed 12 errors (11 news, 1 social). smoke100, midsize40,
fresh60 and fresh60b are unchanged.

**Frozen at `7b8fc69`** before the evaluation sample was opened.

### 3. Independent evaluation (eval120), scored once

**Sample.** 120 more companies, drawn the same way (seed 20261112) and disjoint from diag80 and every earlier set. They
were captured with diag80, not opened until the freeze, then replayed through `ff3b515`, `dc96260` and `7b8fc69`. All
units from the three arms were pooled, labelled blind and scored once.

**Result: the 90% news target is not met.**

| Arm | News precision | 95% CI |
|---|---|---|
| `7b8fc69` (frozen remediation) | **25.6%** (10 / 39) | 14.6–41.1% |
| `dc96260` (earlier candidate) | 27.0% (10 / 37) | 15.4–43.0% |
| `ff3b515` (baseline) | 14.6% (13 / 89) | 8.7–23.4% |

V3 still removes 47 of the baseline's errors and introduces none. The precision gap is the companies whose whole blog
is marketing.

**Weaknesses the independent errors show** (29 incorrect at `7b8fc69`; analysed, not tuned on):

1. **Content-marketing blogs (20 errors, 7 sites).** On these sites every "post" is advice, a property or project
   listing, or thought leadership:

   | Site | Errors |
   |---|---|
   | huspro.no (Byggmester Frank Aasheim): property and project posts | 6 |
   | opts.no (Oslo PT Studio): training advice | 5 |
   | ns.no (Nordic Solutions): IT tips | 3 |
   | ffor.no: course, topic and welcome pages | 3 |
   | dayofweek.com: thought leadership | 2 |
   | sobbl.no: service pages | 2 |

   V3 treats a `/post/` or `/blog/` address as article evidence, and its advice detection works on titles alone.
   Without reading the article text, a company's own marketing posts cannot be told apart from news about it. **This is
   the main structural limit of the deterministic news classifier.** The independent results show that precision
   depends on the site mix: about 85–97% on the earlier sets, 25.6% here.
2. **A subsidiary whose website is its parent's (5 news and 3 social errors).** BE KRAFTSALG AS has `bodoenergi.no` as
   its verified website, and the group's sponsorship stories and profiles are published for it. Domain and name do
   not reveal the group relationship here (`BE` stands for Bodø Energi), so the operator assessment returns `self`.
3. **The context-aware reader-addressing rule (R6) re-admitted 2 advice posts** ("Bekymrer du deg mer nå enn før du
   ble gravid?", "Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker") and gained no correct unit here.
   On the development data it gained 3 correct units and "Du store verden". The independent evidence does not support
   the narrower rule. It is kept as evaluated, because reverting it now would be tuning on eval120. This is listed as a
   decision for the owner.

### 4. Measurements

Precision excludes units labelled unsure. The CI is a Wilson 95% interval. True recall cannot be measured, because no
ground truth of all profiles, articles or jobs exists, so **retention** — correct baseline units that V3 still
publishes — is reported as the recall proxy, with its own Wilson interval. All labels are `assistant_blind` (blind to
the arm), not the owner's.

**eval120 — INDEPENDENT (frozen 7b8fc69, scored once)**

| Category | Arm | Correct | Incorrect | Unsure | Precision (95% CI) | Retention = recall proxy (95% CI) | Errors removed / introduced |
|---|---|---|---|---|---|---|---|
| Social | baseline ff3b515 | 46 | 8 | 3 | 85.2% (73.4–92.3) |  |  |
| Social | V3 remediation 7b8fc69 | 40 | 3 | 2 | 93.0% (81.4–97.6) | 40/46 = 87.0% (74.3–93.9) | 5 / 0 |
| News | baseline ff3b515 | 13 | 76 | 15 | 14.6% (8.7–23.4) |  |  |
| News | V3 remediation 7b8fc69 | 10 | 29 | 15 | 25.6% (14.6–41.1) | 10/13 = 76.9% (49.7–91.8) | 47 / 0 |
| Careers page | baseline ff3b515 | 6 | 3 | 1 | 66.7% (35.4–87.9) |  |  |
| Careers page | V3 remediation 7b8fc69 | 4 | 0 | 0 | 100.0% (51.0–100.0) | 4/6 = 66.7% (30.0–90.3) | 3 / 0 |
| Job ads | baseline ff3b515 | 0 | 0 | 1 | — |  |  |
| Job ads | V3 remediation 7b8fc69 | 0 | 0 | 0 | — | — (no correct baseline unit) | 0 / 0 |

**eval120 — independent, earlier candidate dc96260**

| Category | Arm | Correct | Incorrect | Unsure | Precision (95% CI) | Retention = recall proxy (95% CI) | Errors removed / introduced |
|---|---|---|---|---|---|---|---|
| Social | baseline ff3b515 | 46 | 8 | 3 | 85.2% (73.4–92.3) |  |  |
| Social | V3 dc96260 | 40 | 3 | 2 | 93.0% (81.4–97.6) | 40/46 = 87.0% (74.3–93.9) | 5 / 0 |
| News | baseline ff3b515 | 13 | 76 | 15 | 14.6% (8.7–23.4) |  |  |
| News | V3 dc96260 | 10 | 27 | 15 | 27.0% (15.4–43.0) | 10/13 = 76.9% (49.7–91.8) | 49 / 0 |
| Careers page | baseline ff3b515 | 6 | 3 | 1 | 66.7% (35.4–87.9) |  |  |
| Careers page | V3 dc96260 | 4 | 0 | 0 | 100.0% (51.0–100.0) | 4/6 = 66.7% (30.0–90.3) | 3 / 0 |
| Job ads | baseline ff3b515 | 0 | 0 | 1 | — |  |  |
| Job ads | V3 dc96260 | 0 | 0 | 0 | — | — (no correct baseline unit) | 0 / 0 |

**diag80 — diagnostic (tuned on)**

| Category | Arm | Correct | Incorrect | Unsure | Precision (95% CI) | Retention = recall proxy (95% CI) | Errors removed / introduced |
|---|---|---|---|---|---|---|---|
| Social | baseline ff3b515 | 37 | 1 | 1 | 97.4% (86.5–99.5) |  |  |
| Social | V3 remediation 7b8fc69 | 31 | 0 | 0 | 100.0% (89.0–100.0) | 31/37 = 83.8% (68.9–92.3) | 1 / 0 |
| News | baseline ff3b515 | 71 | 18 | 7 | 79.8% (70.3–86.8) |  |  |
| News | V3 remediation 7b8fc69 | 66 | 2 | 6 | 97.1% (89.9–99.2) | 66/71 = 93.0% (84.6–97.0) | 16 / 0 |
| Careers page | baseline ff3b515 | 4 | 1 | 0 | 80.0% (37.5–96.4) |  |  |
| Careers page | V3 remediation 7b8fc69 | 4 | 0 | 0 | 100.0% (51.0–100.0) | 4/4 = 100.0% (51.0–100.0) | 1 / 0 |
| Job ads | baseline ff3b515 | 0 | 2 | 0 | 0.0% (0.0–65.8) |  |  |
| Job ads | V3 remediation 7b8fc69 | 0 | 0 | 0 | — | — (no correct baseline unit) | 2 / 0 |

**smoke100+midsize40+fresh60 — development (tuned on)**

| Category | Arm | Correct | Incorrect | Unsure | Precision (95% CI) | Retention = recall proxy (95% CI) | Errors removed / introduced |
|---|---|---|---|---|---|---|---|
| Social | baseline ff3b515 | 84 | 13 | 3 | 86.6% (78.4–92.0) |  |  |
| Social | V3 remediation 7b8fc69 | 83 | 0 | 0 | 100.0% (95.6–100.0) | 80/84 = 95.2% (88.4–98.1) | 13 / 0 |
| News | baseline ff3b515 | 77 | 144 | 20 | 34.8% (28.9–41.3) |  |  |
| News | V3 remediation 7b8fc69 | 86 | 6 | 19 | 93.5% (86.5–97.0) | 76/77 = 98.7% (93.0–99.8) | 138 / 0 |
| Careers page | baseline ff3b515 | 14 | 11 | 4 | 56.0% (37.1–73.3) |  |  |
| Careers page | V3 remediation 7b8fc69 | 14 | 0 | 1 | 100.0% (78.5–100.0) | 14/14 = 100.0% (78.5–100.0) | 11 / 0 |
| Job ads | baseline ff3b515 | 0 | 0 | 1 | — |  |  |
| Job ads | V3 remediation 7b8fc69 | 0 | 0 | 0 | — | — (no correct baseline unit) | 0 / 0 |

**fresh60b — consumed held-out (non-independent for the remediation changes)**

| Category | Arm | Correct | Incorrect | Unsure | Precision (95% CI) | Retention = recall proxy (95% CI) | Errors removed / introduced |
|---|---|---|---|---|---|---|---|
| Social | baseline ff3b515 | 57 | 11 | 1 | 83.8% (73.3–90.7) |  |  |
| Social | V3 remediation 7b8fc69 | 55 | 0 | 0 | 100.0% (93.5–100.0) | 55/57 = 96.5% (88.1–99.0) | 11 / 0 |
| News | baseline ff3b515 | 52 | 19 | 20 | 73.2% (62.0–82.2) |  |  |
| News | V3 remediation 7b8fc69 | 52 | 0 | 18 | 100.0% (93.1–100.0) | 52/52 = 100.0% (93.1–100.0) | 19 / 0 |
| Careers page | baseline ff3b515 | 10 | 5 | 4 | 66.7% (41.7–84.8) |  |  |
| Careers page | V3 remediation 7b8fc69 | 9 | 0 | 3 | 100.0% (70.1–100.0) | 9/10 = 90.0% (59.6–98.2) | 5 / 0 |
| Job ads | baseline ff3b515 | 0 | 1 | 0 | 0.0% (0.0–79.3) |  |  |
| Job ads | V3 remediation 7b8fc69 | 0 | 0 | 0 | — | — (no correct baseline unit) | 1 / 0 |

## R7 — validation of the remediation code (`7b8fc69`)

| Check | Result |
|---|---|
| Full suite, working tree | 487 passed, 172 subtests, 0 failed, 0 skipped. At `v3-candidate-1` it was 474. The new tests cover R1, R2, R4, R5, R6 and R3. |
| Clean room (fresh clone, empty uv cache, `uv sync --locked`) | Sync OK; 3 of 3 suite runs with 487 passed and 172 subtests; documented command exit 0 (`measurements/v3-remediation-2026-11-01/release/` and below) |
| Dependencies | `git diff ff3b515 7b8fc69 -- pyproject.toml uv.lock` is empty. No paid API; LLM not loaded; third-party cost $0 in every run. |
| Live 100 companies (fixed smoke input, SHA-256 `80eb79e6…`) | 100/100 `completed` in input order; validation passed; 0 contract findings with 3,994 snapshot hashes re-verified; 0 unsupported summary statements; 196 hosts, none a social or other restricted platform; 142.0 s, 762 requests, $0 |
| Refresh through the run history | 100/100 compared against `published_envelope`. **No removals, additions or retractions.** 2 `unavailable` events: Kongsvinger IL Ishockey's robots.txt was unreachable during the refresh, so its website, description and news were kept as "last value kept". This is the live outage path working. |
| Reproductions, live | 911771098: LinkedIn not published, **20** news items. Tyin Alpint: 0 profiles; site run by another company. Bergknapp: its own 3 profiles. Bartec: group site, 0 profiles. BK Bygg: 0 news, its own 2 profiles. |
| Positive controls (fixtures) | All kept: Kilis 10, Birralee 20, Grønsand 15 plus 2 profiles, Beredt ≥ 6 news, Bergknapp 3, BioMar `biomarnorge`, Birralee and Bjelland careers pages, ASAK MILJØSTEIN's own profiles, 911771098 20 posts. One control changed with evidence: Beredt's `@beredtinkludering`, see R1/R2. |

## Remaining known errors and open decisions

**Known errors (V3 candidate 2):**
1. **News on content-marketing blogs** (independent, 20 of 29 news errors). Advice, property or project listings and
   thought-leadership posts under `/post/` or `/blog/` are published as news. This needs article-text classification,
   which the deterministic rules do not do.
2. **A subsidiary whose website is its parent's** (BE KRAFTSALG AS on `bodoenergi.no`): 5 news and 3 social errors in
   the independent sample. The group relationship is visible only in the registry (parent organisation), which V3 does
   not use for operator assessment.
3. **The reader-addressing rule (R6)** re-admitted 2 advice posts on the independent sample and gained no correct unit
   there.
4. **Single cases:**
   - a job-advertisement page published as news (Sabi);
   - a 2011 welcome text (Kellners);
   - an accountant's regulation posts (Solregn);
   - Stalheim's tour package;
   - Hamatec's 2015 price notice dated 2016;
   - Realbygg's project name on its press listing.
5. **Earlier known errors:** Green Mountain UK and global group news on the Norwegian AS's site, and GMC group news
   shared by sister companies. Both were labelled unsure.
6. **Careers recall.** A careers page is published only if it was read in the run (GMV `/karriere` and Webstep
   `/bli-en-av-oss` were not), so independent retention is 4/6.
7. **Job advertisements:** too rare to measure; no decidable published ad in any remediation sample.

**Decisions for the owner:**
- Whether to submit with news precision this far below target on independent data, or restrict news publication, for
  example to `/nyheter/`, `/aktuelt/` and press sections, or to items whose text names the company. Either option
  needs its own new held-out evaluation.
- Whether to keep R6. It helps on development data and hurts on independent data; the counts are small either way.
- Whether to re-label (`scripts/audit_kit.py`, `--labeller-kind owner`). All labels are the assistant's (blind).
