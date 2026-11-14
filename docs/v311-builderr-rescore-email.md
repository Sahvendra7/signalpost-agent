# Rescore request — final draft (the owner reviews and sends it; Claude does not send it)

**To:** Soham Sinha (Builderr)
**Subject:** Signalpost — revised commit for rescoring (wrong-company claims removed; verified news and job ads)

Hi Soham,

Thank you for the detailed feedback on our entry (rank 2 of 104, about 69/100; of 86 checked claims, 75 were correct and
11 belonged to another company, 87%). We understand that qualification requires at least 95% correct claims and a
score of at least 65/100. We have prepared a revision that addresses both points you raised. Please rescore this exact
commit:

- Repository: https://github.com/Sahvendra7/signalpost-agent
- Branch: `revision/v3.1.1-builderr-rescore`
- Commit: `408f41523e9b7aa2ffc45c12656403f9949bcb2b`

`408f415` is a documentation-only commit on top of the validated release commit
`9d99cba61493e99664db16c78fd37e84408e4408`. Both have identical source code, tests, scripts and lock file. The last code
change is in `38ff24c48e989a987529f4f7d6ca3fa107bce75d`, and all of our validation ran on that code.

**How to run (Python 3.12+, uv)**

```
uv sync --locked
uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>
```

This is the same command as before. No API key, account or environment variable is needed.

**1. Wrong-company claims**

- Your two examples (LØWEHJERTE DESIGN AS: `linkedin.com/company/squarespace/mycompany/verification/` and
  `facebook.com/squarespace`) came from the website builder's template `sameAs` data. These URLs are no longer
  published. Website-builder and platform accounts, platform admin or verification URLs, and group or parent accounts on
  a subsidiary's site are now withheld, and the reason is recorded. These checks run first, so structured data
  (`sameAs`) and link text cannot override them. A company's own profiles are still published.
- A website run by a business manager, another company or the group is no longer presented as the entity's own website.
  It is marked `related_not_exact` and withheld. The registry link itself remains as a separate registry fact.
- We could reproduce only your two confirmed examples, because we do not have your sample. For the other 9, we measured
  the previous commit on a new sample and fixed the wrong-company patterns we found there: business-manager websites,
  group websites and accounts, and parent-company news on a subsidiary's site.

**2. Company news and job postings**

- News: we publish only individual, dated articles from the company's own site. The headline must announce an event in
  the company's life (an acquisition, appointment, agreement, opening, award, anniversary, launch, certification or
  annual meeting), and the article must name the company. Parent-company and supplier stories, guides, product pages and
  promotions are withheld. Application deadlines and feed "updated" dates are never used as publication dates.
- Job ads: we publish only individual, currently open advertisements where the employer is verified as this company.
  An ad hosted elsewhere (Finn, Jobbnorge, applicant-tracking systems) qualifies only if the employer is verified.
  A third-party job board listing other employers' vacancies is not treated as the company's careers page. Undated or
  expired ads are never published.
- We chose accuracy over volume, so news and job coverage is low. On our 200-company check below, 7 news items and no
  job ads were published. Most careers pages list positions without a date, and we do not publish undated ads.

**Our own validation (not a Builderr result)**

- New sample of 200 companies, drawn before the final code was run on it. It was labelled internally by the author of
  the rules and has not been reviewed independently. Of the 138 published external claims we could decide on (websites,
  social profiles, news, careers pages), 134 were correct: 97.1%, with a 95% confidence interval of 92.8–98.9%.
  **4 claims were incorrect, 3 of them belonging to a related entity**: two accounts of a school chain on one member
  school's site, and a general-meeting notice of a closely related entity with a similar name. The fourth was an article labelled as a careers page.
  A further 5 claims were unsure. If those count as wrong, the figure is 134/143 = 93.7%.
- These numbers come from our own small sample. They are not a Builderr score, and the confidence interval goes below
  95%. We therefore do not claim that the 95% threshold is met; only your evaluation can establish that. The sample was
  measured on code `7a88046`. The final code adds two careers-page and job-ad rules that can only withhold claims, and an offline
  replay shows it publishes the same claims on this sample.
- Full test suite: 570 passed and 193 subtests passed, in a fresh clone with `uv sync --locked`. 37 of these are new
  regression tests, including a replay of the LØWEHJERTE page.
- 100-company smoke test of the final code: 100/100 completed in input order with 0 contract findings. All 3,968
  evidence hashes were re-verified with 0 mismatches. No social-media host was contacted, and the cost was $0.
  A refresh run produced no false changes: there was one `unavailable` event, for a company whose e-mail domain could
  not be reached.

**Models, APIs, dependencies and cost**

- Models: none. Default execution is deterministic; no LLM is called, imported or needed.
- Gemini: not part of this release. No Gemini code is in this branch, and no API key is used.
- External sources: the public Brønnøysund registry APIs (NLOD 2.0) and the companies' own websites, with robots.txt
  honoured. No social-media platform is fetched, and there are no paid or keyed APIs.
- Dependencies: Python 3.12+ and the packages pinned in `uv.lock` (beautifulsoup4, extruct, lxml, pydantic, pypdf,
  tldextract 5.3.2, trafilatura and their dependencies). All are under permissive open-source licences (MIT, BSD,
  Apache-2.0, MPL-2.0 and similar); see `docs/dependencies.md`. These are unchanged from our previous submission.
- Expected cost: $0 in third-party charges. The run took about 0.9 seconds per company on the 100-company smoke test.

The full report, including the measurements and known limitations, is in `docs/v311-rescore-revision.md`. The labelled
sample and run records are in `measurements/v311-rescore-2026-11-14/`.

Thank you for the opportunity to resubmit.

Kind regards,
Sachin
