# V3 accuracy measurement (Phase 4)

**These are local engineering measurements, not Builderr scores.** The labels were made by the assistant that wrote
the rules. They were made **blind to which code version published each item** (both versions' items were pooled,
de-duplicated and shuffled, with the version hidden), each with a short reason. They are not owner-verified. To
re-label any subset and re-score:

```bash
uv run python scripts/audit_kit.py score --labels <items.labelled.csv> --arms <arms.json> --baseline base --candidate v3 \
  --labeller "<name>" --labeller-kind owner --out <out>
```

Artefacts are in `measurements/v3-2026-11-01/`:
- `inputs/` — input sets with `SHA256SUMS`;
- `replay/` — envelopes and reports for both versions on every set;
- `audits/` — labelled CSVs, blind checklists, version maps and results.

## Method

1. **Baseline capture.** `ff3b515` (a pristine `git archive`) ran live with `--snapshot-dir` on 2026-11-01 before any
   V3 code existed, for `smoke100`, `midsize40` and `fresh60`. `fresh60b` was captured later from the same baseline
   tree, before it was inspected.
2. **Replay.** `scripts/replay_run.py` re-runs each captured run through a code tree with no network. Both versions see
   the same bytes, so a difference between them is caused by code, not by the web changing.
   - Replay fidelity (live baseline versus replayed baseline, audited units): midsize40 100%, smoke100 98.4%, fresh60
     100%, fresh60b 100%.
   - The single smoke100 difference is a careers-page link whose page the live run never captured.
3. **Units.** One unit is one published `(organisation, field, key)` for `social_profile`, `news_item`, `job_posting`
   and `careers_page`. `official_website` units are listed but were **not labelled**. The website set is identical in
   both versions (site discovery is untouched), and no website check was performed for this audit.
4. **Census.** Every unit from either version was labelled. There was no sampling, so no weighting was needed.
5. **Labelling rubric.**
   - **social** — the profile belongs to this legal entity.
   - **news** — a dated article about this company or its own activities, correctly dated as far as the page shows.
     Product, service or project pages, listings, default posts, journalism by publishers and evergreen advice do not
     count.
   - **job** — a single advertisement for a position at this company, open or recently posted as stated.
   - **careers** — this company's page about working there.
6. **Metrics.**
   - Precision = correct ÷ (correct + incorrect), with a Wilson 95% interval. "Unsure" is excluded and reported.
   - **Retention** = correct baseline units still published by V3 ÷ correct baseline units. This is the recall proxy:
     true recall needs ground truth that does not exist here.
   - "Gained" counts correct units only V3 publishes.

## Results in chronological order (each as it happened)

### 1. Development sets, after phases 1–3 and the dev fixes (rules frozen at `ca34ef5`)

midsize40 + smoke100. V3 precision: social 100% (34), news 100% (65 correct, 4 unsure), careers 100% (6). Retention:
social 100%, news 100%, careers 100%.

### 2. First held-out evaluation, fresh60, once (rules frozen at `ca34ef5`) — gates FAILED

| Category | Base precision | V3 precision | V3 retention |
|---|---|---|---|
| Social | 93.0% | 92.1% | **62.3%** |
| News | 19.6% | **19.8%** | 80.0% |
| Careers | 50.0% | 100% (n=7) | 75.0% |

Causes:
- **Social retention:**
  - legal names that start with "AS";
  - newspaper brand handles equal to the site's own domain name;
  - a top-level-domain change taken as a group redirect;
  - a dealer list read as an imprint.
- **News precision, both versions:** 30% of the companies were **newspapers**, whose articles are journalism, not news
  about the company. Others published **evergreen advice** (cleaning guides, accounting tips, coffee recipes).

The rules were fixed (`6efd3cd`, logged in `docs/v3-changelog.md`). fresh60 then became a development set.

### 3. Second held-out evaluation, fresh60b, once (rules frozen at `6efd3cd`)

| Category | Base precision | V3 precision (95% CI) | V3 retention | Gate |
|---|---|---|---|---|
| Social | 83.8% | **100%** (50/50; 92.9–100%) | 87.7% | **passed** (≥95%, ≥85%) |
| News | 73.2% | **85.0%** (73.9–91.9%) | 98.1% | **failed** (<90%) |
| Careers | 66.7% | 88.9% (n=9) | 80.0% | **failed** (marginal; small n) |
| Jobs | 1 published, incorrect | 0 published | — | — |

V3 introduced **0 new errors** in any category.

The residual V3 news errors are:
- seven "Prosjekt: …" project descriptions on one site;
- two WordPress theme demo posts created in the same second.

The lost correct units come from three bugs: URL-encoded ø in handles, a single-letter initial in a legal name, and a
municipal careers path under `/tjenester/`.

### 4. After the post-held-out fixes (`b5199fe`) — development re-check on all four sets (no third held-out set)

Pooled over smoke100, midsize40, fresh60 and fresh60b; 564 labelled units:

| Category | Base precision | V3 precision (95% CI) | Retention | Errors removed | Errors introduced |
|---|---|---|---|---|---|
| Social | 86.1% (n=165) | **97.9%** (94.0–99.3%) | 95.8% | 20 | 0 |
| News | 44.2% (n=292) | **95.1%** (90.2–97.6%) | 98.5% | 156 | 0 |
| Careers | 60.0% (n=40) | **95.8%** (79.8–99.3%) | 95.8% | 15 | 0 |
| Jobs | 0 of 1 decided | none published | — | 1 | 0 |

These numbers are measured on sets the rules were (partly) tuned on. **They are not a held-out result.** The
held-out result for the final rules is row 3, measured on the earlier freeze.

### Remaining known errors (V3, all sets)

- **Social:**
  - **ASAK AS** publishes the profiles of **ASAK MILJØSTEIN AS**, a separate registered entity. The handle starts with
    the company's own name and domain; telling them apart needs a registry lookup, which is not implemented.
  - **ASHTEAD TECHNOLOGY AS** publishes the global group's LinkedIn, whose name is identical to the Norwegian AS's.
- **News:** advice posts without an advice-like title (three accounting posts), and one post dated a year after its
  content.

### Performance (replay, same machine, same bytes)

| Set | Base runtime | V3 runtime | Requests (base / V3) | Contract validation |
|---|---|---|---|---|
| midsize40 | 35.7 s | 22.2 s | 452 / 459 | passed / passed |
| smoke100 | 11.5 s | 10.0 s | 895 / 896 | passed / passed |
| fresh60 | 61.0 s | 54.8 s | 617 / 616 | passed / passed |
| fresh60b | 68.0 s | 63.7 s | 623 / 622 | passed / passed |

Request counts differ by at most 7, because careers-page link selection is stricter. Third-party cost is $0 in every
run.

### Jobs

Published job advertisements are rare in every set: the baseline published one in 300 companies, and it was wrong. So
job precision cannot be measured meaningfully from these samples. Job behaviour is pinned by synthetic tests instead
(`tests/test_v3_jobs.py`): expired, current, other employer, recruiter, news archive and undated.
