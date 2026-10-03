# Builderr category → source map

Only Builderr's own materials count as support. On 2026-10-03 builderr.ai was reachable, so the
official text was read directly (copies are in `out/builderr/`, which is not committed):

- `[CONTRACT]` `/docs/signalpost-evaluation-harness.md`: evaluation contract, scoring version 2 (effective 2026-08-26).
- `[BRIEF]` `/starter-briefs/signalpost.md`: full brief, including "Required company envelope".
- `[SOURCES]` `/starter-briefs/signalpost-sources.md`: permitted-source policy.
- `[PAGE]` `/challenges/signalpost`: challenge page.
- `[STARTER]` this repository as shipped (README, OUTPUT_CONTRACT.md).

Relevant official wording:

- `[BRIEF]` Required envelope sections: "2. Latest annual accounts and available history; 3. Leadership and
  registered workplaces; 4. Verified official website and company-owned profiles; 5. Hiring and dated
  public activity from permitted sources".
- `[PAGE]` "Collect company details, people, locations, financial results, jobs and public activity where available."
- `[CONTRACT]` "For every **external field family**, coverage is 70% company recall and 30% individual-claim
  recall against the independently verified union of discoveries from every submitted crawler and Builderr's
  own crawlers."
- `[SOURCES]` Preferred official sources: Enhetsregisteret bulk/API, Regnskapsregisteret API **and annual-account
  copies**, roles endpoints, subunit records. "Official data is the identity anchor. It does not, by itself,
  identify the public brand or website."

Measured coverage comes from the Phase 4A live run (100 companies, seed 20261002), which is in
`docs/live-source-expansion-results.md`.

| Builderr category | Eligible sources (in code) | Evidence observed live | Measured company coverage (n = 100) | Confidence the source contributes |
|---|---|---|---|---|
| Filings ("latest annual accounts and available history") | Regnskapsregisteret `/regnskap/{org}`. Copy-PDF list and file. | 2023–2025 periods; 7 fields published per period; 4,463 more numeric fields in the same response; 100 image-only PDFs | 100 (filed year); 99 with values | **Supported** (`[BRIEF]` §2, `[SOURCES]`). Whether the extra fields exist in Builderr's verified pool is **UNKNOWN**. |
| Leadership ("leadership") | Brreg roles | 495 role facts | 100 (CEO 63, chair 99) | **Supported** (`[BRIEF]` §3, `[SOURCES]` "official roles endpoints") |
| Locations ("registered workplaces") | Brreg business address; subunits | 329 facts | 100 address; 73 with subunits | **Supported** (`[BRIEF]` §3, `[SOURCES]` "official subunit records") |
| Websites ("verified official website and company-owned profiles") | Registry `hjemmeside` (identity-gated crawl); non-search discovery (strict gate) | 17 registry URLs (8 crawled and verified); +5 discovered by the gate, 4 correct | 8 crawled-verified (17 with a registry URL) → 12 audited with discovery | **Supported** (`[BRIEF]` §4). `[SOURCES]`: the registry alone does not identify the website, so a registry-listed URL that has not been crawled may not count. UNCONFIRMED. |
| Hiring ("hiring … from permitted sources") | NAV job feed (orgnr-verified) | not run | **0** (no source in V1); NAV UNMEASURED | Category **supported** (`[BRIEF]` §5, `[PAGE]` "jobs"). NAV's permission for evaluator runs is **UNCONFIRMED** (the public token is documented "for experiments"; `[PAGE]` forbids credentials tied to the entrant's own account). |
| Public activity ("dated public activity from permitted sources") | Brreg update feed (`registry_activity`); roles `sistEndret` (`roles_last_changed`) | 3,562 dated update events; 100 roles timestamps | **0 confirmed.** Raw: `registry_activity` 100, `roles_last_changed` 100 | **UNCONFIRMED** (see below) |

Raw source results with no Builderr category: identity (814 facts), description (registered
activity and statutory purpose, 201), relationships (group structure, 3). The description facts may
feed synthesis ("what the company does"), but that is not a coverage category.

## registry_activity vs public_activity

Kept as separate labels. The official text was read in this phase and does **not** settle the
mapping.

- For: `[BRIEF]` §5 asks for "dated public activity from permitted sources". A Brreg update is dated,
  comes from a preferred official source (`[SOURCES]`), and is exact to the organisation number.
- Against: `[CONTRACT]` scores recall per "external field family". `[SOURCES]` treats official data as "the
  identity anchor". Neither lists the update feed as an activity source.
- Measured caveat: all 100 sampled companies have an update in the last 365 days, probably because
  every universe company filed 2025 accounts in 2026 (`/sisteInnsendteAarsregnskap` is the most common
  changed field in the samples). 89.6% of events have no field detail. A large part of this "activity"
  repeats the filing fact.

**Status: UNCONFIRMED.** Until Builderr confirms in writing, `registry_activity` and
`roles_last_changed` must not be reported as public-activity or hiring coverage in any score claim.

## Open questions only Builderr can answer

1. Do official-registry fields (filings, leadership, locations) count as "external field families"
   for recall, or only as identity anchoring and precision?
2. Is a Brreg update event a "dated public activity" claim?
3. Does the verified pool include the additional open-accounts fields (e.g. `sumDriftskostnad`,
   `loennskostnad`), or only the headline fields?
4. Does a registry-listed website that was not crawled or verified count toward website coverage?
5. Is the NAV public token acceptable in an evaluator run?
