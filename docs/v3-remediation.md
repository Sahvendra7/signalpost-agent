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
