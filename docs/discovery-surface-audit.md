# Discovery-surface audit (zero-cost V2, Phase 1)

Question: which already-available, permitted fields can point to a company-owned domain? Raw responses
were inventoried for the fixed 100-company sample on 2026-10-03: Brreg `/enheter/{org}`,
`/underenheter?overordnetEnhet=`, `/enheter/{org}/roller`. Every string resembling a URL or e-mail address
was recorded.

## Fields found

| Field | Companies with value | Used by V1 | Used by V2 | Trust |
|---|---|---|---|---|
| `enheter.hjemmeside` | 17 | yes (registry gate v1) | yes, plus a v2 rescue when v1 is ambiguous | official pointer; still needs a site gate |
| `enheter.epostadresse` | 29 (24 non-free-mail domains) | no | **yes** (candidate domain; registry e-mail domain also a C2 control signal) | official pointer, but often an accountant's or a group's mailbox, so candidate only |
| `underenheter[].hjemmeside` | 12 | no (dropped by the normaliser) | **yes** | official pointer for a branch; may be a chain or brand site |
| `underenheter[].epostadresse` | 22 (18 non-free-mail domains) | no | **yes** | as entity e-mail |
| `enheter.telefon` / `mobil` | present for many | no | corroboration only | third parties copy phone numbers (arasenstadion.no) |
| `erIKonsern`, roles with entity holders | some | group structure only | not used for domains | a parent's site is not the company's site |
| Regnskapsregisteret accounts / filing metadata | 99 | yes | no URLs present | none |
| Annual-account copies | 100 | (rejected: image-only, slow) | no | none |
| Trade names / aliases | **not in open data** | — | — | — |

Free-mail and ISP domains are dropped (`site_identity.FREE_MAIL`). The audit found two the original
list missed: `verizon.net` and `gmx.de`.

## Yield of official pointers on the fixed sample

- Companies without a verified site (gate v1 + Phase 4C): 88. Of these, **19** have at least one
  official pointer: 9 with a registry-listed URL that v1 did not verify, and 10 more through e-mail domains only.
- No candidate domain is shared by two companies in the sample, so the per-run domain cache matters
  mainly at larger batch sizes.
- The other 69 companies have no official pointer at all. Only the `<legal-name>.no` guesses, behind
  DNS resolution and the strict gate, can reach them without a search engine.

## Not used, and why

- Search engines and paid APIs: excluded by the owner ($0 search spend).
- Directory sites (proff.no, purehelp.no, 1881.no, gulesider.no…): third-party copies of registry data;
  `DIRECTORY` class.
- Platform pages (LinkedIn, Facebook, Instagram, YouTube): not fetched (Builderr source policy, robots).
  Profiles come only from verified-site links.
- Parent or group websites from role/group relationships: these are the parent's identity, not the company's.
