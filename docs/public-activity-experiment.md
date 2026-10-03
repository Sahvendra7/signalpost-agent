# Public-activity experiment (Phase 4C)

Measurement only; nothing here is in the batch command. Internal label **`public_activity`**.
**SCORING_MAPPING = UNCONFIRMED** (see "What the official material says").

| Item | Value |
|---|---|
| Date | 2026-10-03, ~10:00 UTC |
| Code | `d83f32c` plus the item-URL fix committed with this document. 181 tests pass. |
| Sample | Fixed Phase 4A sample (100 companies, sha256 `80eb79e6…7677`); baseline profiles and envelopes from Phase 4A |
| Command | `uv run python scripts/run_public_activity_experiment.py --profiles out/experiments/baseline-profiles.jsonl --envelopes out/experiments/baseline-envelopes.jsonl --discovery out/experiments/e4-site-discovery.json --out out/experiments-public-activity --search` |
| Raw outputs | `measurements/phase4c-public-activity-2026-10-03/` |
| Cost | $0 (no paid API ran; Brave had no key) |

## What the official material says

Read on 2026-10-03 from builderr.ai. The sample page is archived by hash only:
`measurements/phase4c-public-activity-2026-10-03/builderr-sample.sha256`.

- **Source policy** (`/starter-briefs/signalpost-sources.md`): permitted first-party sources include
  "Sitemap, news, investor, careers, location and contact pages" and "**Social or video profiles linked by
  the verified company site, subject to the destination platform's access terms**". It also says "Do not
  scrape a platform when its terms, robots policy or applicable law prohibit the submitted method",
  naming LinkedIn and Meta.
- **Brief** (`/starter-briefs/signalpost.md`), envelope section 5: "Hiring and dated public activity from
  permitted sources". Section 4: "Verified official website and **company-owned profiles**".
- **Official sample** (`/signalpost`): coverage has five dimensions, `company`, `financials`,
  `people_places`, `website` and **`footprint`** (labelled "Public footprint", section "Hiring & activity").
  In the embedded data, **`footprint` is true exactly when the company has ≥1 external profile handle**:
  52/100 companies, **0 mismatches**. Dated posts and jobs are not required. All 87 handles marked
  `rightsStatus: "approved"` are exactly the social links found on identity-verified company websites
  (87/87). A further 16 `experimental` handles come from the reference crawler's LinkedIn discovery.

Conclusion: in Builderr's own sample, a **site-linked company profile** fills the fifth area. Whether the
**evaluation contract** scores it that way is not stated: the sample is a display, not the scorer.
Hence `SCORING_MAPPING = UNCONFIRMED`. The same holds for dated first-party news. The brief asks for
"dated public activity", but the sample's footprint flag does not depend on it.

## Method

1. **Verified sites.** The 8 registry-linked sites that pass the existing registry gate, plus the 5 sites
   accepted by Phase 4A non-search discovery, re-checked with **identity gate v2**
   (`experiments/identity_v2.py`, policy in `docs/website-identity-policy-v2.md`).
2. **Site-linked profiles.** Outbound links on the verified homepage and up to three same-site pages
   (feed and news pages), plus JSON-LD `sameAs`. Share/intent/plugin links are excluded. A link is
   **OFFICIALLY_LINKED** only if the existing social-identity gate passes (normalised legal name in the
   handle) or the link is the organisation's own JSON-LD `sameAs`. Otherwise it is **AMBIGUOUS**.
3. **Dated activity.** Only from the verified site: declared RSS/Atom feeds, JSON-LD `datePublished`,
   `article:published_time`, and `<time datetime>` inside `<article>`. A date is kept only when the source
   states it, and future or implausible dates are rejected. The item URL must be on the company's own
   domain, otherwise the page URL is used.
4. **Platforms are never fetched.** Not LinkedIn, Facebook or Instagram (source policy), and not YouTube
   feeds (`robots.txt` disallows `/feeds/videos.xml`). Robots is honoured on every site; 401/403 on
   robots means disallow.

## Results (n = 100)

| Metric | Baseline (V1) | Website discovery (Phase 4A, gate v1) | This experiment |
|---|---|---|---|
| Companies with a verified company website | 8 | 13 by gate (12 after audit) | **12** (8 registry + 4 discovered; gate v2 rejects arasenstadion.no) |
| Companies with ≥1 site-linked profile | 2 | not measured | **5** |
| Companies with ≥1 dated first-party activity | 0 | — | **6** (3 within 365 days) |
| Companies with profile **or** dated activity | 2 | — | **9** |
| Profiles accepted / ambiguous | 2 companies | — | **8 / 4** (Facebook 5, Instagram 1, LinkedIn 1, YouTube 1) |
| Dated activities | 0 | — | **33** (0 undated items kept; all from site feeds) |
| Wrong-company matches | 0 | 1 (arasenstadion.no) | **0** in manual audit |
| HTTP requests (attempts) | 590 | +206 | **+60** (23 gate v2, including 5 Brreg entity reads; 37 site crawl) |
| Runtime | 76.5 s | +59.5 s | **+18.2 s** (6 workers; process wall 19.6 s, peak RSS 156 MB) |

### Incremental company coverage in the fifth area (vs baseline 2)

| Definition | Companies | Incremental | Note |
|---|---|---|---|
| Site-linked profile (matches the official sample's footprint logic) | 5 | **+3** | All 3 come from discovered first-party sites (920772099, 921136501, 927818094) |
| Profile or dated first-party activity | 9 | **+7** | Adds 875606662, 919378875, 920186114, 986757368 via feeds |
| Profile or activity within 365 days | 6 | +4 | Several feeds are stale: newest items from 2017, 2019 and 2021 |

### Derived (A–G)

| | Value |
|---|---|
| A. Companies newly covered | +3 (profile definition) / +7 (profile or dated) |
| B. Verified facts newly found | 8 profiles + 33 dated activities = 41 (baseline already had 2 of the profiles) |
| C. Activities / company | 0.33 per sampled company; 5.5 per company with activity |
| D. Profiles / company | 0.08 per sampled company; 1.6 per company with a profile |
| E. Requests / company | 0.60 per sampled company; 5.0 per verified site |
| F. Seconds / company | 0.18 (wall ÷ 100) |
| G. Cost / company | $0 |

### Audit notes

- **Accepted profiles (8):** each is linked from a FIRST_PARTY or registry-verified site and the handle
  carries the normalised legal name, e.g. `facebook.com/stiftelsencrux`,
  `linkedin.com/company/stiftelsen-crux-hovedkontor`, `facebook.com/ByggmesterUlfJohannessenAs`. No wrong
  company was found. Platform pages were not opened, so reciprocal verification was not possible.
- **Ambiguous profiles (4) are correctly withheld.** kilishockey.no (KONGSVINGER IL ISHOCKEY) links
  `facebook.com/KILtoppfotball` and `instagram.com/kiltoppfotball`, the club's **football** entity, a
  different legal entity. Grønsand's `facebook.com/gronsand` and `instagram.com/gronsandgjestagard` fail the
  name gate ("gjestagard" vs "GJESTEGÅRD"). They are probably genuine, so this is recall the gate
  deliberately gives up.
- **One extraction defect was found and fixed during the audit:** an `<article>`-level date picked up a
  Facebook share-button URL as its item URL. The dates were source-stated, but the URL is now restricted
  to the company's own domain. The fix has a test; coverage numbers did not change.
- **Freshness:** 3 of 6 companies with dated activity have nothing newer than 2021. Dates are recorded
  as published by the source and never adjusted.

## Comparison with NAV (hiring)

| Path | Fifth-area companies added | Requests | Runtime | Precision | Credential |
|---|---|---|---|---|---|
| NAV S1 (name prefilter) | +1 hiring | +41 | +67.9 s | 0 wrong | public experiment token |
| NAV S2 (full orgnr index) | +2 hiring | +9,764 | ≈ +754 s | 0 wrong | public experiment token |
| **Website → site-linked profile** | **+3** (sample definition) | **+60** | **+18.2 s** | 0 wrong | none |
| Website → profile or dated activity | +7 | +60 | +18.2 s | 0 wrong | none |

Overlap: NAV's 975387011 (STIFTELSEN CRUX) is already covered by its site-linked profiles.

## Main limitation

The free path is capped by website coverage: **88 of 100 companies have no verified site**, so this
path cannot reach them. That gap is what search (`docs/search-experiment-results.md`) would have to close.
