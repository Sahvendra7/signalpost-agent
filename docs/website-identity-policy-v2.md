# Website and profile identity policy v2 (experimental)

Implemented for experiments only in `src/norway_company_agent/experiments/identity_v2.py`; the batch
command still uses v1. Motivation and root cause: `docs/website-identity-analysis.md`
(976744667 → arasenstadion.no).

## Principle

A page that names the company and its address is **about** the company. Publication requires evidence
that the company **controls** the page. Name, logo, address, phone or a high search rank alone never
suffice.

## Classes

| Class | Meaning | Publishable |
|---|---|---|
| REGISTRY_LINKED | The registry `hjemmeside` for this organisation number; the existing registry gate passes | yes |
| FIRST_PARTY | Discovered independently and passes a control rule with no disqualifier | yes |
| OFFICIALLY_LINKED | A social/video profile linked from a REGISTRY_LINKED or FIRST_PARTY site (or its JSON-LD `sameAs`) whose handle passes the name gate | yes, with the relationship recorded |
| THIRD_PARTY | Parked domain, or contact delegated to another organisation's domain | no |
| FAN_COMMUNITY | Fan/unofficial/supporter/wiki/forum markers in title, h1 or meta | no |
| DIRECTORY | Three or more other organisation numbers on the captured pages, or directory markers; known directory hosts in search | no |
| AMBIGUOUS | None of the above | no |

## Control rules for FIRST_PARTY (any one, after disqualifiers)

- **C1:** the organisation number appears in the site's own footer/contact/legal text, with at most one
  other organisation-number-shaped value on the captured pages.
- **C2:** exact legal-name tokens in title/h1/meta **and** registered postcode **and** a registered street
  token **and** a control indicator: a mailbox on the site's own registered domain, or the open-registry
  `epostadresse` domain equal to the site's domain.
- **C1′:** the organisation number anywhere on the site plus an own-domain or registry mailbox.

**Corroboration only:** registry phone or mobile, address alone, a matching title, social links.

## Disqualifiers (checked first; they override control rules)

1. Parked, for-sale or hosting placeholder text.
2. FAN_COMMUNITY markers: fansite, fan site, fanside, supporterklubb, uoffisiell, unofficial, ikke offisiell,
   not affiliated, ikke tilknyttet; also wiki, forum.
3. Directory shape: three or more other organisation numbers, or directory markers.
4. Delegated contact: published mailboxes exist, none is on the site's own domain, and at least one is
   on a different non-free-mail domain. E-mail addresses obfuscated by Cloudflare (`data-cfemail`,
   `/cdn-cgi/l/email-protection#…`) are decoded deterministically first.

## Search results

A ranked result is only a candidate. Pre-classification: known directory host → DIRECTORY; social URL equal
to an already OFFICIALLY_LINKED profile → OFFICIALLY_LINKED; any other social URL → AMBIGUOUS (platform
pages are not fetched, so they cannot be verified); any other URL → crawl (homepage plus up to two
contact/about pages) → the classes above.

## Live validation (2026-10-03, Phase 4C)

| Candidate | v1 gate | v2 class | Deciding signal | Manual audit |
|---|---|---|---|---|
| spirendesign.no (920772099) | accept (org no.) | FIRST_PARTY | C1 org number in footer | correct |
| lyserom.no (921136501) | accept (org no.) | FIRST_PARTY | C1 org number in footer | correct |
| blioptimal.no (927818094) | accept (name+address) | FIRST_PARTY | C2 + own-domain mailbox | correct |
| annenvri.no (986757368) | accept (name+address) | FIRST_PARTY | C2 + own-domain mailbox | correct |
| arasenstadion.no (976744667) | **accept (wrong)** | **FAN_COMMUNITY** | "Fansite" in title (and contact delegated to `lsk@lsk.no`) | wrong owner |

Without the "Fansite" marker the same page is still rejected as THIRD_PARTY, because its only mailbox is
on another organisation's domain. Without that mailbox it falls to AMBIGUOUS (aboutness only). All three
variants are covered by tests (`tests/test_public_activity.py`).

On these 5 live candidates v2 keeps 4/4 correct and rejects the 1 wrong one. Five cases are a test, not
a precision estimate. Adopting v2 in the batch requires a larger adversarial set: place-named companies,
municipal and tourism pages, group sites listing subsidiaries, free-mail-only small firms.
