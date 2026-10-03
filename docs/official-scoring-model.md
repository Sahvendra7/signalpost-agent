# Official scoring model (reconstructed from the official contract)

Audit date: 2026-10-03. Only Builderr's published text defines the model (source keys and hashes:
`docs/official-requirements-matrix.md`). Board figures from `PAGE` ("Reviewed 3 October 2026") are used as
**evidence about how the rubric behaves**, never as a rule. Our own measurements are engineering numbers; no
Builderr score is claimed or predicted from them.

## 1. What the contract says

Scoring version 2, effective 26 August 2026 for every Round 1 entrant (`EVAL`, `BRIEF`). The total is 100 points:

| Dimension | Points | Official definition (verbatim) |
|---|---|---|
| Recall and coverage | 50 | "For every external field family, coverage is 70% company recall and 30% individual-claim recall against the independently verified union of discoveries from every submitted crawler and Builderr's own crawlers." (`EVAL`) |
| Precision, exact identity and evidence | 30 | "We check that each fact belongs to the right company and has a valid source and date. Wrong or unsupported facts lose points. A material wrong-company match also blocks qualification." (`PAGE`) |
| Decision-useful synthesis | 12 | "The profile should explain what the company does, what changed and what remains unknown, with sources for its conclusions." (`PAGE`); "without making unsupported claims" (`BRIEF`) |
| UX and interaction | 8 | "We check whether a user can find, compare and verify company information on desktop and mobile." (`PAGE`) |

### Recall and coverage (50)

Per external field family *f*:

```
score_f = 0.70 × (companies we cover in f ÷ companies the pool covers in f)
        + 0.30 × (verified facts we found in f ÷ verified facts in the pool for f)
```

Official worked example (`BRIEF`, `EVAL`, `PAGE`): the pool holds 50 job postings across 20 companies. Finding 30
postings across 15 of those companies gives 0.70 × 75% + 0.30 × 60% = **70.5%** "for that information type".

Further official rules:

* **The pool is the union of everyone's verified findings**, including Builderr's own crawlers. It is cumulative and
  versioned; "each verified addition creates a new pool hash and every entrant is rescored against that same latest
  version". It "freezes only after all eligible final submissions have been verified" (`EVAL`). So recall is
  relative to what *any* agent found, and it can fall over time without any change on our side.
* **Sparse batches:** "If the verified pool has fewer than 15 positive company-field opportunities across at least
  three external field families, recall is reported as not measured for that batch rather than as 0%" (`EVAL`).
* **Abstention:** "Abstention is reported separately and cannot satisfy coverage" (`EVAL`).

**NOT PUBLISHED:** the list of external field families; how family scores combine into 50 (equal weights or not);
whether registry-derived fields are "external"; how a fact is matched to a pool fact (exact value, normalised URL,
or something else); and whether a family where the pool is empty for a batch is skipped.

### Precision and evidence (30)

Published elements: right company; "valid source and date"; "Wrong or unsupported facts lose points" (`PAGE`).
"Company-matching precision is separate from factual accuracy" (`BRIEF`). Official-run checks (`EVAL`): published
material claims have source, retrieval time and reporting period where relevant; no fabricated financial value or
material wrong-company publication. **NOT PUBLISHED:** the formula, the sampling of checked facts, and how
`ambiguous` or `not_available` claims are treated (they cannot be "wrong", but "cannot satisfy coverage").

### Synthesis (12) and UX (8)

Only the verbatim definitions above are published. **NOT PUBLISHED:** the rubric steps, whether they are judged
from the envelopes, from a hosted view, or from the repository, and whether a JSON-only submission can score UX at
all. `SAMPLE` (Builderr's own product sample) shows what Builderr considers good: a company list with search and
sort, a per-company profile with sections (overview, financials, leadership, locations, hiring & activity, run
evidence, sources found), "View source" links with retrieval time on every section, coverage dots per area, and
"Ask Signalpost" answers built from **deterministic templates** over the profile's own facts ("Every answer is
limited to the sources shown on this profile. Missing evidence stays missing.").

### Qualification, ranking and ties

* "Qualification is an official run with 65/100 or more." (`EVAL`) Coverage, recall and precision "are scored
  dimensions, not separate qualification thresholds".
* A material wrong-company publication or fabricated financial value keeps a run from becoming official (`BRIEF`,
  `EVAL`).
* "Final ranking uses the mean across every scheduled daily batch while an entrant has an active frozen version. An
  entrant-caused failed or missed batch scores zero after Builderr reproduces the failure in a clean evaluator run."
  (`EVAL`)
* "Revisions … never replace earlier batch results." (`EVAL`)
* "Ties break on fewer wrong-company publications, then higher weighted company recall, then lower declared
  third-party cost." (`EVAL`)

## 2. Evidence from the public board (3 October 2026)

28 submissions, 19 assessed, **0 qualified**. Every scored entry was "recalculated against the same locked
1,200-company set", and "Each scored entry ran twice".

| Dimension | Top | Typical | Observed values |
|---|---|---|---|
| Recall /50 | 17.69 (Karthik) | **12.83** (9 entries exactly; 12 entries in 12.83–12.91) | 5.15 … 17.69 |
| Evidence /30 | 29.00 (the entrant with the second-lowest recall) | **26.92** (most entries) | 22.92 … 29.00 |
| Synthesis /12 | 12.00 | 12.00 or 9.46 | 4.80, 5.00, 7.15, 7.20, 9.46, 12.00 |
| UX /8 | 8.00 | 3.20 or 8.00 | 3.20, 6.40, 8.00 |
| Total | 60.51 | 52–60 | 41.29 … 60.51 |

Inferences. These are evidence, not rules, and are labelled as such everywhere they are used:

1. **Recall is the bottleneck for everyone.** No entrant exceeds 35.4% of the recall points. Many different agents
   land on an identical 12.83, which suggests a common baseline that every competent agent gets, plus very little
   external coverage beyond it.
2. **Synthesis and UX are largely "won" by well-built entries.** The leaders take 12/12 and 8/8. An entry without
   them gives away up to 20 points that the leaders bank.
3. **The 65 bar arithmetic.** With evidence at about 27 and synthesis plus UX at 20, a run needs **recall ≥ 18/50
   (36%)** to qualify. That is above every assessed entry today.
4. Discrete UX values (3.20 = 40%, 6.40 = 80%, 8.00 = 100%) suggest a stepped rubric.

## 3. Which of our facts can contribute where

Families are not published. The table maps each fact we emit to the official wording it could fall under, and states
the strength of that mapping.

| Our claim (`category.field`) | Official wording it maps to | Likely scoring role | Confidence |
|---|---|---|---|
| `identity.*` (name, form, industry, employees, dates, flags) | "Legal identity" (`BRIEF` §1); `SAMPLE` area "Company record" | Precision (always correct). Recall only if registry families count as "external". | Mapping certain; recall role UNCONFIRMED |
| `description.registered_activity`, `statutory_purpose` | "what it does" (`BRIEF`) | Synthesis input; recall UNCONFIRMED | Medium |
| `description.website_description` | "what it does" | Synthesis input; possibly an external family (site-derived) | Medium |
| `filings.*` (7 figures × periods, latest filed year) | "how its latest filed numbers look" / "Latest annual accounts and available history" | Precision ("no fabricated financial value"); recall UNCONFIRMED (registry-derived) | Mapping certain |
| `leadership.*` (Brreg roles) | "who leads it" | as above | Mapping certain |
| `locations.*` (addresses, subunits) | "where it operates" / "registered workplaces" | as above | Mapping certain |
| `websites.official_website` | "Verified official website" (`BRIEF` §4); `SAMPLE` area "Company website" | **External** (needs crawling and identity proof). Strong candidate for an external family. | High |
| `websites.social_profile` | "company-owned profiles" (`BRIEF` §4); `SAMPLE` footprint area | **External**. Strong candidate. | High |
| `websites.careers_page` | "whether it appears to be hiring" (weak) | Possibly hiring support; not a job posting | Low |
| `websites.registry_listed_website` | Registry field; "does not, by itself, identify … the website" (`SOURCES`) | Not a verified website | Certain (does not count as verified) |
| `public_activity.site_activity` (dated first-party items) | "dated public activity" (`BRIEF` §5) | **External** | Medium-high (permitted and in scope; pool inclusion UNCONFIRMED) |
| `hiring.job_posting` (schema.org `JobPosting`) | "job postings" (the official worked example) | **External**, the one family Builderr names | High |
| `registry_activity.roles_last_changed` | none named | Probably none | Low |
| `relationships.group_structure` | "Group … relationships must be labelled" (`SOURCES`) | Precision / synthesis | Low for recall |

What each dimension can be earned from, given the contract:

* **Recall/coverage (50):** only verified, exact-company facts that also exist in the pooled union. Company recall
  (70%) rewards **breadth across companies**. One verified fact for a company counts fully toward that company in
  that family, so one verified profile for 100 companies is worth more than ten profiles for 10 companies.
* **Precision/evidence (30):** every published fact, registry facts included, needs the right company plus a valid
  source and date. More claims means more exposure. Unverifiable spans or undated claims are the risk.
* **Synthesis (12):** a per-company explanation of what it does, what changed and what is unknown, citing
  sources. None today.
* **UX (8):** a way for a person to find, compare and verify. None today.

## 4. Our measured position (engineering numbers, not a score)

From live runs of the declared command (V2) on companies never measured before. "Covered" means at least one available
fact.

| Sample | Verified website | Site-linked profile or dated activity | Job posting | All five areas |
|---|---|---|---|---|
| 4 × 100 (V2 comparison, `docs/v2-results.md`) | 46/400 (11.5%) | 31/400 (7.75%) | 0 | 31 |
| 150 unseen (this audit) | 12/150 (8.0%) | 8/150 (5.3%) | 0 | 8 |
| 1,200 unseen (this audit) | see `official-submission-checklist.md` §C | | | |

Structural ceiling: only **10.91%** of the 411,160-company universe has a registry website. Our non-search
discovery lifts verified sites slightly above that share of companies. `SAMPLE` (Builderr's reference, top
richness first) shows 97/100 websites and 52/100 footprint, but it is not a random sample.

## 5. Scoring opportunities revealed by the full contract

Ordered by expected points per unit of risk. None of them touches the identity gate.

1. **Deterministic synthesis (up to 12).** Template summaries over our own claims: what it does (registered
   activity plus verified site description), who leads it, where, latest filed numbers with period, website and
   profiles, what changed since the previous run, and an explicit unknowns list. Each sentence cites claim and
   evidence ids. This is the same technique `SAMPLE` uses. No LLM, no new requests, no precision risk.
2. **Static viewer (up to 8).** One self-contained HTML file generated from the envelopes: search, sort and compare,
   per-section source links with retrieval time and hash, and a mobile layout. No new requests.
3. **Breadth in external families (company recall is 70%).** Within permitted sources:
   * Jobs (the family Builderr names). Today we read only JSON-LD `JobPosting` on verified sites. Candidates:
     careers pages and ATS links reachable from the verified site (careers pages are named in `SOURCES`; the ATS
     host's terms are UNCONFIRMED) and NAV (UNCONFIRMED, ask Builderr).
   * Profiles and activity: widen same-site discovery (e.g. footer links on all fetched pages, `sameAs` in JSON-LD,
     news and sitemap pages) for already verified sites. Cheap, and inside the existing gate.
   * More verified websites: every extra verified site unlocks several families at once.
4. **Envelope clarity for the precision check:** an envelope-level state, top-level `legal_identity`, and
   `change_type`. These are low cost and remove interpretation risk on "valid source and date".
5. **Do not chase registry-only depth** (extra filing figures, Brreg update history) until Builderr confirms those
   families. `SAMPLE` uses exactly our seven financial figures and never uses registry events for activity.

## 6. What remains unknown, and the question to put to Builderr

1. The list of external field families and how they combine into 50.
2. Whether registry-derived facts count toward recall.
3. Whether site-linked profiles and dated company-site items are in the pool.
4. The time and resource budget (wall clock, CPU, memory, disk) and the network policy for official runs.
5. The batch file schema, and how the cutoff and the frozen registry snapshot are passed.
6. How synthesis and UX are judged (envelope field, hosted view, or repository artifact).
7. The model key, model and budget if an LLM is used.
