# Handoff: read this first

This is where the work stands for whoever continues on another machine or account.

## Where things are

| Item | Value |
| --- | --- |
| Repository | `Sahvendra7/signalpost-agent` |
| Working branch | `claude/awesome-sagan-m2lppu` (everything below is pushed) |
| GitHub default branch | `main` = `5575d0c`, an older tree **without** the summary, the viewer and Revision 1. A runner that clones the URL without a commit gets it (`docs/c300-revision.md` §A1). |
| V1 | `104c3c4`, tag `submission-candidate-1`. C12: 57.87/100 (recall 8.87, precision 29, synthesis 12, UX 8) |
| Revision 1 | `05d7566` (code `a5e06ce`), submitted by the owner. Builderr C300 directional row (2026-10-17): 56.85/100 (recall 26.18, precision 28.27, synthesis 2.40, UX 0). Which tree Builderr processed is not determinable from the available metadata. |
| C300 revision candidate | Code `6487205` (code commits `7492f32`, `6487205`); the docs/measurements commit on top is code-identical. Not submitted, not scored. See `docs/c300-revision.md`. |
| **Final release candidate** | Branch `claude/c300-refresh-fix`. Code `71fa494` (C300 `6487205` + refresh fix `8fba893` + race fix); the docs commit on top is code-identical. **Not submitted, not scored.** See `docs/c300-refresh-fix.md` §0 and `docs/final-submission-manifest.md`. Superseded: `7879be3` (code `8fba893`). |

## Read in this order

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
- Do not commit Builderr's sample data (only its hash).
- Never claim a score Builderr has not given.

## Setup

```bash
uv sync --locked
uv run --with pytest pytest -q   # expect 356 passed, 91 subtests passed
```

## Open decisions and next steps (owner)

- Decide whether to submit the C300 revision before October 18. Name the exact commit in the submission, and either
  make the submission branch the GitHub default branch or state the commit explicitly, so that `main` (`5575d0c`) is
  not what gets run.
- The remaining recall bottleneck is website discovery. Most companies still have no discovered website, and no
  revision so far has touched discovery.
