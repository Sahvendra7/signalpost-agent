# Handoff: read this first

This is where the work stands for whoever continues on another machine or account.

## Where things are

| Item | Value |
| --- | --- |
| Repository | `Sahvendra7/signalpost-agent` |
| Working branch | `claude/awesome-sagan-m2lppu`: the V3 work, branched from `ff3b515`. **Local commits; not pushed until the owner has reviewed them.** |
| GitHub default branch | `main` = `5575d0c`, an older tree **without** the summary, the viewer and Revision 1. A runner that clones the URL without a commit gets it (`docs/c300-revision.md` §A1). |
| V1 | `104c3c4`, tag `submission-candidate-1`. C12: 57.87/100 (recall 8.87, precision 29, synthesis 12, UX 8) |
| Revision 1 | `05d7566` (code `a5e06ce`), submitted by the owner. Builderr C300 directional row (2026-10-17): 56.85/100 (recall 26.18, precision 28.27, synthesis 2.40, UX 0). Which tree Builderr processed is not determinable from the available metadata. |
| C300 revision candidate | Code `6487205` (code commits `7492f32`, `6487205`); the docs/measurements commit on top is code-identical. Not submitted, not scored. See `docs/c300-revision.md`. |
| Previously submitted | `ff3b515` (branch `claude/c300-refresh-fix`) — the V3 baseline. |
| **V3.1 candidate 2 (recommended)** | Tag `v3.1-candidate-2` (local), code `334a085`: candidate 1 plus the foreign-namesake entity correction (LOGSCOM AS / Logscom AB; `docs/v31-release-report.md` §10). The news rules are unchanged. Not pushed, not submitted, not scored. |
| V3.1 candidate 1 | Tag `v3.1-candidate-1` (local), code `0e4c426`, after the news accuracy remediation (`docs/v31-release-report.md`). Not pushed, not submitted, not scored. Independent news precision 80.2% (eval200b): the 90% target is not met. Social 100%. |
| V3 candidate 2 | Code `7b8fc69` plus documentation and measurements, after the pre-release remediation pass (`docs/v3-remediation.md`). Not pushed, not submitted, not scored. Independent news precision 25.6%: the target is not met. |
| V3 candidate 1 | Branch `claude/awesome-sagan-m2lppu`, code `730ccfe` plus documentation and measurements. **Not submitted, not scored.** See `docs/v3-changelog.md`, `docs/v3-accuracy.md` and the V3 section of `docs/final-submission-manifest.md`. |
| Earlier release candidate | Branch `claude/c300-refresh-fix`. Code `71fa494` (C300 `6487205` + refresh fix `8fba893` + race fix); the docs commit on top is code-identical. **Not submitted, not scored.** See `docs/c300-refresh-fix.md` §0 and `docs/final-submission-manifest.md`. Superseded: `7879be3` (code `8fba893`). |

## Read in this order

0. V3.1: `docs/v31-release-report.md` (outcome, all measurements, the recommended commit), then
   `docs/v31-news-analysis.md` (the 29-error analysis, the comparison of approaches, both independent evaluations).
   V3:
   - `docs/superpowers/specs/2026-11-01-signalpost-v3-design.md` (design review and final design);
   - `docs/v3-changelog.md` (every behaviour change);
   - `docs/v3-accuracy.md` (measurement, including the failed held-out gates);
   - `docs/search-app.md`.
1. `docs/c300-refresh-fix.md`: the refresh fix ported onto C300, its validation, and the root causes of the
   intermittent test failures.
2. `docs/c300-revision.md`: C300 diagnosis (synthesis, UX, the WordPress/LinkedIn case), the fixes, validation and
   release check.
3. `docs/revision-1-final.md`: Revision 1 (exact social URLs, dated news, jobs, manager rule) and its audit.
4. `docs/c12-gap-analysis.md`, `docs/official-submission-checklist.md` and `docs/official-scoring-model.md`.

## Standing rules, kept throughout

- No paid APIs, no Brave and no NAV.
- The LLM stays off.
- Never fetch LinkedIn, Facebook, Instagram, YouTube, X or TikTok.
- Never trust name-only identity, and never fabricate.
- A business manager's own content is never the managed entity's, unless the item names that entity.
- A hosting platform's own pages and profiles are never its tenant's (`site_facts.in_site_scope`).
- A source outage is never a company change; a missing number is unknown, never zero.
- A sister, group or brand company's profiles, news or jobs are never attributed without evidence (V3 `attribution/`).
- Local measurements are labelled by who labelled them, and are never presented as Builderr scores.
- Do not commit Builderr's sample data (only its hash).
- Never claim a score Builderr has not given.

## Setup

```bash
uv sync --locked
uv run --with pytest pytest -q   # V3.1 candidate 1: expect 526 passed, 172 subtests passed
uv run python scripts/serve.py --data-dir out/app   # local search app (docs/search-app.md)
```

## Open decisions and next steps (owner)

- V3: review the branch, then decide whether to push it and submit it. Name the exact commit in the submission;
  `main` is still the older `5575d0c`. The V3 news held-out gate failed once (85.0% against ≥90%); see
  `docs/v3-accuracy.md` before deciding.
- Optionally re-label the V3 audit yourself (`scripts/audit_kit.py`, `--labeller-kind owner`). The current labels are
  `assistant_blind`.

- Decide whether to submit the C300 revision before October 18. Name the exact commit in the submission, and either
  make the submission branch the GitHub default branch or state the commit explicitly, so that `main` (`5575d0c`) is
  not what gets run.
- The remaining recall bottleneck is website discovery. Most companies still have no discovered website, and no
  revision so far has touched discovery.
