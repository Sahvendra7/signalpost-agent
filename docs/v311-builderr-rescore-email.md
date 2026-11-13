# Rescore request — draft (send only after the owner approves and the branch is pushed)

**To:** Soham Sinha (Builderr)
**Subject:** Signalpost — revised commit for rescoring (wrong-company claims removed; verified news and job ads)

Hi Soham,

Thank you for the detailed feedback on our entry (rank 2/104, about 69/100, 11 of 86 checked claims belonging to
another company). We have prepared a revision that addresses both points. Please rescore this exact commit:

- Repository: https://github.com/Sahvendra7/signalpost-agent
- Branch: `revision/v3.1.1-builderr-rescore`
- Commit: `<RELEASE_COMMIT_SHA>` (code-identical to `38ff24c48e989a987529f4f7d6ca3fa107bce75d`)
- Command (unchanged):
  `uv sync --locked`
  `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>`

**1. Wrong-company claims**
- The two examples you gave (LØWEHJERTE DESIGN AS: `linkedin.com/company/squarespace/mycompany/verification/` and
  `facebook.com/squarespace`) came from the website builder's template `sameAs` data. These URLs are no longer published.
  Website-builder and platform accounts, platform admin or verification URLs, and group or parent accounts on a
  subsidiary's site are now held back, with the reason recorded. Structured data and link text cannot override this.
- A website run by a business manager, another company or the group is no longer presented as the entity's own website.
  It is marked `related_not_exact` and withheld. The registry link itself remains as a separate registry fact.

**2. Company news and job postings**
- News: we publish only individual, dated articles from the company's own site whose headline announces an event in the
  company's life (an acquisition, appointment, agreement, opening, award, anniversary, launch, certification or annual
  meeting) and that name the company. Parent and group stories on a subsidiary's site, guides, product pages and
  promotions are withheld. Application deadlines and "updated" stamps are never used as publication dates.
- Job ads: we publish only individual, currently open advertisements whose employer is this company. Ads hosted off
  the site (Finn, Jobbnorge, applicant-tracking systems) need the employer to be verified. Job boards listing other
  employers' vacancies are not treated as the company's careers page. Undated or expired ads are never published.

**Validation (our own; not a Builderr score)**
- On a new sample of 200 companies drawn after the rules were frozen (labelled by us), 134 of 138 decided published
  external claims (website, social profile, news, careers page) were correct (97.1%, 95% CI 92.8–98.9). 3 belonged to a
  related entity. The sample is small, so we do not claim the 95% threshold.
- 100-company smoke test: 100/100 completed in input order, 0 contract findings, 3,968 evidence hashes re-verified,
  refresh with no false changes, $0.
- Models: none (no LLM is used or loaded). External sources: the public Brønnøysund registry APIs and the companies'
  own websites only. No social-media platform is fetched. Licences and dependencies are unchanged. Operating cost: $0.

The full report is in `docs/v311-rescore-revision.md` in the repository.

Kind regards,
<name>
