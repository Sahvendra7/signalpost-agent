# Revision email for V3.1.2 — draft (the owner reviews and sends it; Claude does not send it)

Use this **only if** the owner decides to submit `<V312_COMMIT_SHA>` (see `docs/v312-final-optimization.md` §9).
Replace `<V312_COMMIT_SHA>` with the full SHA of the commit that is pushed (the documentation commit on top of code
`95a5464073054b6717b963f3839541590ecdba52`), and delete the paragraph in brackets that does not apply.

**To:** submit@builderr.ai (Soham Sinha)
**Subject:** Signalpost — revised commit (Sachin): wrong-company fixes, verified websites, question on UX grading

Hi Soham,

Please use this exact commit for our next frozen version:

- Agent name: Signalpost (Sachin)
- Repository: https://github.com/Sahvendra7/signalpost-agent
- Branch: `final/v3.1.2-optimization`
- Commit: `<V312_COMMIT_SHA>` (documentation only on top of code `95a5464073054b6717b963f3839541590ecdba52`)

[If the V3.1.1 commit `408f415` was already sent: This replaces `408f415`, and it contains everything in it.]
[If it was not sent: This is our answer to your feedback on `ff3b515` (75 of 86 claims correct, 11 belonging to another company).]

**How to run (Python 3.12+, uv) — unchanged**

```
uv sync --locked
uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>
```

No API key, account or environment variable is needed.

**What changed since `ff3b515`**

- Wrong-company claims: website-builder and platform accounts (your LØWEHJERTE examples), group and parent accounts,
  and websites run by a business manager, another company or the group are withheld and marked `related_not_exact`.
  New in this commit: a foreign-registered company whose registry website is its Norwegian namesake's is held the
  same way, and a registrar's "parked", expired-domain, web-host or error page is never published as a website.
- News and job ads: only dated announcements that name the company, and open advertisements with a verified employer.
  Coverage of both is low; we chose accuracy.
- Websites: a site the registry lists without a scheme is read over http when https does not answer, and a few more
  registry-listed sites are verified (the domain is the legal name, or a sole proprietor's registered trade or
  personal name), each with guards against related companies.
- Every profile with a verified website now opens with a short cited summary.

**Our own check (not a Builderr result)**

- A new sample of 300 companies, drawn after the code was frozen. Of 192 published external claims we could decide on,
  190 were correct: 99.0%, 95% confidence interval 96.3–99.7%. One claim belonged to a related company (fixed in this
  commit after the check); one was a notice that is not company news. 5 more were unsure; counting them as wrong gives
  190/197 = 96.4%.
- The labels are ours (the author of the rules) and were not reviewed independently. We do not claim the 95% bar is
  met; only your check can establish that.
- 594 tests pass in a fresh clone with `uv sync --locked`.
- 100-company smoke test: 100/100 completed in input order, 0 contract findings, 3,969 evidence hashes re-verified
  with 0 mismatches, no social-media host contacted, $0, 100 seconds. A refresh run produced one `unavailable` event
  and no false change. Report and viewer: `measurements/v312-final-2026-11-14/runs-final-95a5464/`.

**Models, APIs, licences, cost**

- Models: none. No LLM is called or imported. No Gemini code is in this branch.
- Sources: the public Brønnøysund registry APIs (NLOD 2.0) and companies' own websites, robots.txt honoured. No
  social-media platform is fetched. No paid or keyed API.
- Dependencies: unchanged; pinned in `uv.lock`, permissive licences (`docs/dependencies.md`).
- Expected cost per official run: $0. About 1–2 seconds per company.

**One question on UX**

Every run writes a self-contained page next to the envelopes (`out/envelopes.viewer.html`): search, side-by-side
comparison of up to four companies, and the source and retrieval date of every fact, on laptop and phone. Our UX
score was 0.60. Could you tell us what the UX grade is taken from (the run output, the repository, or a hosted link)?
If a hosted link is needed, we can provide one.

Full report: `docs/v312-final-optimization.md`.

Kind regards,
Sachin
