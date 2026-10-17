# Handoff: read this first

This is where the work stands for whoever continues on another machine or account.

## Where things are

| Item | Value |
| --- | --- |
| Repository | `Sahvendra7/signalpost-agent` |
| Working branch | `claude/awesome-sagan-m2lppu` (everything below is pushed) |
| Last officially evaluated commit | V1 `104c3c4`, tag `submission-candidate-1` |
| C12 score (V1 only) | 57.87/100 (recall 8.87/50, precision 29/30, synthesis 12/12, UX 8/8); qualification needs 65 |
| **Revision 1 candidate** | Code `a5e06ce`; the docs commit on top is code-identical. Built, audited and measured. **Not submitted, not scored.** |

## Revision 1 commits

| Commit | What it does |
| --- | --- |
| `a0cb079` | Core: social, dated news and jobs from verified sites become typed, evidence-contained claims |
| `83321ea` | `MANAGER_DESIGNATED`: the registry-designated site of a registered business manager (the BORI case) |
| `0093419`, `3c946d9`, `58fee4e` | Precision fixes from the first manual audits |
| `45c41ee` | First results docs (superseded) |
| `0f24dc3`, `a459120` | Manager rule narrowed: website association kept; manager news only when an item names the entity |
| `051f2d3`, `a5e06ce` | Precision fixes from the final audits (shared-section confinement, date stamps, one article = one claim, archive links, news archives are not careers pages, article page URL) |

## Read in this order

1. `docs/revision-1-final.md`: final candidate, manager-rule decision, audit, same-day comparison, submission
   check and recommendation.
2. `docs/c12-gap-analysis.md`: why found information was not scoring.
3. `docs/official-submission-checklist.md` and `docs/official-scoring-model.md`: contract and scoring.

## Standing rules, kept throughout

- No paid APIs, no Brave and no NAV.
- The LLM stays off.
- Never fetch LinkedIn, Facebook, Instagram, YouTube, X or TikTok.
- Never trust name-only identity, and never fabricate.
- A business manager's own content is never the managed entity's, unless the item names that entity.
- A source outage is never a company change.
- Do not commit Builderr's sample data (only its hash).
- Never claim a score Builderr has not given.

## Setup

```bash
uv sync --locked
uv run --with pytest pytest -q   # expect 339 passed
```

## Open decisions and next steps

- Decide whether and when to submit Revision 1 (code `a5e06ce`) to Builderr. Nothing has been submitted.
- The remaining recall bottleneck is website discovery. Most companies still have no discovered website, and
  Revision 1 deliberately did not touch discovery.
