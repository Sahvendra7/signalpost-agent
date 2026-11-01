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

## Phase 1 — entity resolution and social attribution

New package `src/norway_company_agent/attribution/`:
- `names.py` — handle relations;
- `operator.py` — who runs the site;
- `social.py` — profile decisions.

**Site operator** (design §B5), decided from pages already captured, with no new request:
- **`other_entity`:** another valid org number is stated in an imprint, and the company's own number appears nowhere.
  Effect: the website claim stays, as the registry lists it, and gains `site_role: operated_by_other_company` and
  `operated_by`. Profiles, the careers page and vacancies are held; `job_posting` becomes `not_applicable`, with the
  reason.
  - Fixes: TYIN ALPINT AS (983181732) received Tyin Filefjell AS's LinkedIn, Facebook and Instagram.
- **`group_or_brand`:** any of the following.
  - The registry website redirects to another domain (BARTEC AS: bartec-technor.no → bartec.com).
  - The domain shares no distinctive token with the legal name, and the name is absent from the site.
  - A "BRAND + own town" legal name in a corporate group (`erIKonsern`), with the full name absent from the homepage.
  - The site's taxonomy names two or more sibling units ("Betonmast Trøndelag", … for BETONMAST OSLO AS).

  Effect: `site_role: group_or_brand_site`; only exact legal-name handles are attributed; the careers page and
  vacancies are held.
- **Own org number stated anywhere on the site → `self`.** This guards against a holding company named in the footer.
- The **business-manager** (Revision 1) and **hosting-platform / section** (C300) rules are unchanged; they are now
  reported as operator kinds.

**Social decisions** (design §B4):
- A profile is accepted when its handle **is the legal name** (EXACT), optionally with neutral additions such as a
  legal form, "norge", the company's own town or a short number (EXACT_NEUTRAL).
- A **brand** (leading name tokens) or an **extended** handle is accepted only on a self-run site whose own domain is
  named after the company. An extended handle is also accepted when the company's own structured data names the
  company and lists the profile.
- Handles naming **another entity** are held: "group", "holding", "global" and similar words, or a different name
  ending in a legal form (`tyin-filefjell-as`, `bdt-viken-revisjon-as`). So are unrelated handles.
- **The domain-name rule and JSON-LD `sameAs` no longer accept a profile on their own.**
- Held profiles keep their reason in `ambiguous_profiles` and in the rejection counts, e.g. `social:handle_names_other_entity`.
- Published profiles carry `attribution: {code, basis}`.

**Tests replaced:**
- `test_revision1.py::AuditRegressions::test_domain_name_must_begin_or_end_the_handle`: `handballnorge` for
  BALLSPORT DRIFT AS is now held. A site named after the company still corroborates its own extended handles.
- `test_revision1.py::SocialRules::test_jsonld_sameas_of_own_organization_is_accepted`: `fd-group` listed in
  `sameAs` for Fjell Data AS is now held. A `sameAs` handle that carries the name is still accepted.

**Fixtures now passing:**
- Tyin: 3 → 0 profiles.
- Bergknapp: Grasrota 3 → 0; its own 3 kept.
- Bartec: 4 → 0.
- BioMar: `@BioMarGroup` held; Norway profiles kept.
- BDT Viken: `bdt-viken-revisjon-as` held.
- Controls unchanged: Grønsand, Birralee, Beredt, Crux, Bjelland, Bergen Rørteknikk, BK Bygg, Bemex.

## Phase 2 — news classification, publication dates, subject

New module `attribution/news.py`. Every dated candidate is classified on its own. A feed, a news listing or an
`<article>` wrapper no longer proves that an item is news.

**Rejections, in order:**

| Code | Rejects |
|---|---|
| `media_file` | images and documents |
| `non_article_path` | product, service, project, portfolio, cabin, booking, contact, about, privacy, archive and author pages (e.g. `/prosjekter/`, `/portfolio-item/`, `/category/`) |
| `listing_not_item` | the homepage, or a listing page's own page-level date (e.g. "Siste nytt · Beredt AS") |
| `default_cms_post` | "Hello world!" and similar default posts |
| `project_category` | feed items filed only under project or building-type categories |
| `outside_news_section` | a news listing's card linking to an evergreen page outside the section, when most of its cards stay inside it |
| `bulk_entry_burst` | four or more posts from one source within 15 minutes, or five on one day when only dates are known. BK Bygg posted 10 reference projects in 3 minutes |

**Positive article evidence is now required.** An item needs at least one of:
- a news or dated URL;
- a post in the site's own main feed (plain WordPress slugs stay valid);
- a dated card on the site's news page;
- JSON-LD article markup on its own page. `og:type` does not count: Stiftelsen Crux marks every page, contact pages
  included, as an article.

**Publication time.** In an `<article>`, a `<time>` marked published wins; otherwise the first time not marked
updated or modified is used. A lone hAtom `class="updated"` time with one date is kept only as `date_kind:
stated_on_page`, never as a publication date. Conflicting updated-only times give no date. Feed `<updated>` stays
rejected (unchanged).

**Item URL.** An `<article>` card's URL is its heading link or its first internal link that is not an archive, author,
media or share link. Bjelland's cards previously all pointed at `/category/aktuelt/` and were de-duplicated into one.
Now its real articles are kept separately, and its portfolio items are rejected.

**Subject:**
- `sibling_entity_item` — never published. The site's own categories tag another unit of the group (Betonmast's feed
  tags each post with the regional company it concerns).
- Sites run by another company or by a group/brand publish only items that name this company: its organisation
  number, its full legal name, or a category equal to its name. The code is `item_not_about_entity_on_<kind>_site`.
- Business-manager sites keep the Revision 1 rule.

**Tests:**
- `test_revision1.py::NewsRules::test_homepage_page_level_dates_dropped_but_homepage_article_cards_kept` still passes
  unchanged. A dated `<article>` card on the homepage without its own link stays a news item (`homepage_article_card`).
- Fixtures now passing:
  - BK Bygg 10 → 0; Bergen Rørteknikk 10 → 0;
  - "Hello world!" on BDT Viken and Best Work → 0;
  - Crux contact page and `.jpg` → 0, its real article kept;
  - Bjelland 3 portfolio items rejected, real articles 6 → 11;
  - Bergknapp `/prosjekter/` → 0; Bartec group magazine 17 → 0;
  - Betonmast Oslo 10 → 1 (its own tagged item); Beredt listing page removed, 7 articles kept.
- Controls unchanged: 911771098 (20), Kilis Hockey (10), Birralee (20), Grønsand (15).
  - **Correction (found in Phase 8):** after `6efd3cd` (the second-person title rule, Phase 4), 911771098 has 19,
    not 20. See "Phase 8".

## Phase 3 — job advertisements and careers pages

New module `attribution/jobs.py`.

**Dates.**
- `parse_deadline` keeps future closing dates (up to 18 months ahead). `validThrough` previously went through
  `parse_date`, which rejects future dates. That dropped the validThrough of every current advertisement and kept the
  expired ones, which were then published.
- `parse_date` itself is unchanged.

**Currency** — only `open` and `recently_posted` are published:

| State | Meaning |
|---|---|
| `open` | a stated deadline or `validThrough` on or after the run date (Europe/Oslo) |
| `recently_posted` | no closing date stated, posted at most 45 days before the run. The basis says exactly that; the advertisement is never called "current" |
| `expired` | deadline passed, or posted more than 45 days ago with no closing date |
| `currency_unknown` | no date at all; unknown stays unknown |

**Employer.** The employer named in the advertisement (`hiringOrganization`, or an "Arbeidsgiver:"/"Employer:" label)
must be the company; another name gives `other_employer`. With no employer named:
- a self-run site, not a recruiter → the company is presumed, with that basis stated;
- a recruiter or staffing company (NACE 78.1–78.3) → `employer_unstated_on_job_board`;
- a shared or group site → held.

A recruiter's own vacancies that name it as employer are still published.

**Single advertisement.**
- A JSON-LD JobPosting in a news or archive page → `job_on_news_page`.
- Open applications, talent banks, "Registrer CV" and bare "Sommerjobb"/"Lærling" titles → `generic_recruitment`.

**Careers page.**
- The link must be a careers path segment or a careers label ("Ledige stillinger", "Jobb hos oss"). The bare substring
  `jobb` no longer qualifies.
- The fetched page must itself pass `is_careers_page`.
- Service pages for employers or customers (`/for-bedrifter/`, `/arbeidsgivere/`, `/tjenester/`) are never careers
  pages.
- The summary now says "Careers page (a recruitment page, not a job advertisement)".

**Claims.** Job claims carry `currency: {state, basis}`, `attribution`, and `hiring_organization` when it is stated.

**Tests updated** (dates made relative to the run day, so they cannot expire):
- `test_site_research.py` `CAREERS`: the fixture deadline 2026-10-31 had passed.
- `test_revision1.py::JobRules::test_one_job_page_is_one_posting`: posted 2026-09-20, which crosses the 45-day
  window on 2026-11-05.

**Fixtures.** Best Work `/for-bedrifter/` and Beredt `/arbeidsgivere/unge-i-praksis/` no longer give careers pages.
The Birralee, Bjelland and Bemex careers pages are kept.

## Phase 4 — fixes from the development-set audit (rules frozen after this entry)

The blind dev audit (midsize40 + smoke100, `docs/v3-accuracy.md`) found three correct news items V3 had lost. It also
found two errors that neither version caught.

- **"Uncategorized"** and other CMS default categories are no category. They no longer count as project taxonomy,
  which had wrongly rejected two posts each from JEDM and Bli Optimal.
- **`date_contradicts_title`.** A post whose title names a year more than one year after its stated date was reused,
  so the stated date is not its publication date. Example: "Utlysing 2026" dated 2018.
- **`careers:recruiter_job_board`.** A recruiter's (NACE 78) vacancies page lists its clients' jobs. It is a careers
  page only when it is explicitly about working at the recruiter (`jobb-hos-…`, `karriere`, `join-us`). The Bemex
  control expectation in `test_v3_regressions.py` was corrected from "kept" to "held".

## Phase 4 — fixes from the first held-out evaluation

The first held-out evaluation (fresh60, run once with the rules frozen at `ca34ef5`) failed the gates. Social retention
was 62%, and news precision was 20% in **both** arms; the results are in `docs/v3-accuracy.md`. Investigating it
turned fresh60 into a development set, so the rules below were validated on a **new** held-out set (fresh60b).

**Social and operator rules:**
- Legal names that start with a legal form ("AS JACO", "AS SOLREGN") match handles that keep it (`asjaco`,
  `as-solregn`).
- An acronym of the name is a neutral suffix (`…-IPR`).
- A handle that **is the name of the company's own website** (`ringblad` on ringblad.no) is accepted on a self-run
  site that no other company runs (`handle_is_own_domain_name`). The domain still never attributes a profile on a site
  run by another company or by a group or brand. TYIN ALPINT stays fixed: its site states another company's number.
- The cross-link rule counts exact handles with a neutral suffix as exact.
- `NO` is read as an organisation number only in the VAT form (`NO 123 456 789 MVA`). A page listing three or more
  companies, or a dealers, partners or members page, is a directory, not an imprint. AS FINANCIERING's dealer list had
  made it `other_entity`.
- A redirect makes a site a group site only when a `.no` domain redirects to an international domain
  (bartec-technor.no → bartec.com). A rename to another Norwegian domain does not (stalheim.com → stalheimhotel.no,
  hadeland.net → hadeland.no).

**News rules:**
- **Publishers** — newspapers, magazines and other publishers, broadcasters and news agencies (NACE 58.1, 60, 63.91,
  63.12). Their journalism is their product, not news about the company. Only items naming the company are published
  (`publisher_content_not_about_company`). Their job classifieds are not careers pages.
- **Evergreen advice and marketing** — titles such as "Slik …", "Hvordan …", "Hvor ofte …", "… sjekkliste", "How to
  …" or second-person "du/dere/you" are not news unless they name the company (`evergreen_advice_not_news`).
- **Press releases** — "Pressemelding: …" titles and `pressemelding-…` slugs count as article evidence.

## Phase 4 — fixes after the second held-out evaluation (validated on development sets only)

The second held-out evaluation (fresh60b, run once with the rules frozen at `6efd3cd`) passed the social gate. It failed
the news precision gate at 85% and the careers gates; see `docs/v3-accuracy.md`. The causes were three bugs and two
missing rules. These changes come after that evaluation, so they are checked only on the four development sets and the
fixtures; no third held-out set was run.

**Bugs fixed:**
- `fold()` transliterated ø/å/æ before URL-decoding. Percent-encoded handles lost the letter:
  `@GlommenMj%C3%B8senSkog`, `gr%C3%B8nn-jobb-as`.
- Single-letter parts of a legal name are kept as an alternative form: "Alf I. Larsen A/S" ↔ `alf.i.larsen.as`.
- A careers path under `/tjenester/` (a municipality's site map) is not a service page when its own last segment is a
  careers segment.

**Rules added:**
- `project_title` — titles starting "Prosjekt:", "Referanse:", "Project:", "Case:".
- Two or more different posts created in the same second (a theme's demo content) are a bulk entry. Midnight
  timestamps count as dates, not times.

## Phase 5 — evidence history, published-envelope changes, retractions, first-seen

**Run history** (`history.py`).
- The documented command keeps every run in `<output dir>/signalpost-history/<run_id>/`: envelopes, profiles, report
  and manifest.
  - Each run is written to a temporary directory, with the manifest last, then renamed into place.
  - A run that stopped early (deadline or interrupt) is kept but marked `complete: false`, and is never used as a
    baseline.
  - Pruning keeps the newest 10 runs (`--history-keep`) and always the newest two complete runs. It only deletes
    directories carrying the history marker.
- `--no-history` disables it. The history is written after the envelopes, profiles and report are durable, and never
  fails a run.

**Baseline** — what the changes are compared with:
1. `--previous-envelopes` (what was published);
2. otherwise, when no `--previous-profiles` is given, the newest complete history run in which that company's research
   completed;
3. otherwise `--previous-profiles`, with its existing behaviour. Its facts are re-derived with the current rules; that
   is stated in `refresh.baseline.note`.

Outage carry-forward still comes from the previous profiles (the refresh fix is unchanged).

**Change types** (additive; the contract validates the allowed set):
- `retracted` — the previous run published the fact, this run still found it, and a rule now withholds it. The event
  carries the rule code, a plain basis and both code versions. It is never described as "previously verified".
- `not_rechecked` — the page the fact came from was not read in this run (informational).
- `removed` — now strictly "the page was read again and the item is gone".
- `added`, `changed`, `unverified` and `unavailable` are unchanged.

**First seen.** Social profiles, news items and job postings carry `first_seen_at` / `first_seen_run_id`, carried over
from the baseline. `is_new: true` appears only when a baseline existed and the fact was not in it; with no baseline,
nothing is called new.

**Report.** New blocks:
- `baseline` — its source, and how many companies had one;
- `new_items` — per family, plus retractions;
- `checks` — candidates withheld by rule, by reason; labelled as automatic checks, not accuracy;
- `manual_audit` — from `--audit-results`, otherwise `not_audited`;
- `history`.

## Phase 6 — viewer v2 (design §B10)

The viewer stays one self-contained HTML file: no network, CSP `default-src 'none'`, text inserted with
`textContent` only.

- **Evidence inspector.** Every fact has an *Inspect* button. It opens a dialog showing:
  - the value and state;
  - how the fact relates to the company (attribution basis) and why it is current (job deadline basis);
  - the website's role (for example "operated by other company", with that company's organisation number);
  - first seen, and whether it is new;
  - for each source: address, source type, retrieval time, content hash and quoted span.

  In app mode (Phase 7) it also links the captured bytes.
- **What's new.** The `#new` view lists, per company, the facts new since the baseline and the facts our checks
  withdrew, removed or changed, with the rule's basis. Without a baseline it says so and calls nothing new. A new filter,
  "With new items", is added to the company list.
- **How reliable is this?** The `#trust` view explains how each category is checked. It shows the manual-audit
  precision only when `--audit-results` was supplied, labelled as a local measurement. Otherwise it says
  "Not audited". It also lists items held back by automatic checks, labelled as checks, not accuracy.
- **Held-back items** have their own section, "Seen but not attributed to this company", separate from "Not known".
  Neither counts as a fact.
- **News** shows the newest 10 per company, with "Show all".
- **Plain labels.** States, changes and categories have plain-language labels; for example `retracted` shows as
  "Withdrawn by our checks".
- **Phone comparison.** Below 760 px the comparison is one card per field, with a numbered chip per company, instead of
  a sideways-scrolling table. The existing headless test was updated to read the cards on mobile. The desktop table is
  unchanged.
- **Header** says how many companies were compared with their previous run.
- **Fix.** `_claim_notes` reads `currency`, `attribution` and `operated_by` only when they are objects. Financial claims
  carry `currency: "NOK"`.

Tests (`tests/test_v3_viewer.py`), headless Chromium at 1366×820 and 390×844:
- inspector content and closing;
- What's New rows (new and withdrawn);
- trust panel ("Not audited");
- comparison of 2 and 4 companies;
- no horizontal page scroll, no page errors, no request leaving the page;
- no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval` or `new Function` in the page;
- size budget: the template is under 80 KB and the average is under 60 KB per company. The 16 fixture companies measure
  about 20 KB each.

Screenshots: `docs/screenshots/v3-viewer-*.png`.

## Phase 7 — local search application (design §B11–§B12)

New package `src/norway_company_agent/app/` and the command `scripts/serve.py`. It uses only the standard library and
adds no dependency. Usage is in `docs/search-app.md`.

- **Search.** Searches the dataset (imported envelope files plus companies researched in the app) and the registry,
  using either the fixed Brreg search endpoint or `--bulk`. Name or organisation number only. URL-like input is
  refused before anything is fetched.
- **On-demand research** runs the batch pipeline for one row with a 120 s deadline. Limits: 2 live threads (orphans
  counted), a queue of 20, de-duplication and cancel. The previous stored run is the baseline, so a re-check reports
  new and withdrawn items. Outcomes:
  - completed or partial (failed sources named) is stored;
  - failed (not in registry / registry unreachable) or cancelled is not stored.
- **Pages.** Profiles, comparison and What's New are the Phase 6 viewer, served with `app` links: back to search, and
  captured bytes in the inspector. The viewer gains an `app.open` hook so an app document opens on its view.
- **Security** (§B12): loopback bind; Host check (421); token, Origin, Sec-Fetch-Site and JSON for POST; 4 KB bodies;
  rate limits; 10 s socket timeout; 32 concurrent requests; snapshots only for indexed hashes, as a sandboxed text
  attachment; no tracebacks; no subprocess. Data directories are 0700 and files 0600.
- **Bug found while testing.** With a 120 s deadline, the batch default `grace_seconds=60` makes the "will it fit"
  rule degrade every single-company research to official-only. The app passes `grace_seconds=min(15, deadline/4)`.
  Batch defaults are unchanged.

Tests:
- `tests/test_v3_app.py`: offline, end to end — search, research completed/partial/failed/cancelled, persistence,
  read-only imports, snapshots, and a headless flow at 1366×820 and 390×844.
- `tests/test_v3_app_security.py`: every control in §B12.

Screenshots: `docs/screenshots/app-*.png`.
