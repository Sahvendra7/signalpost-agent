# V3 behaviour-change log

Every deliberate change of published behaviour relative to the baseline `ff3b515` is listed here. Each entry names
the rule, the reason (the defect it fixes) and any earlier test assertion it replaces. See the design in
`docs/superpowers/specs/2026-11-01-signalpost-v3-design.md`.

## Phase 0 — groundwork (no change to published facts)

- **Every envelope carries `run.code_version`, and so does the run report.** Fields: `source_sha256`,
  `package_version`, `git_commit`, `git_dirty`. The field is additive. Envelopes without it still validate. A
  malformed value produces the contract finding `invalid_code_version`.
- **New tooling.** `scripts/replay_run.py` with `norway_company_agent/replay.py` replays captured runs. The audit kit
  is `scripts/audit_kit.py` with `norway_company_agent/audit.py`. Regression fixtures for 16 companies are in
  `tests/fixtures/v3/`.

## Phase 1 — entity resolution and social attribution

New package `src/norway_company_agent/attribution/`:
- `names.py` — handle relations;
- `operator.py` — who runs the site;
- `social.py` — profile decisions.

**Site operator** (design §B5), decided from pages already captured, with no new request:
- **`other_entity`:** another valid org number is stated in an imprint, and the company's own number appears nowhere.
  Effect: the website claim stays, as the registry lists it, and gains `site_role: operated_by_other_company` and
  `operated_by`. Profiles, the careers page and vacancies are held; `job_posting` becomes `not_applicable`, with the
  reason.
  - Fixes: TYIN ALPINT AS (983181732) received Tyin Filefjell AS's LinkedIn, Facebook and Instagram.
- **`group_or_brand`:** any of the following.
  - The registry website redirects to another domain (BARTEC AS: bartec-technor.no → bartec.com).
  - The domain shares no distinctive token with the legal name, and the name is absent from the site.
  - A "BRAND + own town" legal name in a corporate group (`erIKonsern`), with the full name absent from the homepage.
  - The site's taxonomy names two or more sibling units ("Betonmast Trøndelag", … for BETONMAST OSLO AS).

  Effect: `site_role: group_or_brand_site`; only exact legal-name handles are attributed; the careers page and
  vacancies are held.
- **Own org number stated anywhere on the site → `self`.** This guards against a holding company named in the footer.
- The **business-manager** (Revision 1) and **hosting-platform / section** (C300) rules are unchanged; they are now
  reported as operator kinds.

**Social decisions** (design §B4):
- A profile is accepted when its handle **is the legal name** (EXACT), optionally with neutral additions such as a
  legal form, "norge", the company's own town or a short number (EXACT_NEUTRAL).
- A **brand** (leading name tokens) or an **extended** handle is accepted only on a self-run site whose own domain is
  named after the company. An extended handle is also accepted when the company's own structured data names the
  company and lists the profile.
- Handles naming **another entity** are held: "group", "holding", "global" and similar words, or a different name
  ending in a legal form (`tyin-filefjell-as`, `bdt-viken-revisjon-as`). So are unrelated handles.
- **The domain-name rule and JSON-LD `sameAs` no longer accept a profile on their own.**
- Held profiles keep their reason in `ambiguous_profiles` and in the rejection counts, e.g. `social:handle_names_other_entity`.
- Published profiles carry `attribution: {code, basis}`.

**Tests replaced:**
- `test_revision1.py::AuditRegressions::test_domain_name_must_begin_or_end_the_handle`: `handballnorge` for
  BALLSPORT DRIFT AS is now held. A site named after the company still corroborates its own extended handles.
- `test_revision1.py::SocialRules::test_jsonld_sameas_of_own_organization_is_accepted`: `fd-group` listed in
  `sameAs` for Fjell Data AS is now held. A `sameAs` handle that carries the name is still accepted.

**Fixtures now passing:**
- Tyin: 3 → 0 profiles.
- Bergknapp: Grasrota 3 → 0; its own 3 kept.
- Bartec: 4 → 0.
- BioMar: `@BioMarGroup` held; Norway profiles kept.
- BDT Viken: `bdt-viken-revisjon-as` held.
- Controls unchanged: Grønsand, Birralee, Beredt, Crux, Bjelland, Bergen Rørteknikk, BK Bygg, Bemex.
