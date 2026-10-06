# Revision 1, final candidate: results and submission check

**Revision 1 has not been submitted and has not been scored.** Every number here is a local engineering
measurement. The official C12 score of 57.87/100 (reported elsewhere as 57.93) belongs to **V1** (`104c3c4`,
tag `submission-candidate-1`). It is not a Revision 1 score, and no Revision 1 score is claimed or estimated.

| | Commit |
| --- | --- |
| V1 (officially evaluated) | `104c3c45d9aef303d3112749a44de5aaf38bca8e` |
| **Revision 1 code under test** | **`a5e06ce5e989ffeafa1c50937a10fa4bc4a1fbb4`** |
| Revision 1 candidate | The head of `claude/awesome-sagan-m2lppu` that adds this document; code-identical to `a5e06ce` (`git diff a5e06ce HEAD -- src tests scripts pyproject.toml uv.lock` is empty) |

This supersedes `docs/revision-1-results.md` (measured on `58fee4e`). Two things changed since then. The
business-manager rule was narrowed, and the manual audit of three new rounds of same-day runs found and fixed
eight defect classes in the core extraction, one of them a wrong-company publication.

## 1. What Revision 1 changes (core)

Builderr's V1 feedback: social profile 0%, dated news 0% and hiring 0%. The named misses were MTM SKOGSERVICE
811730912 (Facebook/Instagram), 813396092 (bori.no/aktuelt) and GRANNE 838797172 (granne.no/ledige-stillinger).

| Change | Effect |
| --- | --- |
| Exact social URLs | The value is the URL exactly as the verified site links it. V1 published a rewritten form absent from the cited page for 124 of 136 social claims (1,200) and 37 of 39 (400). Revision 1: 0. |
| `public_activity.social_profile` | Typed claim with `platform`, `source_page`, `evidence_span`. V1 used an object under `websites.social_profile`. |
| Dated first-party activity | `public_activity.news_item` from JSON-LD, meta, `<time>`, feeds and listing date stamps. A dateless listing is followed to at most 3 article pages on the same site. |
| Job postings | schema.org JobPosting, and positions linked from the site's careers page. A careers page with no position yields none. |
| Evidence containment | Every title, URL and stated date is checked against the captured bytes it cites; failures are counted, never repaired. |
| Deterministic claim typing | No LLM. |
| Strict identity inheritance | Every fact inherits the identity of the already verified website and never establishes identity itself. The identity gate is unchanged. |
| No platform requests | No LinkedIn, Facebook, Instagram, YouTube, X or TikTok host is contacted (host audit of every run). |

## 2. The business-manager rule (decision)

Commit `83321ea` added `MANAGER_DESIGNATED`. The rule accepts the website of a registered forretningsfører when
the entity's own Brreg record names the site, Brreg lists the manager, the manager's organisation number is
printed on the site, a control signal ties the entity's contact to the site, and the identity gate found nothing
contrary. It then published the manager site's 5 most recent news items as the managed entity's news.

**Decision: keep the website association, and stop attributing the manager's content** (`0f24dc3`, `a459120`).
These are two separate facts:

- **A. Website association: kept.** The registry itself names the site and the manager relationship. The claim
  is `official_website` with `operated_by` (name, organisation number, `registry_role: forretningsfører`) and
  confidence 0.9.
- **B. The manager's own content: not attributed.** Its social profiles, vacancies and careers page are never
  the entity's. A news item is published only when **the item itself** explicitly names the managed entity:
  - its organisation number; or
  - its full legal name as a phrase, in the item's title or summary, or in its own cited article page.

  A listing page's text never counts, and neither do distinctive words alone. A legal name extended by a number,
  a roman numeral or a legal-form or "drift" word names another entity: "SAMEIET X II", "SAMEIET X DRIFT" and
  "X BORETTSLAG" are not "SAMEIET X". The basis is stored as `subject_basis`. Held items are counted as
  `activity:manager_news_not_about_entity`, and the claim states `not_applicable` with that count. Stored records
  without `subject_basis` publish no manager news, so a refresh cannot republish the old attributions.

**Regression case 813396092** (SAMEIE JESSHEIM PARK DRIFT, forretningsfører BORI BBL): the website association
is published. bori.no/aktuelt is BORI BBL's own news ("Bli BORI-medlem…", "Din første bolig…"). Checked live on
2026-10-05, no item names the sameie, so no news is attributed. A news claim for bori.no/aktuelt is therefore
**not supported** under this rule, even though Builderr listed it as a miss.

**Live effect:** across 13 manager-designated companies (8 on 1,200, 5 on 400), 199 dated manager-site items
were held. One was published: "Forvaltningsavtale med Workinntoppen C1 Boligsameie" on agioforvaltning.no for
921990820 WORKINNTOPPEN C1 BOLIGSAMEIE, whose legal name is in the title. That is exactly the case the rule
allows.

## 3. The three C12 cases (live, final code, 2026-10-06)

| Case | Published | Not published, and why |
| --- | --- | --- |
| 811730912 MTM SKOGSERVICE | `public_activity.social_profile` https://www.facebook.com/MtmSkogservice and https://www.instagram.com/mtmskogservice/, both contained in the cited page | — |
| 813396092 SAMEIE JESSHEIM PARK DRIFT | `official_website` https://www.bori.no/, operated by BORI BBL 989987011 | News, social and vacancies are `not_applicable`: they are BORI BBL's, and no item names the sameie |
| 838797172 GRANNE | `careers_page` https://www.granne.no/ledige-stillinger; Facebook and LinkedIn profiles | `job_posting` is `not_available`: the page says "Her oppdaterer vi så snart det kommer ledige stillinger" (no open position, re-checked live). No job is invented from a careers page. |

The C12 replay tests (`tests/test_revision1.py`) pin all three on the exact captured bytes.

## 4. Precision audit

### Method

Every company whose site-derived claims differ between V1 and Revision 1 was inspected by hand against its
snapshot. Representation-only differences (a rewritten URL becoming the exact one, `site_activity` becoming
`news_item`) were folded away by `audit_diff.py`. This was done in three rounds of four back-to-back live runs.

| Round | Revision 1 code | Companies inspected (400 + 1,200) | Defects found |
| --- | --- | --- | --- |
| 1 | `a459120` | 15 + 40 | 1 wrong company; wrong dates on 4 sites; duplicate articles; author/category archives as items on 2 sites; unsupported jobs on 1 site |
| 2 | `051f2d3` | 14 + 40 | Item URL taken from a related or breadcrumb link on 2 sites |
| 3 | **`a5e06ce`** | 14 + 42 | **None** |

The defects found and fixed. Each has a regression test, confirmed to fail on the code before its fix:

| Case | Defect | Fix (commit) |
| --- | --- | --- |
| 930870781 Læringsverkstedet Tveit | **Wrong company.** Its verified site is a section of the chain's domain; the chain's blog post became its news. | A section site fetches only feeds, news, careers and articles inside its section; items outside it are rejected (`051f2d3`) |
| 998243432 Orkla Regnskap, 926642510 Aksjefabrikken, 920186114 Devold Møllers stiftelse, 883759702 FDVhuset | Wrong date: "Fra 1. januar 2026 fjernes…", "Gjeldende fra 1. august 2026", "ble opprettet 31. januar 2018", a seminar date in a subtitle | A listing date counts only as a stamp (alone, or with a publication cue, weekday, byline or label), never inside running text (`051f2d3`) |
| Same | One article published twice with contradictory dates | One article URL is one claim; structured > feed > listing text (`051f2d3`) |
| 917939527 Ålhytta, 923143785 Arkitekt Sandmark | Author names (`?author=`) and category archives (`/category/…`) as news items | Author and taxonomy archive links are never an item (`051f2d3`) |
| 980429849 Edge Branding | Two old ads from a news-category archive (`/aktuelt/tema/ledig-stilling`) became job postings, while the careers page lists no position | A news page is not a careers page (`051f2d3`) |
| 925503215 Vasser, 931624032 All Gravy | An article page's own title and date published under a related-article or breadcrumb URL | On an article page, the item headed by its `<h1>` is the page (`a5e06ce`) |
| BORI and 12 other manager-designated companies | The manager's news attributed to the managed entity | §2 (`0f24dc3`, `a459120`) |

**V1 wrong-company claims that Revision 1 removes** (seen as "losses" in the comparison):

- 917755256 Nemus Medical Skøyen (a branch section of nemus.no): the chain's news, such as "Nemus Bislett søker
  kiropraktor", and the chain's careers page.
- 930870781 Læringsverkstedet Tveit: the chain's Facebook, Instagram, LinkedIn and YouTube, and its careers page.
- 916974051 Outdoor Norway: personal profiles of third parties (diaryofsid, francomarcio).

**Coverage by the adversarial categories:**

| Category | Automated tests | Live evidence (final runs) |
| --- | --- | --- |
| Fan sites | `test_fan_site_rejected_then_next_candidate_tried` | Gate unchanged |
| Parent / subsidiary | `test_parent_site_with_parent_org_number_is_not_the_subsidiary`, `test_subsidiary_named_on_parent_contact_page_only_is_not_exact` | Nemus, Læringsverkstedet: chain content no longer attributed |
| Same-name entities | `test_similar_name_namesake_is_not_exact`, `test_historical_name_on_stale_site_abstains`, manager name-extension test | — |
| Shared domains | `test_section_of_a_shared_domain_does_not_inherit_the_owner_profiles`, `…_owner_news` | 2 section sites confined |
| Directories | `test_order_dedup_free_mail_and_directories`, `test_no_control_signal_or_contrary_identity_rejects` | — |
| Manager-operated sites | `ManagerDesignatedTests` (6 tests) | 13 sites, 199 items held, 1 attributed by legal name |
| Cross-linked organisations | `test_club_cross_links_keep_only_exact_legal_name_handles` | — |
| Another organisation's social profile | `test_partner_and_platform_default_links_are_not_the_company`, `test_name_match_alone_on_an_unrelated_page_is_not_enough`, `test_domain_name_must_begin_or_end_the_handle`, `test_social_links_of_ambiguous_site_are_quarantined` | 67 profiles held as not corroborated (1,200) |

**Result: 0 wrong-company publications found** among the Revision 1 changes in the final runs. This is our audit,
not Builderr's.

## 5. Same-day comparison (round 3, final code)

All four runs ran live and back to back on 2026-10-05/06, on one machine, with the same command: 8 workers, no
`--bulk`, snapshots on, host audit. Raw reports are in `measurements/revision-1-final-2026-10-06/`.

**Inputs:**

- **400:** the V2 benchmark, SHA-256 `532c54a0…`, rebuilt from the public universe.
- **1,200:** the unseen audit set, SHA-256 `765647df…`.

A company is covered in a family when it has at least one available claim of that family. Social is V1
`websites.social_profile` or Revision 1 `public_activity.social_profile`. Dated news is V1 `site_activity` or
Revision 1 `news_item`. The fifth area is any of social, dated news or hiring.

### 1,200 unseen companies

| Metric | V1 `104c3c4` | R1 `a5e06ce` | Delta |
| --- | --- | --- | --- |
| Website companies | 122 | 132 | +10 (8 manager-designated associations, 2 live drift) |
| Social companies | 66 | 68 | +2 (3 gained, 1 lost) |
| Dated-news companies | 25 | 36 | +11 (13 gained, 2 lost) |
| Hiring companies | 1 | 1 | 0 |
| **Fifth-area companies** | **78** | **85** | **+7 (9 gained, 2 lost)** |
| Social claims | 136 | 126 | −10 |
| Dated-news claims | 162 | 218 | +56 |
| Job claims | 1 | 1 | 0 |
| Total available claims | 47,952 | 48,006 | +54 |
| Social/news/job values not contained in the cited page | 124 social + 21 news (+141 news with no date text) | **0** | |
| Requests | 8,364 | 8,400 | +36 (+0.43%) |
| Runtime | 1,224.5 s | 1,223.1 s | −0.1% |
| Article pages followed from dateless listings | 0 | 25 | |
| Evidence rejections (counted, not published) | not recorded | 239 | |
| Validation | passed, 1,200 completed | passed, 1,200 completed | |
| Platform hosts contacted | none | none | |

**Fifth-area gains.** 7 come from the core change:

- dated news: Wican IT, Altinget, Nordic Boats, Sombra Film, Skan-Kontroll;
- exact social profiles: Byggmester Dversnes, Kynna Bruk.

1 comes from the manager rule: Workinntoppen C1, with an item that names it. 1 is live drift: Glanz's robots.txt
was unreachable in V1's run.

**Fifth-area losses** are both V1 wrong-company claims (Nemus Skøyen, Læringsverkstedet Tveit).

**Evidence rejections, 1,200:**

| Reason | Count |
| --- | --- |
| Manager news not about the entity | 109 |
| Social handle not corroborated | 67 |
| Manager-site profile | 21 |
| Item without a title | 21 |
| CMS page date on a non-news page | 20 |
| Generic title | 1 |

Listing dates inside running text are skipped before validation and not counted.

### 400-company V2 benchmark

| Metric | V1 `104c3c4` | R1 `a5e06ce` | Delta |
| --- | --- | --- | --- |
| Website companies | 46 | 51 | +5 (manager-designated associations) |
| Social companies | 25 | 26 | +1 |
| Dated-news companies | 17 | 17 | 0 (2 gained, 2 lost: both V1 junk, CMS-dated homepage/privacy/portfolio pages) |
| Hiring companies | 0 | 0 | 0 |
| **Fifth-area companies** | **30** | **30** | **0** |
| Social claims | 39 | 39 | 0 |
| Dated-news claims | 85 | 88 | +3 |
| Total available claims | 15,809 | 15,818 | +9 |
| Values not contained in the cited page | 37 of 39 social | **0** | |
| Requests | 2,844 | 2,854 | +10 (+0.35%) |
| Runtime | 417.7 s | 448.3 s | +7.3% |
| Evidence rejections | not recorded | 136 (90 manager news held) | |

### Against the earlier local Revision 1 numbers (`45c41ee` docs, code `58fee4e`)

The earlier figures were 91 fifth-area, 43 dated-activity and 2 hiring companies on 1,200. These are lower now
for three reasons:

- the manager rule no longer attributes manager news, which accounted for 7 of those companies;
- the Edge Branding "jobs" were archived ads;
- dates taken from running text and archive links are no longer items.

**The removed coverage was not supported by the evidence.**

### Runtime and run-to-run variation

Runtime differences are within live run-to-run variation:

| Set | V1, rounds 1/2/3 | R1, rounds 1/2/3 |
| --- | --- | --- |
| 1,200 | 1,210.5 / 1,222.0 / 1,224.5 s | 1,252.5 / 1,228.2 / 1,223.1 s |
| 400 | 430.2 / 420.0 / 417.7 s | 433.3 / 432.5 / 448.3 s |

## 6. Submission check (`a5e06ce`)

| Check | Result |
| --- | --- |
| Clean tree | Yes; every commit is pushed to `claude/awesome-sagan-m2lppu` |
| Reproducible install | Fresh `git clone` of the branch, empty `UV_CACHE_DIR`, `uv sync --locked`: OK. Tests: **339 passed, 83 subtests passed** |
| One command | `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output … --profiles-output … --report … --snapshot-dir … --run-id …`; clean-room run on the 3 C12 companies: valid, exit 0 |
| Paid APIs | None; no key is read by the run path |
| Brave | Not imported by the run path; no Brave host in any host audit |
| NAV | Not in `DEFAULT_MODULES`; no NAV host in any host audit |
| LLM | Off by default; the CLI never builds an LLM layer |
| 1,200-company run | 1,200/1,200 `completed`, validation passed, 1,223.1 s |
| Platform hosts | None contacted in any run |

## 7. Recommendation

`a5e06ce` (or the documentation commit on top of it) is a sound candidate for the next official revision:

- it addresses the representation behind "social 0%" (exact, contained URLs as typed claims);
- it publishes dated first-party news that V1 did not;
- it removes V1 wrong-company claims;
- it costs under 0.5% more requests;
- its final audit found no wrong-company claim.

The local recall gain is modest: +7 fifth-area companies on 1,200 and none on 400. Hiring does not move,
because the named Granne page has no open position. The BORI news miss stays unfilled by design. Any official
effect depends on how Builderr matches social URLs and dated items. **Whether and when to submit is the
owner's decision. Nothing has been submitted.**
