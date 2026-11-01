# V3 pre-release remediation pass (2026-11-01)

Baseline: `v3-candidate-1` (local tag on `4549f3a`; code `dc96260`), unchanged and reproducible.

## R1, R2 — ASAK AS and ASHTEAD TECHNOLOGY AS (social)

**Reproduced** from the captured fresh60 bytes, which are now the fixtures `tests/fixtures/v3/961592097`,
`980281310` and `995284766`. fresh60 has been a development set since the first held-out evaluation.

| Company | Published at `dc96260` | Cause |
|---|---|---|
| ASAK AS (961592097) | `facebook.com/asakmiljostein`, `instagram.com/asak_miljostein` | The handle is "asak" plus "miljøstein" (`EXTENDS`), accepted on asak.no, which is named after the company. asak.no is shared with ASAK MILJØSTEIN AS (980281310) and itself writes "Asak Miljøstein AS". |
| ASHTEAD TECHNOLOGY AS (995284766) | `linkedin.com/company/ashtead-technology` | The registry website is a page of the global group's `ashtead-technology.com` (operator `section`). An exact-name handle was accepted on shared sites, but the group bears the same name. |

**Two general rules** in `attribution/social.py`, fed by `site_facts.extract_site_facts`:

1. `handle_names_other_company_on_site`.
   - A `BRAND` or `EXTENDS` handle is held when it spells, exactly, a company name that the website itself writes with a
     legal form ("Asak Miljøstein AS"), and that name is not the target's. `names.named_entities` reads such names
     from the captured pages.
   - The other company keeps its profiles: ASAK MILJØSTEIN AS's are `handle_exact`.
2. `group_name_handle_on_{section|group_or_brand}_site`.
   - On a site run by a larger organisation (`section` or `group_or_brand`) whose registered domain is named exactly
     like the company, a bare exact-name handle (no legal form, no Norway marker) is held: it is the organisation's
     account.
   - `biomar-norge` and `bergknapp-as`-style handles are unaffected.
   - Platform-hosted sites (`platform`) are excluded, because a tenant's exact-name handle there is its own.

**Effect on every published social unit in the four existing sets** (replay, `dc96260` against the working tree):

| Set | Lost | Gained |
|---|---|---|
| fresh60 | 2 ASAK profiles, 1 Ashtead LinkedIn (all labelled incorrect) | 0 |
| midsize40 | `instagram.com/beredtinkludering` | 0 |
| smoke100 | — | — |
| fresh60b (consumed held-out; measured only, not tuned on) | — | — |

**Label correction.** The Beredt profile had been labelled "correct, own sub-brand". It belongs to BEREDT INKLUDERING
AS (934470222), a separately registered company that beredt.no itself calls one of "to selskaper" (two companies). The
dev-audit label is corrected, with this evidence, in
`measurements/v3-remediation-2026-11-01/label-corrections.csv`. The control in
`test_v3_regressions.py::SocialAttribution::test_controls_keep_their_profiles` is updated to match.

**Tests:**
- `test_v3_regressions.py::SocialAttribution::test_asak_does_not_take_the_profiles_of_asak_miljostein` — ASAK held,
  ASAK MILJØSTEIN keeps both;
- `test_v3_regressions.py::SocialAttribution::test_ashtead_norwegian_as_does_not_take_the_global_linkedin`.
