# Scoring model (what we optimise for)

No official Builderr score has been received for this repository. Nothing here is a score claim.

## Published rubric

| Dimension | Points | Source |
|---|---:|---|
| Recall & coverage | 50 | `[USER]`; also quoted from the challenge page by `[2ND]` repositories |
| Precision & evidence | 30 | `[2ND]` quoting the page; `[OPEN]` |
| Synthesis | 12 | `[2ND]`; `[OPEN]` |
| UX | 8 | `[2ND]`; `[OPEN]` |
| **Qualification** | **>= 65/100 on an official run** | `[SITE]` "minimum qualification score of 65/100 on an official run" |

Other facts from the page `[SITE]`: $2,500 in final rewards; 100 random companies per day; submissions
close Oct 21; a sample of 100 companies had 48 with data in all five categories.

Superseded rubrics in the starter docs (`external-footprint-loop.md`: 55/15/10/12/8;
`score_competition_v3.py`) are **not** the current rubric. They are kept for reference only.

## Constraints confirmed by the project owner (2026-10-02, from the official page)

- Recall + coverage = 50 points: **70% company coverage, 30% individual checked facts**.
- Information areas: filings, leadership, locations, websites, hiring/public activity.
- Builderr supplies fresh companies at runtime; precomputed profiles are not used for ranking.
- Every supplied company must produce one terminal result; wrong-company publications are especially serious.
- Third-party API cost can be a tiebreaker.

Consequence: a source that adds facts to companies already covered in an area is worth far less than
one that covers a company–area pair that was empty. The experiment harness therefore reports
coverage per area (share of companies with ≥1 verified fact) as the primary metric.

## How each dimension most plausibly scores (working model, `[OPEN]` until confirmed)

### Recall & coverage (50)
Pooled-evidence recall: the evaluator holds facts known to exist for each sampled company (likely
pooled from all entrants plus its own research) and measures what fraction we return, per category.
Implications:
- Every category matters roughly equally; an empty category costs its full share.
- `not_available` from a source we *did* check is honest but still unrecalled; recall only rises by
  retrieving more exact-entity facts.
- Breadth of facts within a category (all board members, all subunits, all financial lines) probably
  counts, so emit fact-level claims, not one blob per module.

### Precision & evidence (30)
- A wrong-company fact is the costliest error (also undermines recall credit).
- Each `available` claim needs resolvable evidence (Builderr's citation validator rules).
- Dates and reporting periods must be present and correct.

### Synthesis (12)
A readable profile built only from claims: what the company does, people, places, latest financials,
hiring, recent activity, changes, unknowns. Every number/name/date in prose must appear in a claim.

### UX (8)
Ease of inspection: identity → facts → evidence → dates → changes → unknowns with minimal clicks.

## Optimisation priority (expected score impact ÷ engineering cost)

1. Contract-conformant envelope with fact-level claims (protects all 100 points). Low cost.
2. Exact-org-number official sources fully exploited (roles, subunits, accounts, filing years,
   registry purpose/activity, registry update/announcement history). Covers ~100% of companies across
   filings, leadership, locations and part of activity. Low–medium cost.
3. Exact-org-number job feed (NAV public feed carries employer org numbers). Medium cost; must confirm
   permission.
4. Website discovery for the 86% without a registry URL, verified by org number on the page. Medium–high
   cost; needs a permitted discovery source.
5. Deterministic synthesis + static HTML report. Low cost, 20 points.
