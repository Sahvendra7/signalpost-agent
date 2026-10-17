# Revision 1 results: existing website evidence as material claims

> **Superseded by `docs/revision-1-final.md`** (final candidate code `a5e06ce`). The business-manager rule described
> below was narrowed: the website association is kept, but the manager's news is attributed only when an item names
> the managed entity. Three further audit rounds fixed eight defect classes in the core extraction. The figures below
> (code `58fee4e`) are historical.

**Revision 1 has not been submitted, and no score is claimed.** These are local engineering measurements.
They show what the code now publishes. They do not show how Builderr will score it: its pool, its matching
rules and its family definitions are not published (`docs/official-scoring-model.md`).

**What was compared:**

| Version | Commit | Runs |
| --- | --- | --- |
| V1 | `104c3c4`, the code Builderr evaluated (C12: 57.87/100) | `v1b-400`, `v1b-1200` |
| Revision 1 | `58fee4e` | `r1g-400`, `r1g-1200` |

All four runs ran live, back to back on 2026-10-05, on the same machine, with the same command and settings:

- 8 workers;
- no `--bulk`;
- snapshots on;
- the host audit from `measurements/final-validation-2026-10-03/host_audit.py`.

**Inputs:**

- **400:** the V2 benchmark (`out/r1/bench400.jsonl`, SHA-256 `532c54a0…`). It is the fixed 100-company
  sample plus seeds 20261101, 20261102 and 20261103.
- **1,200:** the unseen audit set (`measurements/official-audit-2026-10-03/unseen-1200/input-companies.jsonl`).

**Raw results:** `measurements/revision-1-2026-10-04/`, analysed with `compare_runs.py`.

**Coverage definitions.** A company is covered in a family when it has at least one available claim of that
family:

| Family | V1 claims | Revision 1 claims |
| --- | --- | --- |
| Social | `websites.social_profile` | `public_activity.social_profile` |
| Dated activity | `public_activity.site_activity` | `public_activity.news_item` |
| Hiring | `hiring.job_posting` | `hiring.job_posting` |

"Fifth area" means any of the three.

## 1,200 unseen companies

| Metric | Current V1 | Revision 1 | Delta |
| --- | --- | --- | --- |
| Website companies | 123 | 129 | +6 (7 gained, 1 lost) |
| Social companies | 67 | 67 | 0 (1 gained, 1 lost) |
| Dated-activity companies | 25 | 43 | **+18** (19 gained, 1 lost) |
| Hiring companies | 1 | 2 | +1 |
| **Fifth-area companies** | **79** | **91** | **+12 (12 gained, 0 lost)** |
| Social claims | 138 | 125 | −13 |
| Dated-activity claims | 162 | 283 | +121 |
| Job claims | 1 | 3 | +2 |
| Total available claims, all families | 47,957 | 48,071 | +114 |
| Claims whose value is not in the cited captured page | 126 social (91%) | **0** | |
| Requests | 8,306 | 8,326 | +20 (+0.24%) |
| Runtime | 1,152.9 s | 1,179.7 s | +26.8 s (+2.3%) |
| Article pages followed from dateless listings | 0 | 25 | |
| Evidence rejections (counted, not published) | not recorded | 127 | |
| Wrong-company matches in the manual audit | — | **0 remaining** (5 defects found and fixed, see below) | |
| Platform hosts contacted (LinkedIn, Meta, YouTube, X, TikTok) | none | none | |
| Validation, envelopes | passed, 1,200/1,200 | passed, 1,200/1,200 | |

The 127 evidence rejections break down as:

| Reason | Count |
| --- | --- |
| Social handle not corroborated | 64 |
| Profile on a business manager's site | 21 |
| Item without a title | 21 |
| CMS page date on a non-news page | 20 |
| Generic title | 1 |

What the 1-company losses are:

- **Website 979378726 (Kragerø Stenindustri):** its robots.txt was unreachable during this run. That is live
  drift; the robots policy is the same in both versions.
- **Social 930870781:** Læringsverkstedet Tveit's verified site is a subpage of the chain's site, and the
  chain's own Facebook page is no longer attributed to the kindergarten. This is intended.
- **Activity 920929257:** "Om Tony Trefelling" and "Kontakt oss" were CMS-dated pages, not news. This is
  intended.

## 400-company V2 benchmark

| Metric | Current V1 | Revision 1 | Delta |
| --- | --- | --- | --- |
| Website companies | 46 | 51 | +5 |
| Social companies | 26 | 27 | +1 |
| Dated-activity companies | 17 | 22 | +5 (7 gained, 2 lost) |
| Hiring companies | 0 | 0 | 0 |
| **Fifth-area companies** | **31** | **36** | **+5 (5 gained, 0 lost)** |
| Social claims | 40 | 40 | 0 |
| Dated-activity claims | 85 | 118 | +33 |
| Total available claims | 15,813 | 15,851 | +38 |
| Claims whose value is not in the cited captured page | 38 of 40 social | 0 | |
| Requests | 2,829 | 2,853 | +24 (+0.8%) |
| Runtime | 395.8 s | 419.2 s | +5.9% |
| Wrong-company matches in the manual audit | — | 0 | |

The two activity losses on the 400 benchmark were V1 junk:

- CS Netthandel: a homepage and a privacy page dated by JSON-LD.
- Ralston Bau: a portfolio case page dated by `article:published_time`.

## Where the gain comes from

**Incremental verified company coverage (the main metric).** The fifth area gains +12 companies on 1,200
(79 → 91, +15%) and +5 on 400 (31 → 36, +16%), with no company lost on either set. Most of it comes from the
separable business-manager rule:

| Part of Revision 1 | Fifth-area companies gained on 1,200 | On 400 |
| --- | --- | --- |
| `MANAGER_DESIGNATED` (commit `83321ea`): registry-designated site of a registered business manager, dated news only | **7** | **5** |
| Core: dated news on own sites, now read from listings that state dates next to titles | 4 (Wican IT, Altinget, Nordic Boats, Skan-Kontroll) | 0 |
| Core: social profile with the exact linked URL | 1 (Byggmester Dversnes) | 0 |
| **Total** | **12** | **5** |

Without `83321ea`, the fifth area would be 79 → 84 (+5) on 1,200 and unchanged on 400.

Within companies already covered, the core change adds:

- **Dated news:** activity companies 25 → 43 on 1,200 and 17 → 22 on 400, counting the manager sites.
- **Jobs:** 1 → 2 companies on 1,200.

**Incremental verified material claims (secondary).** There are +121 dated-activity claims and +2 job claims.
There are 13 fewer social claims, from stricter de-duplication (case-insensitive handles, one claim per
profile) and from parent and chain profiles that are no longer attributed.

**Representation.** This is the core change's main effect, and it cannot be measured locally:

- **V1:** 91% of published social URLs did not occur in the page they cite (126 of 138 on 1,200; 38 of 40 on
  400), and the value was an object under `websites`.
- **Revision 1:** every social claim is `public_activity.social_profile` with the exact linked URL. Every news
  and job claim's title, and every stated date, occurs in its cited snapshot. This was re-checked independently
  on the snapshot bytes by `compare_runs.py`.

If Builderr's "no scored social claims" came from URL matching or from evidence containment, this is what
turns the 67 companies' existing social claims into matchable ones. That would be a recall gain on
already-discovered profiles, not on new companies. Whether it does so can only be known from Builderr's
scoring.

## Precision safety

- **Automated:**
  - all 330 tests pass, including the existing identity-adversarial tests (`tests/test_identity_adversarial.py`, `tests/test_site_research.py` and `tests/test_crawl_safety.py`: fan sites, directories, parent and subsidiary sites, namesakes, brand names, parked domains, quarantined social links of ambiguous sites, platform hosts; 41 tests, all passing);
  - 27 Revision 1 tests, including the C12 regression replays and one test for each audit defect.
- **Manual audit:** every company that gained a family was inspected by hand, in three rounds:
  - 23 companies on the first 1,200 run;
  - 19 on the second;
  - all 19 on the final run;
  - 8 on the 400 benchmark.

  The audit found five defects in the new extraction, all fixed before the final runs (commits `3c946d9` and
  `58fee4e`):

  | Case | Defect | Fix |
  | --- | --- | --- |
  | 971531983 NHF Region Innlandet | Its verified site is a section of handball.no, and the federation's own profiles were accepted, because "handball" occurs in "norgeshandballforbund". This was a **wrong-company publication**, fixed. | On a section of a shared domain, only the legal-name gate may accept a profile. Elsewhere the domain name must begin or end the handle. |
  | 928934977 Altinget | The dated milestones inside one article became separate news items. | Listing extraction is skipped on article pages that carry their own date. |
  | 980429849 Edge Branding, Altinget | Staff and author links (`/ansatte/`, `/person/`) were taken as items. | Such links are never an item's title or URL. |
  | 998549833 Northern Beat, 813302632 Arkwright | "Registrer din søknad" and "Careers in Oslo" were taken as job titles. | Generic application and careers phrases are not job titles. |
  | 816945852 (usbl.no) | Yoast stamps every page as a dated Article, so the news listing was mistaken for an article, while careers, contact and listing pages became "news". | Page-level CMS dates count only on news pages, and listings are told apart from articles by their path. |

  After the fixes, no wrong-company or unsupported claim was found among the gained companies of the final runs.
  This is our audit, not Builderr's.
- **Inheritance of identity:** every new fact inherits the identity of the already verified website. Social
  profiles, news pages and job pages never establish identity themselves.

### The one policy decision: `MANAGER_DESIGNATED` (commit `83321ea`, separable)

The C12 miss 813396092 (BORI) is a sameie whose own Brreg record names `www.bori.no`, the site of its
registered *forretningsfører* BORI BBL. The rule accepts such a site only when every one of these holds:

1. the entity's own registry record names the site;
2. Brreg lists a forretningsfører;
3. the manager's organisation number is printed on the site;
4. a control signal is present: the registry e-mail domain matches the site, or the site has an own-domain
   mailbox;
5. the identity gate found nothing contrary.

When the rule applies, only the official website (labelled `operated_by`, confidence 0.9) and the manager
site's 5 most recent dated news items are published. The manager's social profiles, vacancies and careers page
are never attributed to the managed entity.

| Set | Websites added by this rule | Fifth-area companies from this rule alone |
| --- | --- | --- |
| 1,200 | 7 | 7 |
| 400 | 5 | 5 |

It is plausibly much larger in Builderr's set: 22.8% of universe companies with a registry website share it
with five or more entities, mostly housing cooperatives.

**The risk:** the news items describe the manager ("Usbl etablerer Eida Eiendomsmegling"), and they are
attributed to the borettslag. Builderr's own pool counted the BORI case as a miss, which suggests its verifier
accepts it. A stricter reading of "each fact belongs to the right company" would not. This is the only part of
Revision 1 that moves an identity boundary, and it can be dropped by reverting `83321ea`.

## What Revision 1 does not change

- **Sources:** no new sources, no Brave, no search engine, no NAV, no LLM, and no platform fetches (none in any
  host audit).
- **Website discovery:** unchanged. Most of the gap to Builderr's 37.6% website/profile coverage is companies
  without any discovered website, and this revision does not address that.
- **Synthesis and UX:** not redesigned. Revision 1 makes one wording fix for manager-operated sites and teaches
  the viewer and summary the new value shapes.
- **Jobs:** they remain rare. Of the 20 careers pages on verified sites in the 1,200 set, most link no position;
  Granne's currently says none are open.

## Recommendation for official Revision 1

Submit the core change: commits `a0cb079`, `0093419`, `3c946d9` and `58fee4e`. Its argument:

- It makes the crawler's existing finds typed, evidence-contained claims. The 91% of social URLs that were not
  in their cited page are now exact links.
- It adds dated news and jobs that were found but unpublished.
- It costs under 1% more requests.
- Its audit found no remaining wrong-company claim.

Its new-company effect is small (+5 on 1,200, 0 on 400). Its expected value lies in Builderr being able to
match claims we already had.

Decide separately on `83321ea` (`MANAGER_DESIGNATED`). It provides most of the measured new-company coverage
(+7 on 1,200, +5 on 400) and covers exactly the kind of case Builderr named (BORI), at a precision risk that only
Builderr's verifier can settle. Our recommendation is to include it, because Builderr named the case as a miss.
Keep it as its own commit, so it can be removed in Revision 2 if precision drops.

Do not present any of this as a score improvement until Builderr scores it.
