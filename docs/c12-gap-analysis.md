# C12 gap analysis: discovered but not scored

Builderr's first official result was for commit `104c3c4`, the same code as `4f827ee`:

| Dimension | Score |
| --- | --- |
| Recall | 8.87/50 |
| Precision | 29/30 |
| Synthesis | 12/12 |
| UX | 8/8 |
| **Total** | **57.87** |

The feedback: there were **no scored social, dated-news or job claims**, coverage was **37.6% of
verified website/profile opportunities**, and there were three named misses.

**Method.** We traced the pipeline at `104c3c4`. We ran the evaluated code live on the three named
organisations on 2026-10-04, with snapshots on (`/tmp` run, input below). We also re-read every page that the
1,200-company V1 validation run captured (`out/final-validation/live-1200`, code `4f827ee`, 2026-10-03).

**Limits.** Nothing here is a guess about Builderr's scorer. Where the cause is in our output, the evidence is
shown. Where it depends on how Builderr matches facts (unpublished), we say so.

## Pipeline at `104c3c4`

Each stage, from fetching to output:

1. **Website fetch.** `site_research.research_company_site`: identity pages first, then enrichment (`_enrich`):
   one declared feed, one news page and one careers page.
2. **Extraction**, each producing records on `SiteResult`:
   - `website._social_links` and `structured_social_links` give links, normalised by `normalize_social_url`;
   - `html_items` (JSON-LD, `article:published_time`, `<article><time>`) and `feed_items` give activities;
   - `job_postings` gives jobs, from schema.org `JobPosting` only.
3. **Identity.** Social links go through `identity.assess_social_identity`: a passing link goes to
   `profiles`, the rest to `ambiguous_profiles`.
4. **Claims.** `claims._site_research_claims` (and `_website_claims` for the v1 record) produces three
   claim types:

   | Claim | Value |
   | --- | --- |
   | `websites.social_profile` | `{platform, url}`, where `url` is the **normalised** URL |
   | `public_activity.site_activity` | `{title, url, publication_date, ...}` |
   | `hiring.job_posting` | JobPosting only |

5. **Output.** Claims go into the envelope's `claims`, and evidence goes into `evidence`. The evidence for a
   site fact is the captured page (URL, retrieval time, SHA-256).

## The three named misses, traced on the evaluated code

| Organisation | Discovered | Stored | Normalised | Claim created | Evidence attached | Output | Reason for loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 811730912 MTM SKOGSERVICE AS, www.mtm-skogservice.no | Yes. The page links `https://www.facebook.com/MtmSkogservice` and `https://www.instagram.com/mtmskogservice/` (plus a YouTube channel) | Yes (`site_research.profiles`) | **Rewritten** to `https://facebook.com/MtmSkogservice` and `https://instagram.com/mtmskogservice` | Yes, but as `websites.social_profile` with value `{"platform", "url"}` | Yes (the homepage) | Yes | The published URL **does not occur in the captured page**; the page has the `www.` form, the trailing slash and a different path. The category is `websites`, not a public-activity family, and the value is an object, not the profile URL. A matcher on the linked URL cannot match it, and an evidence check of "value in page" fails. |
| 813396092 SAMEIE JESSHEIM PARK DRIFT, www.bori.no | The registry website bori.no was fetched: homepage, contact page, `/aktuelt/` | No. The identity gate returned `AMBIGUOUS` ("no control signal"), and pages of a rejected site are not kept | — | **No.** `official_website: ambiguous`, and no site facts at all | — | `site_activity: not_available` | **Identity, not extraction.** bori.no is the website of **BORI BBL (989987011)**, the sameie's registered *forretningsfører* and *regnskapsfører* in Brreg. The sameie's own registry record lists `www.bori.no` and `forvaltning@bori.no`. The policy accepts only the entity's own site, so every site fact is dropped. Separately, `/aktuelt/` lists no dates; dates are only on the article pages (JSON-LD `datePublished` and "Publisert 01. okt. 2026"), which are never fetched. |
| 838797172 GRANNE FORSIKRING, www.granne.no | Yes. `/aktuelt` and `/ledige-stillinger` were both fetched, and the site was verified (REGISTRY_LINKED) | Yes (pages and hashes) | — | **Jobs: no.** Only schema.org `JobPosting` is read, and the careers page has none; only a `websites.careers_page` claim was made. **News: no.** The listing states no dates, and article pages are not fetched. | — | `job_posting: not_available`, `site_activity: not_available`, plus `careers_page: available` | **Extraction.** A careers page was found, but the code could not read listed positions. Today (2026-10-04) the page says *"Her oppdaterer vi så snart det kommer ledige stillinger"* (no open position), so **no job claim can be made from today's page**; at C12 time a position may have been listed. The `/aktuelt` titles are undated on the listing page. |

## Family by family, measured on the 1,200-company V1 run (121 verified sites)

### Social profiles: discovered and published, but not in a form that can match

- **Discovered:** 66 companies with at least one site-linked profile.
- **Claim created:** yes, 137 `websites.social_profile` claims.
- **Evidence attached:** yes.
- **Lost because:** **125 of 137 published URLs (91%) do not occur in the captured page.** `normalize_social_url`
  rewrote them (it strips `www.`, trailing slashes and query strings, and lower-cases some paths). The value is an
  object, and the category is `websites`. The v1 website record also published its own rewritten links, from a
  record whose hash covers only the homepage, so some of those links cannot be found in the evidenced bytes at
  all.
- **Gate, deliberately kept:** 59 links on verified sites fail the identity gate. Inspected one by one, these are
  - tattoo artists' personal Instagram accounts;
  - Wix default links;
  - Facebook policy, pixel and ads pages;
  - partners (Uni Micro);
  - apprentice companies' pages (blitomrer.no);
  - Facebook posts and shares;
  - a few probable own profiles under a brand or abbreviation (tombvgs, InnlandetBE, nemus).

  They are not a recall loss we should recover; precision is worth more.

### Dated activity: published from feeds, but probably not in the scored form

- **Published:** 25 companies, 162 `public_activity.site_activity` claims:
  - 122 from RSS/Atom feeds, 24 from `<article><time>`, 9 from JSON-LD and 7 from `article:published_time`;
  - 21 have no title.
- **Lost because:** **not determinable from our side.** Candidates:
  - the field name (`site_activity`, where Builderr says "dated news");
  - an object value;
  - evidence that is an XML feed rather than a page.

  Builderr's statement that *no* dated-news claim was scored says that, whatever the reason, this
  representation did not count.
- **Not extracted at all:** news listings that state dates only next to each title (no `<time>` element), and
  listings that state no dates at all. In the second case the date is on the article page, which is never fetched
  (Granne, BORI). 22 of the 121 verified sites have a captured news page.

### Jobs: careers pages found, positions not read

- **Published:** 1 company (schema.org `JobPosting`).
- **Discovered but not read:** 20 careers pages were captured on verified sites. Re-reading them shows:

  | Careers pages | What they show |
  | --- | --- |
  | 2 | Positions linked from the careers page |
  | 1 | States that no positions are open (Granne) |
  | 17 | No linked position |

  A careers page is published as `websites.careers_page`, which is not a job posting and must not become one.

### Websites and the 37.6%

- In the 1,200 run, 81 companies have a registry website that we did not verify.
- Across the universe, **10,244 of the 44,855 companies with a registry website (22.8%) share their website
  domain with at least five other entities**. Examples:

  | Domain | Entities |
  | --- | --- |
  | usbl.no | 1,442 |
  | vestbo.no | 625 |
  | obos.no | 551 |
  | bate.no | 458 |
  | bori.no | 301 |

  They are mostly housing cooperatives and sameier (6,633 SAM, ESEK or BRL entities have a registry website).
- Our policy rejects every one of these as not the entity's own site. Builderr's pool evidently counts at least
  one (BORI, 813396092), which is a plausible part of the gap between our coverage and the pool's.

## What Revision 1 changes, and what it does not

All of this is done without new sources, without Brave, NAV or the LLM, and without touching synthesis or UX
design.

1. **Social.** `public_activity.social_profile` claims whose value is the URL exactly as linked on the captured
   page, with `platform`, `canonical_url` (the de-duplication key only), `source_page` and `evidence_span`.
   The v1 record's rewritten links are no longer published.
2. **Dated news.** `public_activity.news_item` claims:
   - from listing pages that state a date next to a title;
   - from structured dates (JSON-LD, meta, `<time>`, feeds) as before;
   - from at most a few article pages linked from an already-fetched news listing that states no dates, within
     the existing company budget.

   A date is published only when the page states it.
3. **Jobs.** `hiring.job_posting` claims from positions listed on the verified site's careers page, as well as
   JobPosting. A careers page with no open position yields none.
4. **Validation.** Every value must occur in the captured page it cites (`evidence_text.py`):
   - the URL, as linked;
   - the title, in the page text;
   - the date, stated in the page.

   A failing candidate is counted, never repaired.
5. **Managed entities (separate change, can be dropped on its own).** A registry-designated website that
   belongs to the entity's registered *forretningsfører* is accepted as a labelled `MANAGER_DESIGNATED` website.
   This requires all of:
   - the entity's own Brreg record names the site;
   - Brreg lists an organisation as the entity's forretningsfører;
   - that organisation's organisation number is printed on the site.

   Only its news items are published; the manager's own social profiles and jobs are not attributed to the
   managed entity.

Results: `docs/revision-1-results.md`.
