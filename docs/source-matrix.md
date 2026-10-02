# Source matrix

"Permitted?" is this repository's reading of the starter's source rule. The official permitted-source
page could not be fetched (`[OPEN]`); every row marked *confirm* must be checked against it before the
connector is enabled in the evaluated command. Identity strength: **org** = keyed by exact
organisation number (no entity resolution needed); **verify** = must pass an identity gate.

| Source | Permitted? | Info types | Identity | Access | Stability | Recall contribution | Precision risk | Rate-limit risk | Evidence quality | History? |
|---|---|---|---|---|---|---|---|---|---|---|
| Brreg Enhetsregisteret bulk CSV | Yes, NLOD 2.0 `[STARTER]` | identity, form, NACE, address, website, employees, latest-accounts year | org | 1 download/day | High | 100% identity | None | None | Row-level; hash is of whole file | Current only |
| Brreg entity API `/enheter/{org}` | Yes `[STARTER]` | as bulk + purpose (`vedtektsfestetFormaal`), activity (`aktivitet`), foundation/registration dates, flags | org | JSON, keyless | High | 100% identity + description for most | None | Low | Exact bytes hashable | Current |
| Brreg roles `/enheter/{org}/roller` | Yes `[STARTER]` | CEO, chair, board, auditor, accountant, last-changed date | org | JSON | High | Leadership for ~all AS | None (person names are registry-bound) | Low | Exact | Current + `sistEndret` |
| Brreg subunits `/underenheter?overordnetEnhet=` | Yes `[STARTER]` | establishments, addresses, employees, NACE | org | JSON | High | Locations beyond HQ for a minority | None | Low | Exact | Current |
| Brreg group `/konsernstruktur/{org}` | Yes `[STARTER]` | parent/subsidiaries | org | JSON | Medium (often 404) | Relationships, small share | None | Low | Exact | Current |
| Regnskapsregisteret `/regnskap/{org}` | Yes `[STARTER]` | latest normalised accounts with period | org | JSON | High | Filings for ~all of universe (universe is defined by 2025 filers) | None | Low | Exact, has period | Latest year |
| Regnskapsregisteret filing years + PDF copies | Yes `[STARTER]` | filed years, official PDFs (directors' report, notes, employees, auditor) | org | JSON + PDF | Medium | Multi-year filings, description text from årsberetning | Low | **~30/min** | Exact PDF bytes | Multi-year |
| Brreg update feed `/oppdateringer/enheter` | Likely (same NLOD API) — *confirm* | dated change events (type, date) | org | JSON | Medium | Dated public activity for ~all | None | Low–Med | Exact | Yes |
| Brreg announcements (kunngjøringer) | *confirm* (HTML on w2.brreg.no; robots/terms unknown) | dated official announcements (board changes, address, capital, merger, dissolution) | org | HTML | Medium | Dated public activity for most | None | Unknown | Exact page | Yes |
| Registry-linked company website | Yes, with robots `[STARTER]` | description, contact, people, locations, news, social links | verify (org number or full legal name on page) | HTML | Low–Med | ~14% of universe have one | Medium (parent/brand sites) | Per-host politeness | Page bytes + span | Current; news dated |
| Company-site outbound social links | Yes as company-owned links `[STARTER]` | LinkedIn/Facebook/Instagram/YouTube URLs | verify (site must pass gate; handle must match name) | from site HTML | Medium | Small | Low–Med | None | Site bytes | Current |
| NAV public job feed (arbeidsplassen) | *confirm* (public token API; licence `[OPEN]`) | current job ads with employer org number, dates | org | JSON feed | Medium | Jobs for hiring companies (minority) | Low (org-keyed) | Low | Exact JSON | Posting dates |
| Finanstilsynet entity register | *confirm* | licences for regulated firms | org | JSON | Medium | Small, sector-specific | None | Low | Exact | Current |
| Wikidata (P2333 Norwegian org number) | *confirm* (CC0) | website, founding, HQ for large firms | org (via P2333) | SPARQL/JSON | Medium | Very small | Low | Low | Exact | Partial |
| Search APIs (Brave etc.) for site discovery | Only with licensed API and declared cost `[STARTER]` | candidate URLs only (never facts) | verify by re-fetch | API | Medium | Websites for part of the 86% without registry URL | High unless gated | Paid quota | Candidate only; evidence is the re-fetched page | — |
| Google News RSS, Google Maps scrape | Not as automated scraping (search-engine terms) — **exclude** from evaluated command | news, ratings | verify | — | — | — | High | High | — | — |
| LinkedIn, Meta, Indeed, Glassdoor direct collection | **Exclude** `[STARTER]` (restricted) | — | — | — | — | — | — | — | — | — |
| Proff / Purehelp / other aggregators | **Exclude** (third-party scraping of resold registry data; terms restrict) | — | — | — | — | — | — | — | — | — |

## Category → source plan

| Category | Core (always) | Secondary (when relevant) | Discovery |
|---|---|---|---|
| Identity | entity API (or bulk) | — | — |
| Official filings | accounts API | filing years + latest PDF (rate-limited) | — |
| Leadership | roles API | company site team page (verified) | — |
| Locations | entity addresses, subunits | company site contact page | — |
| Websites | registry `hjemmeside` (verified) | email domain if exposed, PDF/annual-report URL | licensed search (verified) |
| Public activity | update feed / announcements, filing events, role last-changed | company-site news (verified, dated), NAV jobs | — |
