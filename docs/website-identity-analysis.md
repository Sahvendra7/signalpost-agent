# Website identity analysis: the 976744667 → arasenstadion.no false match

Evidence gathered 2026-10-03 by fetching the live pages and the open Brreg entity records. Phase 4A
captured the candidate with sha256 `ef2dd068…` (`measurements/phase4a-2026-10-02/e4-site-discovery.json`).
The page has changed since, and today's homepage hashes to `40ad70ef…`, but every signal below appears
in both. This is analysis and a proposal only; the gate has **not** been changed.

## What happened

| Step | Detail |
|---|---|
| Company | 976744667 ÅRÅSEN STADION AS. No registry website, no registry e-mail; registry phone present. |
| Candidate source | `name_domain_guess`: legal-name tokens `arasen` + `stadion` → `arasenstadion.no`. The domain resolved. |
| Gate | `discovered_site_strict_v1`, rule (b): "full legal name on homepage plus registered postcode and street on the site", score 0.95, so `exact`. |
| Truth | Third-party fan site. Title: "🏟️ Åråsen Stadion Fansite - Hjemmet til Lillestrøm Sportsklubb". Footer: "Kontakt stadion … lsk.no/om-stadion/". The obfuscated contact e-mail (Cloudflare `data-cfemail`) decodes to `lsk@lsk.no`, a different organisation's domain. No organisation number anywhere. |

## Root cause

Rule (b) tests **aboutness, not control**. The legal name and the registered address on a page prove
the page is *about* the entity or its premises. They do not prove the entity *operates* the page. The
weakness is sharpest when a company is named after a public place (a stadium, a building, a street, a
farm, a property). Any fan, news, tourism or directory page about the place repeats exactly the name
and address the rule looks for.

The phone number would not have saved it. The registry phone for 976744667 ends in "…6 60", and the fan
site prints the stadium's number 63 80 56 60. A registry-phone rule would have **passed** this site
too. Phone numbers are public facts that third parties copy, so they can corroborate, never prove control.

## Signals on the five accepted discovery candidates

| Company | Domain | Org no. on site | Own-domain mailbox on site | Registry e-mail domain | Registry phone on site | Third-party markers | Audit |
|---|---|---|---|---|---|---|---|
| 920772099 SPIREN DESIGN AS | spirendesign.no | **yes** (footer "Org.nr: 920 772 099") | yes | none | n/a | none | correct |
| 921136501 LYSE ROM AS | lyserom.no | **yes** (footer "921136501MVA") | no (gmail) | none | n/a | none | correct |
| 927818094 BLI OPTIMAL AS | blioptimal.no | no | **yes** (on `/kontakt-oss/`, crawled pages) | none | n/a | none | correct |
| 986757368 ANNEN VRI AS | annenvri.no | no | **yes** (`post@annenvri.no`, footer) | none | yes | none | correct |
| 976744667 ÅRÅSEN STADION AS | arasenstadion.no | no | **no**: only `lsk@lsk.no` | none | **yes** | **"Fansite" in title**; contact delegated to `lsk.no` | **wrong** |

The two genuine sites that passed only via rule (b) both publish a mailbox on their own domain. The
fan site publishes only another organisation's mailbox.

## Proposed trust model (four classes)

| Class | Definition | Publish? |
|---|---|---|
| 1. Registry-linked | URL is the registry `hjemmeside` for this organisation number | Yes, if the existing registry gate passes (org number, or full legal name in homepage identity text) |
| 2. First-party discovered | Not registry-listed, and passes **one control rule** below with **no disqualifier** | Yes |
| 3. Third-party / fan / community / directory | Any disqualifier fires | Never; record the reason |
| 4. Ambiguous | Neither of the above | Never |

**Control rules** (any one suffices):

- **C1. Organisation number in the site's own legal/footer/contact text** (`identity_text_excerpt` of a
  crawled page), with at most one other distinct 9-digit organisation-number-shaped value on the site.
  This excludes directories and partner lists.
- **C2. Exact legal name + registered postcode + street token (today's rule b) PLUS a control indicator**:
  - a contact e-mail whose domain is the site's own registered domain, or
  - the open registry `epostadresse` domain equals the site's registered domain.

**Corroboration only** (never sufficient alone): registry phone/mobile on the site, social links, an
address alone, a matching page title.

**Disqualifiers** (class 3 regardless of other signals):

- D1. Third-party markers in title, `h1` or meta description: fansite, fan site, fanside, supporter,
  uoffisiell, unofficial, ikke offisiell, wiki, katalog, bedriftsoversikt.
- D2. Delegated contact: the site publishes contact e-mails, none on its own domain, and at least one on
  a different registered domain that is not a free-mail provider (`lsk@lsk.no` on arasenstadion.no).
  Free-mail-only sites (e.g. lyserom.no's gmail) are not disqualified by D2.
- D3. Directory shape: three or more distinct organisation numbers on the crawled pages.
- Existing: parked, for-sale and hosting placeholders.

## Effect on the measured candidates (applied by hand; not implemented)

| Gate | Accepted | Correct | Wrong | Lost correct |
|---|---|---|---|---|
| `discovered_site_strict_v1` (current) | 5 | 4 | **1** | — |
| Proposed class model | 4 | 4 | **0** | 0 |

The rule only tightens rule (b). The 13 Phase 4A candidates that were ambiguous stay ambiguous. With
n = 5 accepted candidates this is a hypothesis test, not a precision estimate. Before adoption it needs
the adversarial fixtures (place-named companies with fan/news pages, directories listing the org number,
group sites listing subsidiary numbers, sites with only free-mail contact) and a re-run of the Phase 4A
discovery sample.

## Implementation notes for V2 (not done now)

- The website fetcher must keep `mailto:` targets and decode Cloudflare `data-cfemail` / `/cdn-cgi/l/email-protection#…`
  values (the XOR decoding is deterministic). Without this, C2 and D2 cannot see obfuscated addresses.
- Record the class and the deciding signal on every website claim, so a reviewer can see why a site
  was published.
