# Signalpost V3.1.1 — Builderr rescoring revision (wrong-company claims, verified news and job ads)

Branch `revision/v3.1.1-builderr-rescore`, based on V3.1 candidate 2 (`139e23c`, code `334a085`), the tip of
`claude/awesome-sagan-m2lppu`. That branch, its tags and `ff3b515` are unchanged. Gemini is not in this branch (no code
from `experiment/v3.2-hybrid`); no LLM is imported. Nothing has been pushed or submitted.

## 1. Evaluator feedback and what could be reconstructed

Builderr audited the previously submitted commit **`ff3b515`**. Result: rank 2/104, about 69/100, 86 claims checked,
75 correct, **11 belonging to another company** (87%). Qualification needs ≥65/100 **and** ≥95% correct attribution.
The evaluator asked for two changes:
1. remove every claim that belongs to a different company;
2. add dated company news and open job postings, linked from the company's own website ("we have nothing verified
   from you there").

**Confirmed by the evaluator (2 of 11).** LØWEHJERTE DESIGN AS (987832827):
`https://www.linkedin.com/company/squarespace/mycompany/verification/` and `http://facebook.com/squarespace`.

**Reproduced.** `ff3b515` run live on 2026-11-13 publishes exactly these two URLs, with confidence 0.95 and the basis
"listed in sameAs of the verified site's own Organization structured data". The captured homepage (`www.lowehjerte.no`, a
Squarespace site) carries Squarespace's template defaults in its Organization JSON-LD:
`"sameAs":["http://twitter.com/squarespace","http://facebook.com/squarespace","https://www.linkedin.com/company/squarespace/mycompany/verification/"]`
(fixture `tests/fixtures/v311/987832827/`).

**Not reconstructable: the other 9.** Builderr's sample, its 86 claims and its labels are not in the repository or
available to us; LØWEHJERTE DESIGN AS is in none of our sets. We do not guess them. Instead, §5 measures `ff3b515`,
V3.1 and V3.1.1 on a **new, never-used sample (eval-r300)** with every published external claim labelled, which shows the
classes of wrong-company claim `ff3b515` produces and whether V3.1.1 still produces them. Those are *our* findings, not
the evaluator's 11.

## 2. Root causes of wrong-company attribution in `ff3b515`

| Class | Mechanism in `ff3b515` | Status in V3.1 (`334a085`) | V3.1.1 |
|---|---|---|---|
| Website-builder template accounts (LØWEHJERTE / Squarespace) | Any profile in the `sameAs` of an Organization node whose `url` is on the verified site was accepted at 0.95, whatever its handle. Builder templates fill `sameAs` with the builder's own accounts. | Already withheld (handle unrelated to the legal name); no explicit rule, and the canonical form dropped the `/mycompany/verification/` path. | URL-level owner checks run **before** the handle decision and cannot be overridden by `sameAs` or link text: platform/builder accounts and platform admin/verification URLs are never a company's profile. |
| Group/parent accounts on a subsidiary's site | A brand handle on the subsidiary's (often international) site was accepted. | Partly (registry group site rule, foreign namesake rule). Still published on evalh400/evalg250: VALMET AS → `linkedin/company/valmet` (parent NELES CONTROLS OY), BECTON DICKINSON U.K. LIMITED → `becton_dickinson`, THREE60 ENERGY NORWAY AS → `linkedin/company/three60energy`, TEQT NORGE AS → `se.linkedin.com/company/teqt`, INLUMI AS → `nl.linkedin.com/company/inlumi`. | Withheld by registry/URL rules (§3). |
| Sister company handle spelled with its own legal form | `BirkelandTyseBergsprengerAs` on BIRKELAND AS's site (CamelCase hid the "As"). | Published | Parsed as another entity's legal name. |
| Group news on a subsidiary's site | News on a verified site was attributed to the company. VALMET AS: 30 of 30 published items were Valmet Oyj stock-exchange releases; TEQT NORGE AS: "Teqt Group vokser gjennom oppkjøpet av …". | Still published (V3.1 relies on the item naming the brand). | Group-site and national-unit rules (§4). |
| Job board of other employers | FUNDRAISING NORGE's careers page links finn.no ads "Fundraiser, Norges Røde Kors", "Innsamlingsansvarlig, Caritas Norge". | Still published: all 5 job ads V3.1 published on evalh400 were these. | Employer named in the title is checked; off-site ads need a verified employer; such a page is not the company's careers page. |
| Not news (guides, product pages, opinion, promotions, other organisations' events) | `ff3b515` published 33–44% correct news on labelled sets. | 46–80% depending on the set. | Announcement tier (§4). |

## 3. Social changes (`attribution/social.py` `owner_check`, `attribution/names.py`, `site_facts.py`)

Applied to every linked profile before the handle decision; each returns a withholding decision with a code and a plain
reason, kept in the envelope as an `ambiguous` social claim. No company is named in any rule, and nothing is fetched
from a social platform.
* `not_a_public_profile_url` — a platform admin, verification, settings or login path (`/mycompany/`, `/admin/`,
  `/verification/` …).
* `platform_provider_account` — the handle is a website-builder, hosting, CMS or social-platform account
  (Squarespace, Wix, WordPress, Shopify, …), unless it is exactly the company's own legal name.
* `group_account_without_national_unit` — the legal name marks a national unit ("NORGE", "NORWAY", "U.K." …), the handle
  leaves the marker out, and the site is not on `.no` or the link is localised to another country.
* `foreign_parent_group_account` — the registry group structure (konsernstruktur) names a foreign top parent (UTLA or
  a foreign legal form), the site is not on `.no`, and the handle has no Norwegian marker.
* `account_localised_abroad_on_group_site` — a Norwegian AS on a non-`.no` site links the profile in another
  country's locale (`nl.linkedin.com`) with no Norwegian marker.
* CamelCase handles ending in a legal form are split into words, so the existing "another entity's legal name" rule sees
  them.

**Legitimate profiles kept.** In all seven earlier labelled audits (379 profiles labelled correct), `owner_check`
withholds **none**; it withholds 6 of the 40 labelled incorrect that it can see from the URL alone (the rest were already
withheld by V3.1). Positive controls replayed and live: Logscom (held, as in V3.1), ASAK, Ashtead, Tyin, Bartec (held),
Bergknapp, BK Bygg, BioMar Norge, Grønsand, Eleda Rail Norge, Three60 Energy Norway's own Instagram — unchanged.

## 4. News and job changes

**News — announcement tier** (`attribution/news.py` `announcement_decision`, default; `SIGNALPOST_NEWS_PUBLICATION=anchored`
reproduces V3.1). Every V3.1 rule runs first (individual article URL, date stated on the page, structural/CMS/listing
rejections, subject and entity rules, content policy). Then an item is published only when
* its headline announces an event in the organisation's life — acquisition or merger, appointment, agreement or
  partnership, opening or move, award, anniversary, launch, certification, annual meeting or report, new name, grant;
* the headline is not a question; and
* the item names the organisation (title or its own text).

Group and parent news:
* operator `group_or_brand` (only items stating the full legal name or organisation number are attributed) when the
  site does not state the company's organisation number and either the registry names a foreign parent and the site is
  not on `.no`, or the company is a national unit on an international site whose domain lacks the marker;
* a national unit's bare group brand ("Teqt", "Eleda") does not name the unit (`group_brand_item_not_national_unit`);
* a Norwegian AS on a non-`.no` brand site that never writes its legal name: only items naming it.

Dates: the known `Søknadsfrist` defect (V3.1 report §10.6) is fixed — a deadline, "updated" or closing label in a
separate element before the date is now read. Feed `<updated>`/`lastBuildDate` are never publication dates (already the
case; now tested). Event dates in running text are not stamps (tested).

**Why so strict.** On the consumed, labelled sets V3.1's news precision was 46–80% and no deterministic content rule
separated correct from incorrect items (V3.2 research). The announcement headline plus naming was the one subset that
did. The rule was written while reading those sets, so its precision there is **diagnostic, not independent**:

| Diagnostic (tuned) | Published | Correct |
|---|---|---|
| evalh400, V3.1 | 178 | 86 (48.3%) |
| evalh400, V3.1.1 (approx., on V3.1's items) | 18 | 18 |
| evalg250, V3.1 | 143 | 66 (46.2%) |
| evalg250, V3.1.1 (approx.) | 9 | 9 |

Retention of V3.1's correct news is about 18%: fewer, genuine announcements, as requested.

**Jobs** (`attribution/jobs.py`, `site_facts.py`, `site_research.py`).
* A title naming another organisation as employer ("Fundraiser, Norges Røde Kors", "Rådgiver hos Bergen kommune") →
  `other_employer`. A trailing place ("Selger – Oslo") is not read as an employer.
* An ad hosted off the company's site (finn.no, an applicant-tracking host) qualifies only with a verified employer:
  named as the company, or the tracking address carries the company's name → else `external_ad_employer_unverified`.
* Several current JobPostings on one page without their own URLs are not individual ads.
* A careers page whose listed positions all name other employers is a job board, not the company's careers page.
* **Discovery:** the crawler now follows up to 3 undated positions on the company's own domain to their advertisement
  pages (same budget, robots and Crawl-delay) and dates them by the labelled deadline or posting date there. Unchanged:
  expired and undated ads are never published; generic recruitment pages are not ads.

### 4.1 Post-audit fixes (found by the eval-r300 audit of the frozen candidate `44d0cd3`)

The eval-r300 audit (§5.2) found five more classes. Each fix is general and has a regression test
(`tests/test_v311_rescore.py::PostAuditFixes` and the updated V3.1 tests):
* **Websites — `related_not_exact`.** A business manager's site (usbl.no, vestbo.no, nbbo.no … for a borettslag or
  sameie), another company's site (Tyin Alpint on tyinfilefjell.no; Logscom AS on the Swedish logscom.com) or a group's
  site (moelven.com for MOELVEN WOOD AS; mde-group.com for MDE TRONDHEIM AS) is no longer published as the entity's
  `official_website`. The claim is `ambiguous` with `relation: related_not_exact`, `related_url` and the reason, as in
  Builderr's own reference sample ("related_not_exact · withheld"); the registry fact stays as
  `registry_listed_website`. A group-named site that states the company's own organisation number (BE KRAFTSALG AS on
  bodoenergi.no) stays its own. Four V3.1 tests that asserted the old behaviour (Tyin, Logscom, the Bori manager case,
  the viewer inspector on Tyin) now assert the new one.
* **Shared group brand.** A handle or domain that is a brand carried by other companies in the registry group
  (`moelven` next to Moelven Industrier ASA and Moelven Bioenergi AS) is the group's.
* **Supplier launches.** A launch headline ("DPA lanserer …") must name the company: a distributor reposts its
  suppliers' launches.
* **Individual article URL.** A card on a listing, the homepage or a bare news-section root (`melbye.no/nyheter`) is not
  an article.
* **Own employer in an ad's title** ("Båtmekaniker og tekniker ved Havforskningsinstituttet" on Jobbnorge) verifies an
  off-site advertisement.

Two further careers refinements came from the live reproductions of the final code (`38ff24c`): a careers page is a
job board for other employers when at least two positions, and at least half, name another employer and none is
verified as the company's own (FUNDRAISING NORGE: 12 of 14); and an international brand site that never writes the
Norwegian company's legal name (INLUMI AS on inlumi.com) gives it neither a careers page nor unnamed-employer ads.
Replays of the eval-r200c and eval-r300 captures are unchanged by these two refinements.

## 5. Measurements

All labels are by the assistant that wrote the rules (not owner-verified), made on a version-blind sheet with the
captured text and URLs visible. They are not Builderr scores. Files: `measurements/v311-rescore-2026-11-14/`.

### 5.1 Samples

| Sample | Drawn | Role |
|---|---|---|
| eval-r300 | 300 organisations with a registered website, seed 20261114, disjoint from every organisation number on every branch; committed (`097049f`) before any run | Post-freeze audit of the frozen candidate `44d0cd3`; then **diagnostic** (it revealed the §4.1 classes) |
| eval-r200c | 200 more, seed 20261115, disjoint from all of the above and from eval-r300; committed (`fef9be4`) before the final code ran on it | **Independent** check of the final code `7a88046` |

### 5.2 eval-r300 — `ff3b515` (live), V3.1 and the frozen V3.1.1 candidate (replays of the same capture)

Every published external claim (website, social, careers page, job ad) of each arm was labelled; news was labelled in
full for V3.1.1 and estimated from a random sample of 40 for the other two (`score_audit.py`).

| Family | `ff3b515` | V3.1 `334a085` | V3.1.1 frozen `44d0cd3` |
|---|---|---|---|
| Websites | 97/110 (88.2%); 13 wrong or related company | 97/110 | 97/110 |
| Social profiles | 70/77 (90.9%); 7 wrong company | 67/70 (95.7%) | 67/70 (95.7%) |
| News | 446 published, ~46% correct (sample 18/40) | 200, ~44% (sample 16/40) | 20 published, 15 correct (75%) |
| Careers pages | 9/18 (50%) | 11/11 | 11/11 |
| Job ads | 2/6 | 2/2 | 0 published |

`ff3b515`'s wrong-company classes here: business-manager websites published as the entity's own (11), group websites
(2), group social accounts (MDE Group, Melbye Group, Moelven: 7), plus not-news and non-careers pages. This is the
closest we can come to the evaluator's 11 without their sample: the same classes, on a new sample.

**After the §4.1 fixes (diagnostic, the fixes were made on this sample):** websites 97/97 published decided (11 manager
sites and 2 group sites held as related), social 67/67 (Moelven held), news 13/13, careers 11/11, job ads 1/1. Only
one labelled-correct claim was lost (Fritt Ord's "Lansering: …", whose headline does not name the foundation).

### 5.3 eval-r200c — independent check of the final code `7a88046`

| Family | Published | Correct | Incorrect | Unsure |
|---|---|---|---|---|
| Websites | 63 | 60 | 0 | 3 |
| Social profiles | 63 | 60 | 2 (WANG chain accounts on a WANG school's site) | 1 |
| News | 7 | 6 | 1 (an extraordinary general meeting of another entity, Oslo Klatresenter) | 0 |
| Careers pages | 10 | 8 | 1 (an article) | 1 |
| Job ads | 0 | — | — | — |
| **All** | **143** | **134** | **4** | **5** |

* **Precision of decided claims: 134/138 = 97.1% (Wilson 95% CI 92.8–98.9%).** Counting every unsure claim as wrong:
  134/143 = 93.7% (88.5–96.7%).
* **Wrong-company claims: 3/138 = 2.2% (0.7–6.2%).**
* 8 business-manager websites were held as related, not published.
* The sample is small (200 companies, 143 claims); the interval includes values below 95%. **We do not claim the
  official 95% threshold is met**; only Builderr's audit can establish that.

### 5.4 Legitimate coverage

* Non-news families on eval-r300: `ff3b515` 178 correct claims, V3.1.1 (after fixes) 176 — 98.9% of `ff3b515`'s correct
  website, social, careers and job claims are retained, while its 20 wrong ones are not.
* News is deliberately sparse: on eval-r300, 13 announcements against ~207 correct items among `ff3b515`'s 446 (~240
  of which were not company news). On the consumed sets the announcement tier keeps about 18% of V3.1's correct items.
* Social retention on the seven earlier labelled audits: 379/379 labelled-correct profiles pass the new owner checks.

## 6. Release validation (final code `7a88046`)

All runs from clean worktrees (`git status` empty), through the outbound-host audit hook. Files:
`measurements/v311-rescore-2026-11-14/runs-final-38ff24c/`, `runs-eval-r200c-7a88046/`, `runs/` (earlier candidates),
`cleanroom/`.

| Check | Result |
|---|---|
| Full test suite (working tree) | **570 passed, 193 subtests passed**, 0 failed. 34 V3.1 news-tier tests run under `SIGNALPOST_NEWS_PUBLICATION=anchored` (V3.1 behaviour, unchanged); on the default tier exactly those 34 change (`suite-default-tier.txt`) |
| Clean room `38ff24c` | Fresh clone, empty uv cache: `uv sync --locked` exit 0; 570 passed, 193 subtests; documented command exit 0 |
| New regression tests | `tests/test_v311_rescore.py`: 37 tests with subtests (LØWEHJERTE fixture replay; platform/admin URLs; sameAs cannot override; national-unit, foreign-parent, localised and shared-brand group accounts; legitimate controls; announcement tier; product/advice/promotion rejected; parent and group news; Søknadsfrist, updated and event dates; plain-slug WordPress; current, expired, generic, other-employer and third-party job ads; job boards; detail-page crawl) |
| 100-company smoke (`38ff24c`, live 2026-11-14) | 100/100 completed in input order; report validation passed; **0 contract findings; 3,968 evidence hashes re-verified, 0 mismatches** (4 website-module evidence entries for 2 companies have no stored snapshot, as before); 197 hosts, **no social-platform host**; **$0**; no LLM; 0 unsupported summary statements; viewer written; 89 s. Published: 16 websites, 11 social, 2 news, 4 careers pages |
| Refresh (`38ff24c`) | Baseline = published envelopes for 100/100; **1 `unavailable` event** (AUTO24 AS: registry e-mail domain unreachable; website retained), no removal or false change |
| Reproductions (`38ff24c`, live, 21 companies) | LØWEHJERTE: no profile published; Tyin, Bartec, Logscom, Valmet, Moelven websites held as related; Valmet, Inlumi, TEQT, BD UK, Moelven group accounts and Birkeland's sister handle held; FUNDRAISING NORGE's job board held; BE Kraftsalg's own-number site kept. Positive controls unchanged: Bergknapp (3 profiles), BK Bygg (2), BioMar Norge (3), Grønsand (2), Eleda Rail Norge (2), Three60 Energy Norway (1), Birkeland (2), Fundraising Norge (2). ASAK, Ashtead, Tyin, Bartec, Logscom, BE Kraftsalg still withhold the profiles V3.1 withheld. 0 contract findings; no platform host |
| eval-r200c (`7a88046`, live) | 200/200 completed; 0 contract findings; 5,734 hashes, 0 mismatches; no platform host; $0. Replays show `38ff24c` publishes the same claims on this capture |
| Desktop and phone viewer (smoke output) | No page errors, no horizontal overflow, search works (Playwright Chromium, 1366×900 and iPhone 13) |
| Evidence/contract | `contract.validate_envelope` on every envelope of every run: 0 findings |

Note on INLUMI AS: on the 2026-11-14 capture its contact page states "inlumi AS, Vollsveien 19, 1366 Lysaker", so the site
names the Norwegian company and its careers page is published; the international-brand-site rule applies only when the
site never writes the company's legal name.

## 7. Known limitations and remaining errors

* **News coverage is low by design.** Only headline announcements naming the organisation are published. Correct
  items without an announcement headline (club reports, newsletters, research news) are withheld.
* **Remaining wrong-company classes seen on eval-r200c:** a chain's accounts on one chain member's site when the chain
  is not a registry group (WANG), and an item about a closely related entity that shares the name (Oslo Klatresenter
  for Oslo Klatreklubb).
* **Unsure websites** (3 of 63 on eval-r200c): a national marketplace site for a local entity, a chain site, and a site
  with no captured text.
* **Job ads remain rare.** No ad was published on eval-r200c; most careers pages list positions without a date on the
  card or on a detail page the crawler reads within its budget, and undated ads are never published.
* **Parish and church sites shared by several sokn** were labelled correct (as the parish's official site); a stricter
  reader could call them related.
* **Labels** are the rule author's, not owner-verified; eval-r300 is now diagnostic; eval-r200c is small.
* **The evaluator's other 9 claims** are unknown; their classes are inferred, not confirmed.
* The V3.1 news rules remain available unchanged (`SIGNALPOST_NEWS_PUBLICATION=anchored`); 34 V3.1 tests pin that tier
  and run under it (`measurements/v311-rescore-2026-11-14/suite-default-tier.txt` lists them on the default tier).

## 8. Submission information (for the owner; nothing has been pushed or submitted)

| | |
|---|---|
| Repository | https://github.com/Sahvendra7/signalpost-agent |
| Branch | `revision/v3.1.1-builderr-rescore` (to be pushed only after the owner's approval) |
| Release commit | The documentation commit that adds this section; its full SHA is given in the handoff message (a commit cannot contain its own SHA). Code-identical to `38ff24c48e989a987529f4f7d6ca3fa107bce75d`. |
| Command | `uv sync --locked` then `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>` |
| Models / LLM | None. The LLM layer is not imported; no Gemini code in this branch |
| External APIs | Brønnøysund registry (Enhetsregisteret, Regnskapsregisteret, konsernstruktur, roller, underenheter; NLOD 2.0) and the companies' own websites (robots.txt honoured). No social platform is fetched; no Brave, no NAV, no paid API |
| Dependencies and licences | Unchanged from V3.1 (`pyproject.toml`, `uv.lock`, `docs/dependencies.md`) |
| Operating cost | $0 third-party cost; about 0.9 s per company on the 100-company smoke (89 s) |
