# Signalpost V3.1 — news classification accuracy remediation: release report

**Status:**
- Not pushed, not submitted, not scored by Builderr.
- **V3.1 candidate 2** (code `334a085`, local tag `v3.1-candidate-2`): candidate 1 plus one entity-resolution
  correction for companies abroad that share the name (LOGSCOM AS / Logscom AB). The news rules are unchanged. See §10.
- V3.1 candidate 1 (`v3.1-candidate-1` on `00e644a`, code `0e4c426`) is unchanged; §1–§9 describe it.
- V3 candidate 2 (`v3-candidate-2`, code `7b8fc69`) is unchanged.

**Outcome in one paragraph.**
- On a new independent sample (eval200b, 200 organisations, scored once), V3.1 news precision is **105/131 = 80.2%
  (95% CI 72.5–86.1%)**, against 60.6% for candidate 2 and 45.5% for the baseline. **The ≥90% target is not met.**
- Social is **68/68 = 100% (CI 94.7–100%)**; the target is met on this sample.
- Careers pages are 7/7, too few to establish a rate. Job ads are not validated.
- V3.1 keeps 70.6% of the baseline's correct news items, against 93.0% for candidate 2.
- Every published news item now states why it qualifies (`attribution`).
- The remaining errors are content marketing and opinion written on companies' own sites. No deterministic rule tested
  separates them reliably from genuine news.

Detail is in `docs/v31-news-analysis.md`. Every number below links to an artefact in
`measurements/v31-2026-11-01/`.

## 1. Root-cause analysis of the 29 eval120 errors

`docs/v31-news-analysis.md` §1–§2 analyses each item: company, organisation number, URL, title, captured body, source,
date evidence, entity, why accepted, why wrong, systematic or isolated. The data is in
`measurements/v3-remediation-2026-11-01/audits/eval120/diag-29-errors.json`.

| Category | Errors | Mechanism |
|---|---|---|
| A1 property, plot and project listings | 7 | accepted on a blog or feed path; no rule read the body |
| A2 reader advice | 8 | the advice rules read titles only |
| A3 promotional or thought leadership | 3 | blog cards with a visible date |
| A4 service or membership pages | 2 | a blog post and a page under `/blog/nyheter/` |
| B group-brand stories (BE Kraftsalg) | 5 | the site is named after the registry parent; V3 treated every name on it as the subsidiary's |
| C CMS pages in the feed (FFOR) | 3 | a course page, a topic page, a welcome post |
| D general law article | 1 | `/aktuelt/` listing |

All 29 were accepted on **where** they appeared, never on **what they say**. 26 did not name the company at all.

The "Du store verden" analysis is in §3: the text, not the title, separates it from advice. The social errors are in
§4: the same BE Kraftsalg mechanism. §6.1 corrects the BE description: bodoenergi.no is BE Kraftsalg's own site,
trading under the parent's brand.

## 2. Comparison of approaches

`docs/v31-news-analysis.md` §6 (first freeze) and §9 (second freeze) cover eight policies, from "current rules" to
"newsroom + item + content + exact entity", plus `layered`, `hybrid`, `anchored` and `strict`. All were measured on
every labelled set, with false positives and retained correct items.

- The dedicated-news-section policies reach high precision only by publishing almost nothing (1–35% retention).
- A news section was not evidence on its own: 7 of the 29 eval120 errors were under `/aktuelt/`.
- `strict` (outside a news section, require an attributed development) reached 96.6% on eval200 as a development set,
  but gutted the positive controls: 911771098 16→2, Birralee 18→2, IKA Hordaland 10→2. It was rejected.

## 3. Final architecture (code `0e4c426`)

1. **Item gate (unchanged from V3):**
   - media files, project and portfolio paths, default CMS posts, bulk bursts, dates that contradict the title, and
     feed items outside the news section are rejected;
   - the date is the published time, never "updated";
   - publishers' journalism is not their news.
2. **Entity:**
   - V3's operator assessment;
   - **new:** a site whose domain is named after another company in the registry group structure is `group_or_brand`
     (`site_named_after_registry_group_company`), even when it states the company's own organisation number;
   - **new:** site-wide text (header, footer, nav, aside, any line repeated on the homepage, feed "appeared first on"
     lines) never counts as an item naming the company.
3. **Subject (unchanged):** an item about a named sibling or another company is withheld.
4. **Content (new, `attribution.news.assess_content`):** what the item's own captured words say.
   - **Negative → withheld:**
     - advice: advice and listicle titles, reader-addressing text, article-marketing markers;
     - listing;
     - product or rental item;
     - service, commercial offer or standing-page title;
     - job advertisement.
   - **Positive → published, with the reason recorded:**
     - `development`: an event attributed to the company in the title, in its voice in that sentence or a neighbouring
       one, or in a sentence naming it;
     - `company_named`;
     - `company_voice`.
   - **Otherwise → withheld** (`not_anchored_to_the_company`). A news section never suffices on its own.
5. **Provenance:** every published `news_item` carries `attribution {code, basis, source_tier, evidence}`, with the quoted
   span. Withheld items are counted by reason in the claim's reason.

Cost is $0. No LLM, no new dependency, no new request: the content layer reads only bytes already captured. No
social-platform page is fetched.

## 4. Regression tests

The full suite passes: **526 tests and 172 subtests** (487 at candidate 2), in the working tree and in 3 of 3 clean-room runs.

**New tests.**

| Test | What it pins | Fails on |
|---|---|---|
| `tests/test_v3_regressions.py::V31NewsContent` (8) | the eval120 errors, on their captured bytes: Huspro listings, opts advice, Nordic Solutions listicles, SOBBL service pages, Day of Week thought leadership, FFOR course page, Sabi Sushi job ad, BE Kraftsalg news and social, Frosterød, Sjokoladesmaking, Kystsnekker'n | `7b8fc69` |
| `tests/test_v3_regressions.py::V31AfterEval200` (6) | the eval200 and live failures: Steinkjer Liftutleie product pages, Vårtun and Logscom job ads, Lugn boilerplate, Frankeringsrekvisita, Sola Hundesenter and Provendo marketing and advice, BE Kraftsalg footer (live capture); plus eval200 controls (Proba, IKA Hordaland, Steinerskolen i Ås, Jentene på Tunet) | `8223a37` |
| `tests/test_v31_news.py` (25) | unit tests for source tier, every content kind, company names (genitive, domain label as words), voiced and attributed developments, sentence breaks, boilerplate, the policies, the registry-group rule, site chrome | — |

**Positive controls retained.**
- Kilis plain-slug WordPress posts: 10/10.
- 911771098: 16, including "Du store verden", kept because its text reports the books' translations in the author's
  voice.
- Proba 9, IKA Hordaland 10, Steinerskolen 8, Jentene på Tunet 8.

**Changed expectations,** each with its reason in the test:
- synthetic item-gate feeds gain a description in the company's voice;
- Birralee 20→18, Grønsand 15→14, Beredt 6→5 and 911771098 20→16. The items whose captured text never names the
  company or speaks in its voice are named in the tests.

## 5. Baseline versus new: all measurements

News precision, with retention in brackets. Retention is correct baseline items still published: a recall proxy, never
true recall.

| Set (role) | Baseline `ff3b515` | Candidate 2 `7b8fc69` | Freeze 1 `8223a37` | **V3.1 `0e4c426`** |
|---|---|---|---|---|
| Tuned sets (developed on) | 47.7% | 95.0% (95.9%) | 97.5% (74.3%) | 98.2% (69.6%) |
| fresh60b (consumed) | 73.2% | 100% (100%) | 100% (57.7%) | 100% (53.8%) |
| eval120 (scored once on `7b8fc69`; then diagnostic) | 14.6% | **25.6%** independent | 63.6% | 66.7% |
| eval200 (scored once on `8223a37`; then development) | 36.5% | 45.5% (74.3%) | **56.8% (52.9%)** independent | 90.2% (52.9%), tuned |
| **eval200b (new, scored once on `0e4c426`)** | 45.5% | 60.6% (93.0%) | 71.6% (71.3%) | **80.2% (70.6%)** independent |

Each version's independent number is the bold one in its column. The development-set numbers are optimistic: 98.2% on
the tuned sets against 80.2% independent.

## 6. Fresh independent evaluation and release validation

**eval200b** (`docs/v31-news-analysis.md` §10).
- 200 organisations newly drawn with a new seed, excluding all 2,014 organisations used before.
- Captured live through the baseline before the second freeze and opened only after it.
- Census of 448 units, labelled once (`assistant_blind`, blind to version, captured text visible) and scored once.

| eval200b | Baseline | Candidate 2 | **V3.1** |
|---|---|---|---|
| News | 143/314 = 45.5% (40.1–51.1) | 137/226 = 60.6% (54.1–66.8) | **105/131 = 80.2% (72.5–86.1)** |
| News retention | — | 133/143 = 93.0% | 101/143 = 70.6% |
| Errors removed / introduced vs baseline | — | 82 / 0 | 145 / 0 |
| Social | 72/78 = 92.3% | 68/68 | **68/68 = 100% (94.7–100)** |
| Careers pages | 8/13 = 61.5% | 7/7 | 7/7 (64.6–100) |
| Unsure (news) | 34 | 33 | 15 |

**Release validation of `0e4c426`** (`measurements/v31-2026-11-01/release-0e4c426/`, from a clean worktree, live
2026-11-02).
- **100 companies:** all 100 completed; validation passed; no contract findings, with all 3,993 evidence hashes
  re-checked; 0 unsupported summary statements; $0; no LLM; 196 hosts, none a restricted social platform; viewer
  written; 133 s. Published: 14 websites, 12 social profiles, 29 news items, 4 careers pages.
- **Refresh:** baseline = the published envelopes (100/100). 2 `unavailable` events (sources unreachable at refresh,
  last values retained). Same published facts.
- **Reproductions (8):**

| Company | Result |
|---|---|
| ASAK (961592097) | no ASAK MILJØSTEIN profiles |
| Ashtead (995284766) | no global LinkedIn |
| Tyin (983181732) | site operated by another company; no profiles |
| Bartec (980932834) | group site; 53 group stories withheld |
| Bergknapp (995596970) | its 3 own profiles; no project posts |
| BK Bygg (995159406) | its 2 profiles; the bulk burst withheld |
| **BE Kraftsalg (990892687)** | no news (the live footer defect of `8223a37` is fixed); no profiles; website kept |
| 911771098 | 16 posts, including "Du store verden" |

- **Clean room** (`measurements/v31-2026-11-01/cleanroom-0e4c426/`): a fresh clone at `0e4c426` with an empty uv cache.
  `uv sync --locked` exit 0; **3 of 3 suite runs with 526 passed and 172 subtests passed**; the documented batch
  command (911771098) exit 0.
- The refresh's 2 `unavailable` events were 929336038 (site HTTP error; careers page and profiles retained) and
  980807568 (robots.txt unreachable; website retained). Neither was reported as a removal.
- **The first freeze `8223a37` was validated the same way** (`release-8223a37/`, `cleanroom-8223a37/`: 3 × 513 passed).
  Its live run exposed the BE Kraftsalg footer defect that freeze 2 fixes.

## 7. Social and careers results

**Social.**
- eval200b: 68/68 (100%, CI 94.7–100), retention 66/72 = 91.7%.
- eval200: 73/75 = 97.3%. The 2 errors are LOGSCOM AS: the site and profiles belong to the Swedish Logscom AB.
- eval120: 40/40 after the registry-group rule (40/43 before). Tuned sets 114/114; fresh60b 55/55.
- Precision did not come from removing profiles: retention is unchanged by V3.1, and the registry rule removes only
  the 3 BE profiles on every set.

**Careers pages.**
- eval200b: 7/7.
- eval200: 4/4, plus 2 unsure: a shopping centre's vacancies page and a chain's jobs page.
- These are too few to establish a rate.

**Job ads.** None was published by V3 versions on eval200 or eval200b. The baseline published one, labelled unsure.
Job-ad accuracy is **not** validated, because there is no labelled sample of published job ads. Job advertisements on
news feeds are now withheld from news.

## 8. Known remaining errors

- **News (eval200b, 26 of 131 decided):**
  - guides, explainers and thought leadership: 12;
  - product, service, reference-project and supplier marketing: 8;
  - opinion, appeals and promotional profiles: 4;
  - job advertisements phrased "søker nå etter en …": 2.

  Concentration: 11 of the companies with published news. Agenta, Fram Marine, Tiny Elephant, Comfort Solskjerming and
  Rosim account for 18.
- **Structural:**
  - "names the company" (81%) and "speaks in its voice" (71%) are weak evidence on a company's own site;
  - an attributed development is 86%;
  - with a deterministic lexicon, none reaches 90% independently.
- **Earlier sets** (tuned, still present): Solregn customer reminders in the company's voice; the Kellners welcome
  page; the Oslo PT third-party promotion (eval120); Kameo's product landing page (eval200).
- **Entity:** a company whose verified site belongs to a foreign sister company with no registry group link (LOGSCOM
  AS / Logscom AB). Its news is withheld only when the text gives it away; its profiles are published. **Fixed in
  candidate 2 (§10).**
- **Retention:**
  - correct items whose captured text neither names the company nor speaks in its voice are withheld (school class
    reports, title-only cards);
  - recruitment posts are no longer news;
  - BE Kraftsalg's own stories that use the trading name "Bodø Energi Kraftsalg" are withheld.
- **Labels:** all labels are `assistant_blind` by the author of the rules, made blind to version and with the captured
  text visible. They are not owner-verified.

## 9. Recommended commit

- **Recommended candidate: `v3.1-candidate-1`.** Code `0e4c426`; the tag points at the final docs and measurements
  commit, which is code-identical.
- It is the best-measured version on independent news data (80.2% against 60.6% for candidate 2). Social and careers
  results are unchanged or better.
- **News does not meet the ≥90% target.** Before deciding to submit, weigh:
  - V3.1 publishes fewer news items (retention 70.6% against 93.0%);
  - one in five published news items is still wrong.

The exact SHAs are in `docs/final-submission-manifest.md` and `HANDOFF.md`.

## 10. V3.1 candidate 2 — companies abroad that share the name (code `334a085`)

You asked for this correction without any change to the news rules, without company-specific exclusions or URL lists,
and without tuning against eval200b.

### 10.1 Reproduction

On `0e4c426`, the eval200 capture of LOGSCOM AS (830872752; fixture `tests/fixtures/v3/830872752`) publishes:
- `https://www.facebook.com/logscom`, with the attribution `handle_exact`;
- `http://instagram.com/logscom_ab`, with the same attribution.

Both are labelled **incorrect** in the eval200 audit: they are the profiles of Logscom AB, Åsele, Sweden. The
regression test `SharedNameAcrossBorders.test_logscom_as_does_not_take_the_swedish_logscom_ab_profiles` reproduces
this; it fails on `0e4c426`.

### 10.2 Identity chain, and why `0e4c426` accepted both profiles

1. **Registry.**
   - LOGSCOM AS was registered in 2022 in Lillehammer. Its registered purpose is to sell "det svenske
     morselskapets produkter".
   - Its `hjemmeside` is `logscom.com`, so the site is registry-linked.
   - Brreg `konsernstruktur` is not_found. Norway's registry records no group with a foreign parent, so the existing
     registry-group rule (`site_named_after_registry_group_company`) cannot fire.
2. **Site operator** (`attribution/operator.assess_operator`).
   - The site's title is "We make logs communicate - Logscom AB", and its contact is "Logscom AB Blåviksvägen 11
     SE-91931 Åsele Sweden".
   - It states no Norwegian organisation number at all, neither 830872752 nor another's. It does not redirect, and
     the domain carries the company's name.
   - With no contrary signal, the operator was `self` / `no_contrary_signal`.
3. **Handle relation** (`attribution/names.handle_relation`).
   - `logscom` equals the distinctive name, so it is EXACT.
   - `logscom_ab` is "logscom" plus "ab". "ab" was in the neutral legal-form list, which also accepts "as", "asa",
     "sa" and "ab", so this was also EXACT.
4. **Decision** (`attribution/social.decide_profile`). An EXACT handle on a `self` site is accepted as the company's
   own.

The weak link is step 2. The site does name its operator, a company with the same name under a Swedish legal form.
Step 3 then treats that foreign form as if it were this company's own.

### 10.3 The general rules

| Rule | Where | Condition | Effect |
|---|---|---|---|
| A foreign legal form names another entity | `names.py` (`FOREIGN_FORMS`, `LegalName.foreign_form`) | A handle ends in AB, GmbH, Ltd, Limited, Inc, ApS, Oy, Oyj, AG, LLC, PLC or BV, and the company's own registered name does not carry that form. | `OTHER_ENTITY`, so the profile is held (`handle_names_other_entity`). |
| The site of a foreign namesake | `operator.py` (`foreign_namesake_named`, code `site_of_a_foreign_namesake`) | The verified site names "<this company's name> <foreign form>", never "<name> <own form>", and does not state this company's organisation number. That last check runs earlier and returns `self`. | The operator is `group_or_brand`. The existing rules for that operator then hold the bare shared-name handle (`group_name_handle_on_group_or_brand_site`) and withhold stories not about this company. The registry-linked website itself stays published, with the role `group_or_brand_site`. |

- **Why the rules are general.** They use only the legal form, which is how registers tell separately registered
  companies apart. They use no company name, domain or URL.
- **NUF.** A NUF (a Norwegian branch of a foreign company) carries the foreign form in its own registered name, e.g.
  "KAMEO INVESTMENT PLATFORM AB NUF". For a NUF the form counts as its own and nothing changes.
- **Danish companies.** The Danish "A/S" cannot be told apart from the Norwegian AS, so it is deliberately not a
  foreign form.

### 10.4 Effect on legitimate profiles

Every captured set was replayed through `334a085` and compared with the stored `0e4c426` replays:
- the sets are smoke100, midsize40, fresh60, fresh60b, diag80, eval120, eval200 and eval200b;
- together they hold 860 organisations, 411 of them with a verified site;
- the evidence is in `measurements/v31-2026-11-01/namesake/`.

- **The only change in published units or operator decisions is Logscom.**
  - Its operator becomes `group_or_brand/site_of_a_foreign_namesake`.
  - Its 2 incorrect profiles are withheld.
  - Its website is kept, and its news was already empty.
- **No profile labelled correct is lost on any set.**
- After the change, **no labelled set publishes an incorrect social profile.**
  - eval200 social goes from 73/75 to 73/73 decided.
  - eval200b stays at 68/68. It was not used to develop or tune this change.
- **Legitimate controls**, captured and pinned as regression tests that pass on both `0e4c426` and `334a085`:

  | Control | Organisation | Behaviour, unchanged |
  |---|---|---|
  | Kameo NUF | 932468352, eval200 | Operator `self`, from its own organisation number. Its 3 profiles, all labelled correct, are kept: `kameo-norge`, `kameo.norge` and `KameoNorge`. |
  | Alpha Solutions Norge AS | 921147325, eval200b | The registry site redirects into the international group's site (an existing rule). The US group's profiles (`alpha-solutions-usa`, `alpha_solutions_us`; labelled incorrect) stay held. |

- **One eval120 news unit differs from the stored replay. It is not caused by this change.**
  - The unit is 955599535, `fib.no/stottespillere/sparebankstiftelsen-dnb`, dated 2026-11-04.
  - `0e4c426` replayed on the same day publishes the identical 126 units.
  - The date is the page's application deadline ("Søknadsfrist: 4. november 2026"). It was rejected while it lay in
    the future, and it passes once it is the run date. See §10.6.

### 10.5 Tests and validation of `334a085`

- **New tests.** All pass on `334a085`.
  - 3 regression tests on captured bytes (`tests/test_v3_regressions.py::SharedNameAcrossBorders`): Logscom (the
    defect), Kameo NUF and Alpha Solutions (the controls).
  - 4 unit tests (`tests/test_v3_attribution.py::ForeignNamesakes`): foreign-form handles, NUF own forms,
    `foreign_namesake_named`, and the operator with and without the company's own organisation number.
  - **On `0e4c426`, the 4 Logscom/defect tests fail and the 3 control tests pass.**
- **Suite.** 533 passed (526 earlier plus 7), including the existing social positive controls: Bergknapp, BioMar
  Norge, BDT Viken, Grønsand, Birralee, Beredt, Bjelland and the others in `SocialAttribution` and `HandleRelations`.
- **Clean room** (`measurements/v31-2026-11-01/cleanroom-334a085/`): a fresh clone at `334a085` with an empty uv
  cache. `uv sync --locked` exit 0; **3 of 3 suite runs with 533 passed and 175 subtests passed**; the documented
  batch command (911771098) exit 0.
- **Live release validation** (`measurements/v31-2026-11-01/release-334a085/`, 2026-11-04): a clean worktree,
  `run_release.sh`.

  | Run | Result |
  |---|---|
  | live 100 | 100/100 `completed`; 0 contract findings (3,995 hashes re-checked); $0; no LLM; no restricted host |
  | refresh | baseline = the published envelopes; 2 `unavailable` events, last values kept (as on `0e4c426`) |
  | 8 reproduction companies | as intended |

  - The published site facts are identical in count to `0e4c426`'s live run of 2026-11-02: 12 profiles, 4 careers
    pages, 14 websites and 29 news items.
  - The one unit-level difference is Kilis Hockey (875606662). It published "Bli med på moroa" on 2026-11-03, between
    the two runs, and the newest-items window dropped the oldest post. One extra withheld check comes from the same
    new post. Both are changes on the live site, not code effects.

### 10.6 Remaining risk

- **A foreign namesake that never writes its legal form.** If the site says only "Logscom", there is no evidence that
  separates the two companies. The site stays `self`, and a bare-name handle is still accepted. No reliable rule
  exists without a foreign registry lookup, which this agent does not do.
- **Forms not in the list.** These include SA/SAS/SARL, SRL, S.p.A., Pty, KK and AB(publ) spellings. The list covers
  the Nordic, German, British, Dutch and US forms found in Norwegian registrations. Danish A/S is excluded on purpose.
- **Norwegian namesakes** (two AS companies with one brand) are unchanged. They are still handled by the
  organisation-number, sibling and registry-group rules, and remain at risk when the site names neither company.
- **Over-holding.** A Norwegian company whose site names only its Swedish sister "X AB", and never "X AS" or its own
  number, now has its bare-name profiles held. This cost no labelled-correct profile on any captured set. It errs
  towards withholding, which is the qualification-safe direction.
- **News date defect (existing, not fixed: the news rules are frozen).**
  - A stated application deadline ("Søknadsfrist") can be read as a publication date.
  - It is rejected only while it lies in the future, so on or after the deadline day the item can publish (fib.no on
    eval120).
  - This affects `0e4c426` and `334a085` equally. A fix belongs to a news-rule change, with its own evaluation.

### 10.7 Recommended release

- **Recommended: `v3.1-candidate-2`.** Code `334a085`; the tag points at the docs and measurements commit on top,
  which is code-identical.
- It is `v3.1-candidate-1` plus a correction that removes the 2 known wrong-company profiles. It changes nothing else
  on 860 captured organisations. The news-classification code is unchanged: only `attribution/names.py` and
  `attribution/operator.py` differ from `0e4c426`.
- The news target is still not met (eval200b 80.2%). That result applies unchanged, because eval200b's outputs are
  identical under `334a085`.
