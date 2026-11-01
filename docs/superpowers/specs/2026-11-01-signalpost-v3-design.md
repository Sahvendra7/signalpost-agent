# Signalpost V3 — reviewed design specification

| | |
|---|---|
| Status | Approved for implementation by the owner (2026-11-01), after the independent review in Part A |
| Baseline | `ff3b5152221be3e39c6f6532f47ebf6f61442336` (code `71fa494`), the last submitted candidate. Tests at baseline: 361 passed, 91 subtests passed |
| Branch | `claude/awesome-sagan-m2lppu`, fast-forwarded to the baseline (no history rewritten). `claude/c300-refresh-fix` still points at the baseline, so the previous candidate stays reproducible |
| Plan | `docs/superpowers/plans/2026-11-01-signalpost-v3-implementation.md` |
| Inputs to this design | Builderr feedback (social attribution, jobs, news, UX, trust); the 2026-11-01 diagnostic report and its live reproductions; the first-draft spec (kept unchanged in the session scratchpad for comparison) |

Scope: all nine owner-requested improvements.

1. Shared entity resolution and accurate social attribution.
2. Strict news classification and company relevance.
3. Accurate current job advertisements.
4. Evidence history, first-seen dates, retractions and code-version stamping.
5. Manual audit kit and per-category accuracy reporting.
6. Viewer with trust indicators, evidence inspection and What's New.
7. Responsive local company search application.
8. On-demand research for companies not yet in the dataset.
9. Integration of search with profiles, comparison and evidence inspection.

---

## Part A — Independent design review of the first draft

Each finding states the problem, its impact and the correction adopted in Part B.

### A1. Architecture and coupling

**DR-1 — `entity.py` was a catch-all.**
- Problem: the draft put name matching, org-number extraction, site-operator assessment and policy into one module. That
  merges five separate decisions: target identity, site operation, profile identity, item subject and job employer.
- Impact: every future rule change touches one large module, and the decisions cannot be tested or reported
  separately.
- Correction: a small `attribution/` package of pure functions, one module per decision, sharing one `Decision` value
  type (§B2). `site_facts.py` keeps *extraction*; `attribution/` makes *decisions*.

**DR-2 — The viewer asset split plus an API-driven client was a large, risky rewrite.**
- Problem: splitting the 300-line inline viewer into files and re-plumbing it onto a fetch-based `DataSource` would
  have duplicated the UI paths: static versus app.
- Impact: there would be two code paths to keep correct, and a high risk of regressing the viewer that C300 validated.
- Correction: the app serves **server-rendered viewer documents**. `render_viewer()` is called on the selected
  companies, and the result is the same self-contained page. A small search page handles search and research jobs. The
  viewer remains the single UI for profiles, comparison and evidence (§B10).

**DR-3 — Incorrect assumption: a new pipeline stage hook was needed.**
- Problem: `run_batch` already keeps a per-company `progress` dict (salvage on deadline), filled as modules complete.
- Correction: expose it through an optional `progress` argument. That is additive, and it leaves envelopes unchanged.
  No new hook is added inside `research_company`.

**DR-4 — Incorrect assumption: the deadline stops work.**
- Problem: at the deadline `run_batch` calls `pool.shutdown(wait=False, cancel_futures=True)`. Running worker threads
  are not killed. They finish within their own fetch timeouts and site budget.
- Impact: in a long-running app, on-demand jobs that time out could pile up as orphan threads.
- Correction: the app counts a job's slot as busy until its worker thread actually ends (the thread is joined in the
  background), not merely until the envelope is emitted. A global cap holds on live research threads (§B12).

### A2. Attribution rules

**DR-5 — Brand handles were missing from the relation model.**
- Problem: the draft's `EXACT/EXTENDS/OTHER/UNRELATED` model would reject correct short-name handles: `birralee` for
  BIRRALEE INTERNATIONAL SCHOOL TRONDHEIM AS, `gronsand` for GRØNSAND GJESTEGÅRD AS.
- Correction: add a `BRAND` relation, meaning a handle made of the leading distinctive legal-name tokens. It is
  accepted only on a self-operated site whose domain label is that same brand (§B4).

**DR-6 — Facebook page ids.**
- Problem: `facebook.com/Bjelland-As-359873177420058` carries a numeric page id that broke the "1–4 digits" neutral
  affix.
- Correction: strip a trailing `-<digits ≥ 8>` page id on Facebook before classification.

**DR-7 — Operator signal (c) needed a 356-municipality data file.**
- Correction: use the target's **own** registered municipality and post town (already in the profile), plus the 15
  county names and four compass regions. The strongest group-site signal is "BRAND + the company's own town" (BETONMAST
  OSLO AS in Oslo; BERTEL O. STEEN LØRENSKOG AS in Lørenskog). No data file is added.

**DR-8 — Operator false positives.**
- Problem: a holding company's org number in the footer of the operating company's own site would trigger
  `other_entity`.
- Correction:
  - the own org number appearing anywhere on the captured pages forces `self`, unless the site is a business manager's
    or a hosting platform's;
  - `other_entity` requires imprint context, at least one other valid number, and the own number absent.
  - The registry-linked website claim is never removed by the operator check.

### A3. Jobs

**DR-9 — The 60-day rule invented currency.**
- Problem: "no deadline → current if posted within 60 days; no date → not published" mixed currency evidence with
  guesses, and treated a careers page listing as if it had no evidence at all.
- Correction: an explicit currency state machine (§B7):
  - `open` — a deadline or `validThrough` on or after the run date;
  - `recently_posted` — `datePosted` within 45 days, no expiry stated, published with that basis stated, never called
    "current";
  - `expired`;
  - `undated`.
  Only `open` and `recently_posted` are published. Future deadlines parse correctly through `parse_deadline`.

**DR-10 — NACE 78 blanket exclusion was wrong.**
- Problem: it would have removed a recruitment company's own genuine vacancies.
- Correction: resolve the employer per posting (§B7):
  - a named employer equal to the target → publish;
  - a named other employer → `other_employer`;
  - no employer named → the target only on a self-operated, non-recruiter site.
  - A recruiter or staffing site (NACE 78.1–78.3) with no employer named → held as `employer_unstated_on_job_board`.

### A4. News

**DR-11 — The 20-item news cap was an extraction cap.**
- Problem: it would silently drop valid items.
- Correction: no publication cap is added. The existing operational caps stay as they are (30 items per page, 50
  per feed, 3 article fetches). The viewer shows the 10 newest per company, with "show all". The summary already
  cites the newest item. Storage is complete.

**DR-12 — The evergreen "how-to" tag added complexity without evaluator backing.**
- Correction: removed from scope.

### A5. Measurement

**DR-13 — Live same-day re-runs drift.**
- Problem: drift happens (Sjøløftet's robots.txt outage in C300).
- Correction: **replay measurement**. The baseline is captured live with `--snapshot-dir`; the V3 code then re-reads
  *the same captured bytes* through the real pipeline. Any difference is then attributable to code. A live V3 run is
  kept only as a smoke check (§B13).

**DR-14 — "Recall loss" was undefined; the true recall denominator is unknowable without ground truth.**
- Correction: define **retention** = correct baseline items still published by V3 ÷ correct baseline items. Report
  gained items separately. Every lost correct item is listed with its reason code (§B13).

**DR-15 — "Independent labels" were overstated.**
- Problem: an assistant that wrote the rules is not an independent labeller.
- Correction:
  - labels are made **blind to arm**: items from both arms are pooled, deduplicated, shuffled with a fixed seed, and
    the arm hidden;
  - each label records its basis;
  - the report names the labeller as `assistant (blind to arm; not owner-verified)`;
  - the audit kit lets the owner relabel any subset, and re-scoring replaces assistant labels with owner labels.
  - Results are never presented as Builderr scores.

**DR-16 — Held-out data could be contaminated.**
- Correction: the held-out set (`fresh60`) was captured from the baseline **before any V3 code was written**. Its
  outputs are not inspected until the single held-out evaluation after the rules freeze.

### A6. Evidence, refresh and history

**DR-17 — "Same bytes, new code ⇒ retracted" was a heuristic.**
- Correction: candidate-level semantics (§B8).
  - `retracted`: the current run still extracted the same candidate from the source, and a gate rejected it.
  - `removed`: the source page was re-read and the candidate is gone.
  - `not_rechecked`: the source page was not read in this run.
  - `unavailable`: the module had an outage (as today).
  These are unambiguous and testable.

**DR-18 — Refresh rebuilt "previous claims" from previous profiles with current rules** (`pipeline.py:517`).
- Impact: corrections were invisible. It was confirmed live: Revision 1 → baseline refresh for 911771098 gave 0
  events.
- Correction: compare against the **previously published envelope** when one is available, which is the historical
  record. Profiles are still used for outage carry-forward, preserving the refresh fix.

**DR-19 — History retention could delete the only usable baseline, and interrupted runs could become baselines.**
- Correction:
  - runs are written to a temporary directory, with `manifest.json` written last, then atomically renamed;
  - a run is `complete` only if no stop reason was recorded;
  - per company, the baseline is the newest history run in which that company's envelope was `completed`;
  - pruning keeps the newest N (default 10) runs **and** always the newest two complete runs;
  - only directories carrying this tool's manifest marker are ever deleted.

**DR-20 — Code version from parsed `.git` files was fragile.**
- Problem: packed refs, detached heads and dirty trees.
- Correction:
  - `git rev-parse HEAD` and `git status --porcelain -- src scripts pyproject.toml uv.lock` run through `subprocess`
    with a fixed argv, no shell and a 5 s timeout, only when `.git` exists;
  - plus `source_sha256` over the runtime files, which is always present and authoritative.

### A7. Security of the local app

**DR-21 — Missing controls in the draft.**
- Missing:
  - request concurrency bound (a per-connection thread pool is unbounded in `ThreadingHTTPServer`);
  - socket timeouts (slowloris);
  - `Sec-Fetch-Site` defence in depth;
  - snapshot serving restricted to hashes referenced by indexed evidence, not any file in the directory;
  - no stack traces in responses;
  - cancellation;
  - orphan-thread accounting (DR-4).
- Correction: all added (§B12). The app runs no subprocess at all; the code-version helper is never called with
  request data.

### A8. UX

**DR-22 — The draft's comparison flow needed both companies in the dataset, but search results offered no "compare".**
- Correction: search results carry "Add to compare" for researched companies, a compare tray shows the selection, and
  `/compare?orgs=` opens the viewer in comparison mode.
- Every viewer document served by the app has a "← Search" link.
- Phone comparison uses field cards (§B10).

### A9. Tests

**DR-23 — Insufficient positive controls.**
- Correction: each rule family has positive-control fixtures from real captured bytes:
  - 911771098 blog posts;
  - Kilis Hockey plain-slug posts;
  - Grønsand brand profiles;
  - Birralee posts and profile;
  - Granne honest hiring;
  - BioMar `biomarnorge`;
  - Bergknapp own profiles.
- Phase acceptance requires the controls unchanged.

### A10. Contract

**DR-24 — Additive only.**
- New fields:
  - `run.code_version`;
  - `refresh.baseline`;
  - change types `retracted` and `not_rechecked`;
  - claim fields `first_seen_at`, `first_seen_run_id`, `is_new`, `attribution`.
- They are validated when present. Envelopes from V1, Revision 1 and C300 still validate (test).

---

## Part B — Final V3 design

### B1. Invariants (unchanged from the draft; enforced every phase)

| # | Invariant | Evidence |
|---|---|---|
| I1 | Default cost $0; no paid or keyed service; no new dependency | `report.operations.third_party_cost_usd`; `pyproject.toml`/`uv.lock` unchanged |
| I2 | LLM never loaded by the batch command or the app | existing test, extended to the app |
| I3 | One terminal envelope per input row, in input order; streaming, deadline and race fixes unchanged | `test_deadline_streaming`, `test_contract`, replay and live runs |
| I4 | Every published claim cites evidence whose bytes hash-verify | `validate_envelope(snapshot_root=…)` |
| I5 | A source outage is never a company change; unknown is never zero | `test_refresh_semantics`, refresh replay qualification |
| I6 | Identity anchored by organisation number | `test_identity_*` |
| I7 | Platform hosts never contacted; robots, Crawl-delay and public-IP guards honoured | `test_crawl_safety`, host audit |
| I8 | Each deliberate behaviour change is listed in `docs/v3-changelog.md`, with the old test assertion it replaces | review |
| I9 | Envelope changes additive; historical envelopes validate | contract tests |
| I10 | Nothing is called verified unless a check ran; labels carry their labeller | audit code, viewer text |

### B2. `attribution/` package: one decision per question

All functions are pure: no I/O and no network. Each returns a `Decision`:

```python
@dataclass(frozen=True)
class Decision:
    accepted: bool
    code: str                 # stable reason code, e.g. "handle_exact", "sibling_entity_item"
    basis: str                # one plain-English sentence for the viewer and the envelope
    signals: tuple = ()       # (signal, detail, page_url, span) tuples behind the decision
```

| Question | Module | Function |
|---|---|---|
| Target identity | (unchanged) `identity.py`, `pipeline._apply_live_identity` | registry anchor by org number |
| Who operates the website? | `attribution/operator.py` | `assess_operator(profile, site_url, website_value, pages, feeds) -> SiteOperator` |
| How does a handle relate to the legal name? | `attribution/names.py` | `LegalName`, `handle_relation(legal, platform, url) -> Relation` |
| Is this profile the company's? | `attribution/social.py` | `decide_profile(legal, relation, operator, corroboration) -> Decision` |
| Is this item a dated article about this company? | `attribution/news.py` | `classify_item(...)`, `subject_of(...)`, `burst_keys(...)` |
| Is this a single current ad by this employer? | `attribution/jobs.py` | `currency(...)`, `employer(...)`, `decide_job(...) -> Decision` |

`site_facts.extract_site_facts(profile, pages, feeds, operator=None)` calls these. When `operator` is `None`, it is
computed from the pages, so existing call sites and tests keep working.

### B3. `names.py`

**`LegalName(name, municipality=None, post_town=None)`:**
- `tokens` — `identity._tokens`: legal forms and stopwords removed, ASCII-folded, ø→o, å→a, æ→ae;
- `compact` — the tokens joined;
- `phrase_re` — the tokens in order, separators `[\s\-_.&/]*`, with `og`/`and`/`&` interchangeable;
- `brands` — the leading-token prefixes `tokens[:k]` for k < len(tokens), whose compact form has at least 4
  characters and is not a generic word (`bygg`, `eiendom`, `service`, `holding`, `invest`, `drift`, `norge`, …);
- `qualifiers` — the tokens after the first brand that equal the registered municipality, post town, a county, or a
  compass region.

**`handle_relation(legal, platform, url) -> Relation(kind, rest)`.** The handle is folded and compacted, as follows:
- LinkedIn: the path after `/company/` or `/school/`;
- YouTube: the `@handle` or `c/<name>` (a channel id is `UNRELATED`);
- Facebook: the first path segment, with a trailing `-<≥8 digits>` page id stripped; `pages/<Name>/<id>` uses
  `<Name>`;
- Instagram: the first segment.

| Kind | Rule |
|---|---|
| `EXACT` | handle == compact, or compact + a legal-form suffix |
| `EXACT_NEUTRAL` | compact plus neutral affixes only: legal form, `norge`/`norway`/`no`/`nor`/`norwegian`, `official`/`offisiell`, `hq`/`hovedkontor`, the company's municipality or post town, 1–4 digits |
| `BRAND` | handle == a brand (`tokens[:k]` compact), optionally with neutral affixes |
| `EXTENDS` | handle starts with compact or a brand, followed by other text that is not neutral and not distinguishing |
| `OTHER_ENTITY` | handle starts with compact or a brand followed by a **distinguishing** word (`group`, `gruppen`, `konsern`, `holding`, `global`, `international`, `intl`, `invest`, `eiendom`, `capital`, `ventures`, `company`, `worldwide`, `europe`, `nordic`, `scandinavia`, `sverige`, `sweden`, `danmark`, `denmark`, `finland`, `usa`, `uk`); **or** it ends in a legal-form suffix while its words before that suffix differ from the legal name (`tyin-filefjell-as` for TYIN ALPINT AS) |
| `UNRELATED` | otherwise (`grasrota`, `wordpress`) |

### B4. Social decision (`social.py`)

Inputs:
- the relation (B3);
- the operator kind (B5);
- corroboration flags:
  - `domain_brand` — the site's own registrable-domain label equals the compact name or a brand;
  - `org_sameas` — listed in `sameAs` of an Organization node whose `name`/`legalName` matches `phrase_re`.

| Relation | `self` | `group_or_brand` | `other_entity`, `manager` | `platform` (subdomain tenant) |
|---|---|---|---|---|
| EXACT / EXACT_NEUTRAL | accept (0.98 / 0.95) | accept | hold | accept (legal-name handles only, as C300) |
| BRAND | accept only if `domain_brand` and the handle equals that brand (0.9) | hold | hold | hold |
| EXTENDS | accept only if (`domain_brand` and the handle starts with the domain label) or `org_sameas` (0.9) | hold | hold | hold |
| OTHER_ENTITY / UNRELATED | hold | hold | hold | hold |

- The domain-name rule and `sameAs` never accept on their own.
- The cross-link rule (several profiles on one platform) and the "exact linked URL is the value" rule are unchanged.
- Held profiles go to `ambiguous_profiles` with the decision's `code` and `basis`.
- Claims carry `attribution: {code, basis}`.

### B5. Site operator (`operator.py`)

**`stated_org_numbers(page)`** — the visible text (scripts and styles dropped, header and footer **kept**). It returns
9-digit numbers, grouped or not, that pass mod11 and occur within 40 characters after an imprint cue: `org.nr`,
`org nr`, `org. nr.`, `organisasjonsnummer`, `org.no`, `foretaksregisteret`, `NO … MVA`.

**Operator kinds,** first match wins:

1. `manager` — `identity_class == MANAGER_DESIGNATED` (Revision 1).
2. `platform` — the site is on a subdomain of a registrable domain it does not own (C300).
3. `self` — the own org number is stated on any captured page.
4. `other_entity` — at least one other valid org number is stated in imprint context, and the own number is absent.
   `operator_org` holds the first such number.
5. `group_or_brand` — any of:
   - (a) the registry URL's registrable domain differs from the final URL's after redirects (Bartec:
     bartec-technor.no → bartec.com);
   - (b) the `phrase_re` legal phrase occurs on no captured page **and** the domain label is not derived from the
     legal name. "Derived" means the domain label equals the compact name, a brand, the initials of the tokens, or one
     of these plus neutral affixes;
   - (c) `qualifiers` is non-empty, a brand matches the domain label, and the full phrase is absent from the homepage;
   - (d) feed categories name at least two sibling forms `<brand> <other qualifier>`.
6. `self` — otherwise.

**Effects:**
- The website claim is kept for registry-linked sites, with `site_role: own | group_or_brand_site` and `operated_by`
  (other_entity). A *discovered* site with `other_entity` is not published (it becomes `ambiguous`).
- The operator decision, with its signals and spans, is stored in the site record.
- The summary states it in plain words.

### B6. News (`news.py`)

**`classify_item(item, page, ctx) -> Decision`.** Ordered rejections:

| Code | Rule |
|---|---|
| `media_file` | item URL path ends in `.jpg .jpeg .png .gif .webp .svg .pdf .doc .docx .xls .xlsx .zip .mp4` |
| `non_article_path` | a path segment is in the non-article vocabulary: `prosjekt`, `prosjekter`, `referanse`, `referanser`, `portfolio`, `portfolio-item`, `produkt`, `produkter`, `product`, `products`, `shop`, `butikk`, `tjeneste`, `tjenester`, `service`, `services`, `hytter`, `hyttemodeller`, `modeller`, `boliger`, `til-salgs`, `utleie`, `booking`, `kontakt`, `kontakt-oss`, `om-oss`, `about`, `about-us`, `personvern`, `privacy`, plus the existing archive (`category`, `tag`, …) and author paths |
| `listing_not_item` | the item URL is the site root or the listing page itself |
| `default_cms_post` | the folded title is in `{hello world, hei verden, sample page, eksempelside, uncategorized, testinnlegg}` |
| `bulk_entry_burst` | the item belongs to a burst in one source: at least 4 timestamped items within 15 minutes, or at least 5 date-only items on one day |
| `project_category` | feed item whose categories are all non-news taxonomy (non-article vocabulary, or building/project types: `næringsbygg`, `boligbygg`, `bolig`, `referanseprosjekter`, `offentlig`, `rehabilitering`) |
| `page_time_not_article` | `article_time_datetime` item on a page that is neither a news page nor an article-typed page; or its link is excluded above |
| `homepage_card_not_article` | homepage card whose URL is under no news path, dated path or article page |
| `no_article_evidence` | positive requirement failed: none of (URL under a news path or `/YYYY/MM/`), (item from the site's main post feed, i.e. a feed declared on the homepage or `/feed/`, `blog-feed.xml`, not a comments or product feed), or (own page typed Article/NewsArticle/BlogPosting/PressRelease, or `og:type=article`) |

**Dates:**
- `article_time_datetime` prefers `time` with `class~=published`, `itemprop=datePublished` or `pubdate`; otherwise
  the first `time` not marked updated or modified. If only updated times exist, there is no item.
- Feed `<updated>` stays rejected.
- Feeds now also return `categories`.

**Subject — `subject_of(item, legal, ctx) -> THIS | SIBLING | UNSTATED`:**
- THIS — the item's title, summary or own page contains `phrase_re` or the org number; or a feed category equals the
  phrase.
- SIBLING — a feed category or the title names `<brand> <different qualifier>`.

Policy:
- SIBLING is never published (`sibling_entity_item`).
- UNSTATED is published only on `self` sites.
- `group_or_brand`, `other_entity` and `manager` sites publish only THIS.

There is no publication cap (DR-11).

### B7. Jobs (`jobs.py`)

**Dates:** `parse_deadline` accepts dates from 1995 up to 18 months ahead (for `validThrough` and deadlines).
`parse_date` keeps rejecting future publication dates.

**Currency, per posting:**

| State | Evidence | Published? | Basis text |
|---|---|---|---|
| `open` | `validThrough` or stated application deadline ≥ the run date (Europe/Oslo) | yes | "application deadline 2026-11-20 (open)" |
| `recently_posted` | no expiry stated; `datePosted` (or a labelled publication date) within 45 days | yes, never called "current" | "posted 2026-10-20, 12 days before retrieval; no closing date stated" |
| `expired` | deadline or `validThrough` < run date, or `datePosted` > 45 days with no expiry | no | `expired` / `stale_posting` |
| `undated` | no date evidence | no | `currency_unknown` |

**Employer:**
- `hiringOrganization.name`, or a visible label (`Arbeidsgiver:`, `Employer:`, `Bedrift:`, `Firma:`) in the card;
- equal to the target (phrase, EXACT/EXACT_NEUTRAL against compact) → accept;
- any other name → `other_employer`;
- unstated:
  - `self` site and not a recruiter (NACE 78.1/78.2/78.3) → the target (basis: "listed on the company's own careers
    page; no other employer named");
  - recruiter → `employer_unstated_on_job_board`;
  - `group_or_brand`, `other_entity` or `manager` → held (`employer_unstated_on_shared_site`).

**Single advertisement:**
- the job URL must be a detail page: deeper than the careers path, a strong job path, an applicant-tracking posting,
  or a JobPosting on its own page;
- a JSON-LD JobPosting on a news or archive page → `job_on_news_page`;
- generic titles → `generic_recruitment` (existing lists plus `talentbank`, `åpen søknad`, `lærling`/`sommerjobb`
  without a year or trade).

**Careers page claim:**
- it requires the fetched page to pass `is_careers_page` and not be under the non-article vocabulary or
  `for-bedrifter`/`arbeidsgivere`/`for-arbeidsgivere`;
- the anchor must match a career heading or a career path segment (`CAREER_HINTS` becomes segment and whole-word
  matching; the substring `jobb` alone is dropped);
- the summary says "Careers page (a recruitment page, not a job advertisement)".

### B8. Evidence history, change semantics, first-seen, code version

**Code version (`provenance.py`):**

```json
{"source_sha256": "...", "package_version": "...", "git_commit": "...|null", "git_dirty": true|false|null}
```

- `source_sha256` covers the sorted relative paths and bytes of `src/**/*.py`, `scripts/run_competition_batch.py`,
  `pyproject.toml` and `uv.lock`.
- The git fields come from a fixed-argv subprocess (DR-20). They are computed once per process and cached.
- Stamped in `envelope.run.code_version`, `report.code_version`, the history manifest and the viewer header.

**History (`history.py`):**
- `--history-dir` defaults to `<output dir>/signalpost-history`; `--no-history` disables it; `--history-keep` defaults
  to 10.
- Writes `envelopes.jsonl.gz`, `profiles.jsonl.gz`, `report.json` and `manifest.json` (written last) into
  `.tmp-<run_id>-<nonce>/`, then `os.replace` to `<run_id>/`.
- Snapshots are referenced, not copied.
- Pruning follows DR-19.

**Baseline selection, per company:**
1. `--previous-envelopes`;
2. the newest complete history run in which the company's envelope was `completed`;
3. none.

`--previous-profiles` keeps its existing role: carry-forward and the fallback diff. `envelope.refresh.baseline` names
the source: `{kind, run_id, code_version}`.

**Change types (claim level, against the baseline envelope's available claims):**

| Type | Exact condition |
|---|---|
| `added` | available now; absent from the baseline |
| `changed` | the same claim key with a different value (existing rules) |
| `removed` | available in the baseline; absent now; the module answered now; **the claim's source page was re-read now**; the candidate is **not** among the current run's extracted candidates |
| `retracted` | available in the baseline; absent now; the current run extracted the **same candidate** (same canonical key) and a gate rejected it. Carries `rule` (the reason code), `basis`, and both code versions. Wording: "previously published by this agent; withdrawn because …" (never "previously verified") |
| `not_rechecked` | available in the baseline; absent now; the module answered, but the claim's source page was not read in this run (budget or selection). Informational |
| `unverified` | existing (website identity no longer confirmed) |
| `unavailable` | existing (module outage; values carried forward) |

To support `retracted` and `removed`, the site record keeps `candidate_keys` (all extracted candidates, by family and
canonical key, capped at 2,000) and `rejected` (`{family, key, code}`, capped at 2,000), plus the set of fetched page
URLs.

**First seen:** every `social_profile`, `news_item` and `job_posting` claim gets `first_seen_at` and
`first_seen_run_id`, copied from the baseline claim with the same key or set to this run.
- `is_new: true` only when a baseline existed and the key was absent from it.
- With no baseline, `is_new` is omitted and the viewer says "first observation".

**Report:** `code_version`, `history`, `new_items` (counts per family and the baseline id), `checks` (gate decisions
by code — "automatic checks, not accuracy"), and `manual_audit` (B9).

### B9. Audit kit (`audit.py`, `scripts/audit_kit.py`)

**`sample`** — `--envelopes A [--baseline B] [--per-stratum N] --seed S --out DIR`.
- Units: `(org, field, key)` for the fields `official_website`, `social_profile`, `news_item`, `job_posting` and
  `careers_page`.
- With a baseline: every differing unit plus N unchanged units per stratum (category × attribution code).
- Arms are hidden and the order is shuffled.
- Writes `items.csv` and a self-contained `checklist.html` (CSP `default-src 'none'`, `textContent` only). Its cards
  show the value, source link, claim span, retrieval time, snapshot path and registry link. Correct / incorrect /
  unsure buttons and a note field produce a downloadable labelled CSV.

**`score`** — `--labels CSV --labeller NAME --labeller-kind owner|assistant_blind`.
- Per category and arm: n, correct, incorrect, unsure, precision and Wilson 95% CI.
- Retention: correct baseline units still published by V3, over correct baseline units.
- Gained correct units; lost correct units with their V3 rejection codes.
- Writes `audit-results.json` and `.md`.

**`--audit-results` on the batch command** puts `report.manual_audit` into the report and the viewer trust panel.
Without it: `{"state": "not_audited"}`.

### B10. Viewer v2 (`viewer.py`, inline template kept)

- **Plain labels:** one mapping table for terminal status, availability and change types (e.g. `ambiguous` → "Not
  attributed (could belong to another company)").
- **Trust panel:** per category, one sentence on how it is checked, the run's automatic check counts, and the manual
  audit (precision ± CI, labeller, date) or "Not audited".
- **Evidence inspector:** a `<dialog>` drawer from any fact showing:
  - source URL;
  - source type in words;
  - retrieved time;
  - SHA-256;
  - claim span;
  - `attribution.basis`;
  - first seen;
  - the previous value and evidence if changed;
  - an "Open captured copy" link when the app serves snapshots.
- **What's New:** a tab listing new profiles, news and jobs (`is_new`), retractions with their basis, and other
  material changes, filterable by category. Without a baseline it says "No previous run to compare with".
- **Not attributed:** a collapsed section listing held profiles and items with their reasons. These are not counted as
  facts.
- **Phone comparison:** at ≤ 700 px, field cards with one row per company (colour chip, name, value, source link) and
  sticky chips. No horizontal scroll.
- **News display limit:** 10 per company, with "Show all N".
- **App mode** (`render_viewer(..., app={"search": "/", "snapshots": "/snapshot/"})`): a "← Search" link and
  captured-copy links. The page stays self-contained. Its CSP is unchanged except `img-src data:`; links are plain
  navigation.

### B11. Local search application (`app/`, `scripts/serve.py`)

```
uv run python scripts/serve.py --data-dir out/app [--envelopes out/envelopes.jsonl ...] [--snapshot-dir out/snapshots ...]
                               [--bulk brreg-enheter.csv.gz] [--audit-results audit-results.json] [--port 8765]
```

| Module | Role |
|---|---|
| `app/security.py` | Host/Origin/Sec-Fetch-Site/token checks; validators (`org`, `run_id`, `job_id`, `sha256`, search query); rate limiter (token bucket) |
| `app/store.py` | Company index (org, legal name, folded tokens, latest run, researched_at, terminal status, path); imported envelopes are read-only; researched envelopes go under `research/<org>/<run_id>/` with atomic writes; directory mode 0700, file mode 0600; snapshot hash set from indexed evidence |
| `app/registry_search.py` | Name/number lookup outside the dataset. The bulk-file token index if `--bulk` is given; else one fixed endpoint `https://data.brreg.no/enhetsregisteret/api/enheter?navn=<urlencoded>&size=20` through `http.fetch_json`; ≤ 20 results; a 10-minute cache |
| `app/research.py` | Job manager: at most 2 live research threads (counting orphans, DR-4), queue ≤ 20, de-duplication by org, cancel through `stop_event`, a 120 s deadline. Runs `run_batch([InputRow(0, org, org)], …, deadline_seconds=120, workers=1, progress=…, previous_envelopes=<latest>)`. Stage names are derived from the profile's evidence keys |
| `app/pages.py` | Search page HTML/CSS/JS as constants: search box, results, research cards, compare tray, What's New link |
| `app/server.py` | `ThreadingHTTPServer` (loopback), handler with a 10 s socket timeout, a request semaphore of 32 (503 when exceeded), routing, JSON responses, viewer documents through `render_viewer` |

**Routes:**

| Route | Validation | Result |
|---|---|---|
| `GET /` | — | search page (token in `<meta>`) |
| `GET /api/search?q=` | 1–100 chars; contains a URL scheme, `/`, `@` or a domain-like `x.tld` → 400 "Search by company name or organisation number"; a 9-digit number must pass mod11 | `{query_kind, local[≤20], registry[≤20]}` |
| `GET /company/<org>` | `^\d{9}$` + mod11; in the index | viewer document for that company (latest run) |
| `GET /compare?orgs=` | 2–4 valid, indexed | viewer document in comparison mode |
| `GET /whats-new` | — | viewer document of all indexed companies, What's New tab |
| `POST /api/research` | JSON `{org}` only, body ≤ 4 KB, token + Origin + Sec-Fetch-Site, rate 10/min | `202 {job_id}` / `200` existing |
| `GET /api/jobs/<id>` | `^[0-9a-f]{32}$` | `{state, stage, elapsed_s, org, result: {terminal_status, partial_sources[]}, error}` |
| `POST /api/jobs/<id>/cancel` | as for research | `{state}` |
| `GET /snapshot/<sha256>` | `^[0-9a-f]{64}$`; the hash must be in the indexed evidence set; the path resolves inside a snapshot dir | bytes as `text/plain; charset=utf-8` attachment, `nosniff`, CSP `sandbox` |

**States the search page renders:** empty, searching, results (in dataset / not yet researched), no match, invalid
input, queued, running (stage + elapsed), completed (link opens the profile), partial (failed sources listed, "Try
again"), failed (invalid number / not in registry / deleted entity / registry unreachable / rate limited /
cancelled), and stale (more than 30 days old → "Re-check", which diffs against the previous run).

### B12. App security model

| Threat | Control |
|---|---|
| Exposure on the network | Bind `127.0.0.1` only; any other `--host` requires `--allow-remote` and prints a warning |
| DNS rebinding | `Host` must be `127.0.0.1:<port>` or `localhost:<port>`; otherwise 421 |
| CSRF | POST needs the per-process 32-byte token (`hmac.compare_digest`), `Origin` equal to the server origin, and `Sec-Fetch-Site` absent or `same-origin`. No cookies |
| SSRF / arbitrary fetch | Inputs are names and org numbers only; the URL-like query is rejected; research URLs come only from the registry record and existing discovery, behind the existing guards; registry search uses one fixed endpoint |
| Stored XSS from captured pages | Snapshots served only as a `text/plain` attachment with CSP `sandbox`; viewer and search page use `textContent` only; CSP `default-src 'none'` (+ `connect-src 'self'` on the search page) |
| Path traversal | Regex-validated parameters; resolved paths must stay inside configured roots; snapshot hashes must be indexed |
| Resource exhaustion | Socket timeout 10 s; request semaphore 32; body ≤ 4 KB; research threads ≤ 2 (orphans counted); queue ≤ 20; research 10/min; registry search 30/min; per-company deadline 120 s |
| Command execution | The app runs no subprocess; nothing derived from a request reaches a shell or the file system unvalidated |
| Information leakage | Errors return a code and a short message, never a traceback; the log records method, path (query cut to 20 chars) and status |
| Privacy | Existing birth-date redaction; data dir 0700; the app is a local, single-user tool |
| Failures and timeouts | Every job ends in a terminal state (completed / partial / failed / cancelled); the envelope's own `terminal_status` is shown; nothing partial is presented as complete |

### B13. Measurement methodology

**Sets** (inputs committed with SHA-256 under `measurements/v3-2026-11-01/inputs/`):

| Set | Size | Role |
|---|---|---|
| fixtures | ~16 companies (captured bytes in `tests/fixtures/v3/`) | deterministic regression in the test suite |
| smoke100 | the committed smoke set (`80eb79e6…`) | continuity with every earlier measurement |
| midsize40 | the 40-company sample where the defects were found (`1420d35a…`) | development set |
| fresh60 | 60 new companies with websites, 10–300 employees (`554c111f…`) | **held-out**: captured before any V3 code; evaluated once after the freeze |

**Procedure:**
1. The baseline (`ff3b515` tree) runs live with snapshots. This was done for all three sets before V3 coding.
2. `scripts/replay_run.py` replays a captured run through any code tree. The baseline itself is replayed too, so both
   arms see identical bytes; this also measures replay fidelity, i.e. differences between the live baseline and the
   replayed baseline.
3. `audit_kit sample` → blind labels → `score`.
4. Wilson 95% intervals; small-n categories are reported, never rounded up.

**Label rubric** (also written into the checklist):
- **social** — correct iff the profile belongs to this legal entity: its handle or name is this company's, not a
  parent, group, sister, platform or unrelated account.
- **news** — correct iff it is a dated article (post, press release or news), published on the stated date as far as
  the page shows, about this company or its own activities; not a product, service, project or reference page, listing
  or default post.
- **job** — correct iff it is a single advertisement for a position at this company, currently open or recently posted
  as stated.
- **careers_page** — correct iff it is this company's page about working there.
- **website** — correct iff it is this company's website (registry-linked counts).

**Gates (local engineering targets, not Builderr scores):**

| Metric | Gate |
|---|---|
| Social precision (dev + held-out pooled) | ≥ 95% point estimate, ≥ the baseline's, and 0 published OTHER_ENTITY/UNRELATED handles |
| News precision | ≥ 90% point estimate and ≥ the baseline's |
| Job precision | ≥ 90% if n ≥ 10; otherwise every item reported and 0 confirmed expired or third-party |
| Careers-page precision | ≥ 90% |
| Retention per category | ≥ 85% of the correct baseline units; every lost correct unit listed with its code; a rule causing > 5 losses is re-examined |
| Website set | identical to the baseline on replay (discovery untouched) |
| Contract | 0 findings; hashes re-verified |
| Performance | replay runtime within +10%; 0 new hosts in the live smoke check |

### B14. Rollback

- Every phase is a separate commit series.
- Each new rule family has a module-level switch constant (`attribution.*.ENABLED`), used only by tests and by the
  rollback procedure. Reverting a phase is `git revert <phase commits>`; the contract stays additive, so older readers
  are unaffected.
- The previous candidate stays at `ff3b515` (`claude/c300-refresh-fix`).

### B15. Out of scope (with reason)

- Website discovery recall: unrelated to the evaluator's findings.
- Platform fetching: the standing rule forbids it.
- The LLM: off by default.
- Hosted deployment: the owner's constraint.
- Evergreen-article tagging: DR-12.
