# Recall analysis (Phases 4A–4C)

Data: `docs/live-source-expansion-results.md` (100 companies, seed 20261002, frozen `461bdbf`).
This is a measurement summary. It does not compute or estimate a Builderr score and does not propose
architecture.

## How sources are ranked

Recall and coverage are worth 50 points. Within each information type, 70% is company coverage and 30%
is individual facts (`[CONTRACT]`, `[BRIEF]`). So sources are ranked first by **incremental verified
companies in a confirmed category**, then by incremental verified facts, then by cost (requests and
runtime), and are penalised by any wrong-company match.

## Company coverage gap by category (baseline)

| Category | Baseline companies | Gap (companies without) | Free source tested | Companies after free sources | Confirmed? |
|---|---|---|---|---|---|
| Filings | 100 (99 with values) | 0 (1 has no structured accounts) | extra open-accounts fields, PDF | 100 (no change) | yes |
| Leadership | 100 | 0 | — | 100 | yes |
| Locations | 100 | 0 | — | 100 | yes |
| Websites | 8 crawled-verified (17 registry URLs) | 83–92 | non-search discovery | 12 audited (13 by gate) | yes |
| Hiring | 0 | 100 | NAV job feed (Phase 4B, public experiment token) | 1 (S1) / 2 (S2) | yes (category); NAV credential UNCONFIRMED |
| Public activity / footprint | 2 (site-linked profiles) | 98 | Brreg update history; site-linked profiles + dated site activity (Phase 4C) | 5 (sample footprint definition); 9 profile-or-dated; 100 only if `registry_activity` counts | **UNCONFIRMED** scoring mapping; the official sample's footprint flag = ≥1 external profile handle |

The official-registry categories are already at the company-coverage ceiling on this sample. The
gaps in company coverage are websites, hiring and public activity: the external categories.

## Free sources ranked by incremental verified companies

| Rank | Source | Incremental companies (confirmed category) | Incremental facts | Extra requests | Extra runtime | Wrong matches |
|---|---|---|---|---|---|---|
| 1 | Non-search website discovery | **+4** websites (+5 by gate) | +4 sites | +123 site attempts (+83 redundant registry re-fetches) + 123 DNS | +59.5 s | **1** |
| 2 | Additional open-accounts fields | 0 | **+4,463** (filings ×2.4) | **0** | ≈ 0 | 0 |
| 3 | Filing copy PDF | 0 | 0 extracted (100 image-only documents) | +200 | +829.6 s | 0 |
| — | Brreg update history | 0 confirmed. +100 only if `registry_activity` is accepted as public activity. | +3,562 events | +180 | +21.2 s | 0 |

Readings:

- **Highest-value free source by the scoring rule: website discovery.** It is the only measured free
  source that adds companies in a confirmed category. The gain is small: 4 of 83 companies without a
  registry URL (4.8%). It also produced the only precision failure of the run.
- **Highest-value free source per unit of cost: the extra open-accounts fields.** They cost no
  requests and roughly double the filing facts, but add no companies. They can only affect the 30%
  fact share of filings, and only if Builderr's verified pool contains those fields (UNKNOWN).
- **Largest potential gain: Brreg update history.** It would add 100 companies, but only through an
  UNCONFIRMED mapping. The 100% recency is probably caused by the universe definition (2025 filers),
  so even a confirmed mapping may duplicate the filing fact.
- **PDF copies cost the most for the least.** With 2.1 s pacing they took 8.3 s per company, about 11×
  the baseline's wall time per company. All 100 PDFs were image-only, so no facts are extractable
  without OCR.

## Fifth area (hiring & public activity): Phase 4B–4C ranking

| Rank | Source | Incremental companies | Extra requests | Extra runtime | Wrong matches | Credential / policy |
|---|---|---|---|---|---|---|
| 1 | Verified site → site-linked profile (official sample's footprint logic) | **+3** | +60 | +18.2 s | 0 | none; explicitly permitted first-party source |
| 2 | Verified site → dated first-party activity (feeds, JSON-LD) | +4 beyond profiles (+7 total) | (same crawl) | (same) | 0 | none |
| 3 | NAV S1 | +1 | +41 | +67.9 s | 0 | public experiment token |
| 4 | NAV S2 | +2 | +9,764 | ≈ +754 s | 0 | public experiment token |
| — | Brave search | UNMEASURED | — | — | — | needs key |

The free fifth-area path is capped by website coverage. All 3 new profile companies came from discovered
first-party sites, so **website coverage (12/100) is now the binding constraint for two areas at once**
(websites and footprint). 88 companies have no verified site.

## Precision observations

- Baseline: 0 identity failures, 0 dangling evidence, 0 false refresh changes.
- Website discovery: 1 of 5 gate acceptances was wrong (`arasenstadion.no`, a fan site that names the
  stadium company's asset and address). The org-number rule (2/2 correct) held up. The legal name +
  postcode + street rule went 2/3: a third party that publishes the entity's name and address passes
  it.
- Name-domain guessing produced 145 of 155 candidates and all 5 acceptances. 123 guesses (85%) had no
  DNS. Registry e-mail domains produced 9 candidates, all ambiguous or unavailable. Two of those
  redirected to a different brand.

## Context from the public board (not a score estimate)

The board reviewed on 3 October 2026 lists 19 assessed entries. Recall ranges from 5.15 to 17.69 of
50, and 9 entries score exactly 12.83. No entry has qualified. This only shows that recall is the
weakest dimension across entrants. It is not used to estimate this agent's score.

## Remaining unknowns

1. NAV: measured (Phase 4B), +1–2 companies; OPTIONAL.
2. Brave or any search-based website discovery: UNMEASURED (no key). Eligible under the adaptive rule: 91/100.
3. Whether `registry_activity` / `roles_last_changed` count as public activity.
4. Whether registry fields count as "external field families" for recall.
5. Whether the verified pool contains the extra open-accounts fields.
6. Whether registry-listed but uncrawled URLs count as website coverage. Baseline: 17 listed vs 8 verified.
7. Variance: one 100-company sample. Discovery's +4 on n = 83 has a wide interval.
8. Website discovery's `nav_employer_site` candidate source: exercised in Phase 4B; 0 candidates (empty `employer.homepage`).
9. Whether the evaluation contract scores a site-linked profile as public activity (the official sample's display does).
10. Gate v2 is validated on 5 live candidates only.
