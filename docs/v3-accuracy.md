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

### 5. Final code (`dc96260`)

Replaying all four sets through `dc96260` publishes exactly the units measured in row 4: smoke100 + midsize40 109/109,
fresh60 104/104 and fresh60b 137/137, excluding websites. So rows 3 and 4 describe the release code. The later commits
changed only refresh labels, absence wording, history carry-forward, the viewer and the app, not what is published.

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

## Pre-release remediation pass (2026-11-01) — new independent evaluation

The full method and tables are in `docs/v3-remediation.md` (R3 §2–§4), and the artefacts in
`measurements/v3-remediation-2026-11-01/`. Rules were frozen at `7b8fc69` before the new evaluation sample was opened.

| Set (role) | Social precision | News precision | Careers-page precision |
|---|---|---|---|
| **eval120 (independent, scored once)** | 93.0% (40/43; CI 81.4–97.6) | **25.6% (10/39; CI 14.6–41.1)** | 100% (4/4; CI 51.0–100) |
| diag80 (diagnostic, tuned on) | 100% (31/31) | 97.1% (66/68) | 100% (4/4) |
| smoke100 + midsize40 + fresh60 (development, tuned on) | 100% (83/83) | 93.5% (86/92) | 100% (14/14) |
| fresh60b (consumed held-out; not independent for the remediation changes) | 100% (55/55) | 100% (52/52) | 100% (9/9) |

- **The 90% news target has not passed on independent data.** The independent news result is 25.6%.
- **Careers.** The 90% careers target cannot be established: the independent sample has only 4 decided careers pages,
  so the interval is 51–100%.
- **Job advertisements.** No sample in this pass had a decidable published job ad, so job-ad accuracy is not
  measured.
- **Social** independent precision is 93.0% (CI 81.4–97.6%), with retention 87.0%.

## V3.1 (2026-11-01/02) — news classification remediation, new independent evaluation eval200

Details are in `docs/v31-news-analysis.md` §6 (comparison of approaches) and §8 (independent evaluation). Artefacts
are in `measurements/v31-2026-11-01/`.

**Set roles.**
- eval120 is consumed: it was used to diagnose the 29 errors.
- fresh60b is consumed.
- smoke100, midsize40, fresh60 and diag80 are tuned.
- eval200 is new: drawn and captured through the baseline before V3.1 existed, opened only after V3.1 was frozen
  (`8223a37`), labelled once (blind to version, captured text visible) and scored once.

| eval200 (independent) | Baseline `ff3b515` | Candidate 2 `7b8fc69` | V3.1 `8223a37` |
|---|---|---|---|
| News precision (95% CI) | 70/192 = 36.5% (30.0–43.5) | 61/134 = 45.5% (37.3–54.0) | **46/81 = 56.8% (45.9–67.0)** |
| News retention (recall proxy) | — | 52/70 = 74.3% | 37/70 = 52.9% |
| Social precision | 73/75 = 97.3% (90.8–99.3) | 73/75 = 97.3% | 73/75 = 97.3% |
| Social retention | — | 69/73 = 94.5% | 69/73 = 94.5% |
| Careers-page precision | 7/12 = 58.3% | 4/4 (CI 51.0–100) | 4/4 (CI 51.0–100) |
| Job postings | none published | none | none |

The sample is 200 organisations. The census holds 308 labelled units (211 news, 82 social, 15 careers).

**Targets.**
- News ≥90%: **not met** (56.8%).
- Social ≥95%: met on this sample (97.3%; the lower CI bound is 90.8%).
- Careers pages: too few to establish (4 decided).
- Job ads: not validated; no labelled sample.

**Tuned sets, for comparison only (optimistic):** news 119/122 = 97.5%, retention 74.3%; fresh60b 30/30; eval120 7/11.
The gap between 97.5% on the tuned sets and 56.8% on eval200 is the main finding of this round. Development-set
precision is not evidence of independent precision.

### V3.1 freeze 2 (`0e4c426`) — eval200b, new and independent, scored once

The sample is 200 new organisations, captured through the baseline before the freeze and opened after it. The census
holds 448 labelled units. Labels are `assistant_blind`, with the captured text visible. Details are in
`docs/v31-news-analysis.md` §10.

| eval200b | Baseline | Candidate 2 `7b8fc69` | Freeze 1 `8223a37` | **Freeze 2 `0e4c426`** |
|---|---|---|---|---|
| News precision (95% CI) | 45.5% (40.1–51.1) | 60.6% (54.1–66.8) | 71.6% (63.9–78.3) | **105/131 = 80.2% (72.5–86.1)** |
| News retention (recall proxy) | — | 93.0% | 71.3% | **70.6% (101/143)** |
| Social precision | 92.3% | 100% (68/68) | 100% | **100% (68/68, 94.7–100)** |
| Careers-page precision | 61.5% | 7/7 | 7/7 | **7/7 (64.6–100)** |

**Targets.**
- News ≥90%: **not met** (80.2%).
- Social ≥95%: met on this sample.
- Careers: 7 decided, which is too few to establish a rate.
- Job ads: not validated; one job was published by the baseline only, and its label is unsure.

### V3.1 candidate 2 (`334a085`) — foreign namesakes, entity resolution only

- **No new sample was scored.** The correction was developed on the eval200 Logscom case, which is development data.
- On every captured set, `334a085` publishes exactly what `0e4c426` publishes, except LOGSCOM AS: its 2 profiles,
  both labelled incorrect, are withheld.
- So the eval200b figures above apply unchanged: news 80.2%, social 68/68.
- eval200 social becomes 73/73 decided. That is development data, so it is not evidence of independent precision.
- Details are in `docs/v31-release-report.md` §10 and `measurements/v31-2026-11-01/namesake/`.
