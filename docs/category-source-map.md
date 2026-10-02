# Builderr category → source map

Only Builderr's own materials count as support. Those reachable from this repository:
- `[STARTER]`: this repository as shipped by Builderr (README, OUTPUT_CONTRACT.md).
- `[SITE]`: builderr.ai text seen through search snippets. The official page itself is blocked from the
  container, so this is indirect.
- `[OWNER]`: area list relayed by the project owner from the official page: filings, leadership,
  locations, websites, hiring/public activity.

"Measured coverage" is UNMEASURED for every row (see `docs/live-source-expansion-results.md`).

| Builderr category | Eligible sources (in code) | Evidence observed | Measured coverage | Confidence the source contributes |
|---|---|---|---|---|
| Filings | Regnskapsregisteret latest accounts (`/regnskap/{org}`); filed-year list and copy PDF | Not observed live | UNMEASURED | **Supported**: `[SITE]` names "official filings"; `[STARTER]` "fetches official financials". Whether PDF existence/hash counts separately is UNCONFIRMED. |
| Leadership | Brreg roles (`/enheter/{org}/roller`) | Not observed live | UNMEASURED | **Supported**: `[SITE]` "leadership", "who runs it"; `[STARTER]` "roles". |
| Locations | Brreg business/postal address; registered subunits | Not observed live | UNMEASURED | **Supported**: `[SITE]` "locations", "where it operates"; `[STARTER]` "registered workplaces". Whether the registered address alone satisfies the category is UNCONFIRMED. |
| Websites | Registry `hjemmeside` (identity-gated); discovered sites (strict gate); company-site social links | Not observed live | UNMEASURED | **Supported** for verified company sites: `[SITE]` "websites"; `[STARTER]` "official company pages, company-owned profiles". Discovered (non-registry) sites: same category, UNMEASURED precision. |
| Hiring | NAV job feed, orgnr-verified | Not observed live | UNMEASURED | Category **supported** (`[OWNER]` "hiring/public activity"; `[STARTER]` lists "jobs" as differentiating evidence). Source permission for evaluator runs is **UNCONFIRMED** (public token is "for experiments"). |
| Public activity | Brreg update feed (`registry_activity`); roles `sistEndret` date; company-site news (not run in batch) | Not observed live | UNMEASURED | **UNCONFIRMED** for registry updates (see below). `[STARTER]` names "dated activity" and "permitted public signals" without defining them. |

## registry_activity vs public_activity

Kept as separate labels. Arguments, neither of them decisive:

- For: the activity area is "dated" (`[STARTER]` "jobs, dated activity, ratings/reviews"). A Brreg update is
  dated, official and exact to the organisation number.
- Against: `[STARTER]` lists activity among *external* evidence ("The strongest differentiator is external
  evidence ..."). The registry is the identity anchor, not external. `[SITE]` describes the profile as covering
  "official filings, leadership, locations, websites and public activity", which separates the official
  registry areas from "public activity".
- An update row's `dato` is when Brreg published the change, not when the company acted. Without
  `endringer` (field-level change detail), an `Endring` row says only that *something* changed.

**Status: UNCONFIRMED.** It needs Builderr's evaluation contract text, which the official page links to
and this container cannot read. Until then, `registry_activity` must not be reported as public-activity
coverage in any score claim.
