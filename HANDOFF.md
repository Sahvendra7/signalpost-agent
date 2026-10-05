# Handoff: read this first

This is where the work stands for whoever continues on another machine or account.

## Where things are

| Item | Value |
| --- | --- |
| Repository | `Sahvendra7/signalpost-agent` |
| Working branch | `claude/awesome-sagan-m2lppu` (everything below is pushed) |
| Last officially evaluated commit | `104c3c4`, tag `submission-candidate-1` |
| C12 score | 57.87/100 (recall 8.87/50, precision 29/30, synthesis 12/12, UX 8/8); qualification needs 65 |
| Revision 1 | Built and measured, **not submitted** |

## Revision 1 commits

| Commit | What it does |
| --- | --- |
| `a0cb079` | Core: social, dated news and jobs from verified sites become typed, evidence-contained claims |
| `83321ea` | **Separable policy decision:** `MANAGER_DESIGNATED`, the registry-designated site of a registered business manager (the BORI case) |
| `0093419`, `3c946d9`, `58fee4e` | Precision fixes found by the manual audits |
| `45c41ee` | Results docs and measurements |

## Read in this order

1. `docs/c12-gap-analysis.md`: why found information was not scoring.
2. `docs/revision-1-results.md`: measured results, the audit and the recommendation.
3. `docs/official-submission-checklist.md` and `docs/official-scoring-model.md`: contract and scoring.
4. The docs on deadline and streaming, refresh semantics, company summary, viewer, input and snapshot, identity
   and status, dependencies, and crawl safety and privacy (all in `docs/`).

## Standing rules, kept throughout

- No paid APIs, no Brave and no NAV.
- The LLM stays off.
- Never fetch LinkedIn, Facebook, Instagram, YouTube, X or TikTok.
- Never trust name-only identity, and never fabricate.
- A source outage is never a company change.
- Do not commit Builderr's sample data (only its hash).
- Never claim a score Builderr has not given.

## Setup

```bash
uv sync --locked
uv run --with pytest pytest -q   # expect 330 passed
```

## Open decisions and next steps

- Decide whether `83321ea` (`MANAGER_DESIGNATED`) goes into the submitted Revision 1.
- Decide when to submit Revision 1 to Builderr.
- The remaining recall bottleneck is website discovery. Most companies still have no discovered website, and
  Revision 1 deliberately did not touch discovery.
