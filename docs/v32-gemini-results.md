# V3.2 research: Gemini for Signalpost — results

Branch `experiment/v3.2-gemini` (local, not pushed), based on `139e23c` (`v3.1-candidate-2`, code `334a085`).
Companion documents: `docs/v32-gemini-api-report.md` (API, cost, privacy, security) and
`docs/v32-llm-architecture.md` (architecture and integration design). All labels are `assistant_blind`.

## 0. Bottom line

1. **On an independent sample, a deterministic + Gemini hybrid is clearly better than V3.1 on both precision and
   coverage, but it does not reach the 90% target.** On evalg250 (250 new companies, 338 labelled news units, scored
   once), the pre-registered primary configuration (prompt P2 evidence-first, `gemini-3.1-flash-lite`):

   | | Precision (Wilson 95%) | Correct units published | V3.1 errors removed |
   |---|---|---|---|
   | V3.1 | 66/143 = 46.2% (38.2–54.3) | 66/140 | — |
   | Experiment C, hybrid | **117/152 = 77.0% (69.7–83.0)** | **117/140** | 45/77, adding 3 |
   | Experiment A, filter | 60/92 = 65.2% (55.0–74.2) | 60/140 | 45/77, keeping 60/66 of V3.1's correct units |

   Company-clustered intervals are wide (C: 50.0–97.3%), and two labelling judgment calls move C between 61.8% and
   92.9%. The improvement over V3.1 holds under every variant (§5.2). The second model, `gemini-3.5-flash-lite`,
   gives practically the same result (C: 75.8%).
2. **One failure mode dominates what remains:** 26 of the hybrid's 35 errors are one company. VALMET AS, a Norwegian
   subsidiary, has the Finnish parent group's global site as its verified website, and Gemini accepted group releases
   as the subsidiary's news. Two things in our own system set this up: the deterministic identity check accepted
   valmet.com on a single name token, and the packet's `known_aliases` included the bare brand "Valmet". Excluding
   that company (a sensitivity check, not the headline), C reaches 117/126 = 92.9%.
3. **Gemini is excellent at content type, weak at legal-entity boundaries under a shared brand.** In the hybrid it
   removed every advice, explainer, listing and job-ad error (66/66, 9/9, 5/5) but only 13/43 other-entity errors.
4. **The deterministic release does not hold its earlier precision on new data**: 46.2% on evalg250 against 80.2% on
   eval200b (58.4% without Valmet). That is an independent measurement of `334a085`, whatever is decided about LLMs.
5. **Cost and operations.**
   * Actual spend $0 (free tier).
   * Paid-tier equivalent: ≈$0.10 per 100 companies for the hybrid; ≈$0.06 for the filter.
   * Median latency 1.6 s; 0 failures after one retry pass (6% transient 503s/timeouts on the first pass).
   * 535/536 quotes verified in the captured text.
6. **Recommendation:** LLM assistance is worth integrating into a *future* release as an opt-in hybrid (§9), but not
   now and not in the competition release. First: fix the entity contract, re-measure on a new independent sample
   (evalg250 is now consumed), have the owner re-label part of it, and move to the paid tier.

## 1. Release protection

* Working tree clean at start; `139e23c` (docs) is code-identical to `334a085` (`git diff 334a085 139e23c -- src tests
  scripts pyproject.toml uv.lock` is empty).
* The tag `v3.1-candidate-2` was a *local* tag of the previous machine and does not exist in this fresh clone or on
  the remote (only `submission-candidate-1`). It was **not** recreated. The release branch was not modified.
* Experimental branch `experiment/v3.2-gemini` created from `139e23c`; nothing pushed.
* No release source file changed: `git diff 139e23c HEAD -- src tests scripts` only adds new files.
* The release run path never imports the new code (tested).
* Tests: **552 passed, 175 subtests** (533 release + 19 new).

## 2. Data and method

| Set | Role | Units | How |
|---|---|---|---|
| eval200, eval200b | diagnostic only (used in V3.1 tuning) | 211 / 352 news units | existing `assistant_blind` labels; article pages re-captured 2026-11-04 |
| **evalg250** | **independent final evaluation (now consumed)** | 338 news units, 250 organisations | drawn 2026-11-04 (seed 20261104) from 110,821 eligible Brreg entities (registered website, not bankrupt/liquidating), excluding all 10,055 organisation numbers found anywhere in the repository; drawn **before any prompt existed** |

evalg250 procedure (as in V3.1):

1. Captured live through the permissive baseline `ff3b515`; snapshots kept.
2. Replayed through a **clean worktree of `334a085`**. A runtime hook logged every withheld candidate and its
   reason; release code was not modified.
3. Census of every news unit either arm published.
4. Article pages captured deterministically: in-scope URLs only, robots.txt honoured, public addresses only.
5. Prompts, contract, validators and arms frozen and hashed in `PREREGISTRATION.json` before labelling.
6. Labelled blind from captured text only (no arm, no V3.1 reason, no model output). Labels committed (`4ae15b3`,
   sha256 `805606…`) **before any model call on evalg250**.
7. Before the prompt-grid results were read, an addendum fixed the final runs: P2 on both Flash-Lite models, plus the
   primary prompt chosen by a stated rule on dev80, which is P2.

Labels: 140 correct, 171 incorrect, 27 unsure. The same assistant wrote the prompts and labelled; that correlation is
a known limitation, and owner re-labelling is recommended.

Metrics (`llm_experiments/scoring.py`): precision with Wilson and company-clustered bootstrap 95% intervals; **pool
coverage** = correct published ÷ correct units in the census (a recall *proxy*, not recall); company coverage;
retention of V3.1's correct units; FP/FN; per error category and company type.

## 3. Deterministic baseline on the independent sample

| Arm | Published | Correct | Incorrect | Unsure | Precision | Wilson 95% | Pool coverage | Company coverage |
|---|---|---|---|---|---|---|---|---|
| Permissive baseline `ff3b515` | 334 | 136 | 171 | 27 | 44.3% | 38.9–49.9 | 136/140 | 16/16 |
| **Release V3.1 `334a085`** | 161 | 66 | 77 | 18 | **46.2%** | 38.2–54.3 | 66/140 | 14/16 |
| V3.1 excluding VALMET AS | 131 | 66 | 47 | 18 | 58.4% | 49.2–67.1 | — | — |

V3.1's 77 errors by category:

| Category | Errors |
|---|---|
| Other entity / unrelated (30 are Valmet Oyj group releases) | 37 |
| Advice / educational | 22 |
| Product marketing | 8 |
| Opinion / promotional profile | 7 |
| Job ads | 2 |
| Structural | 1 |

V3.1 withheld 74 correct units; 72 of them for soft content reasons, only 2 for a hard reason (`bulk_entry_burst`).

## 4. Incident: misaligned evidence in the first diagnostic packets (fixed; those runs withdrawn)

* **Symptom.** Model reasons that described another company: "unrelated content about artist Alexander Rybak" for a
  sports club's item.
* **Root cause.** The labeller aid numbers only the units it lists and skips `official_website` rows. Excerpts were
  attached by row position.
* **Measured.** The unit's own title occurred in its source text for 8/269 (eval200b) and 17/175 (eval200) packets
  before the fix; 199/352 and 94/211 after.
* **Fix.** Excerpts are matched by header (organisation + value). A missing or ambiguous header raises. Regression
  test added.
* **Not affected.** evalg250 packets, built from snapshots, are verified: the title occurs in source or article text
  for 329/338. The social, synthesis and What's New experiments are also unaffected.
* **Withdrawn.** Every run made with the misaligned packets is kept only in `runs/invalid-aid-misalignment/`. All
  diagnostic numbers below come from the corrected packets (`dev80v2-*`, `diagv2-*`).

Lesson: quote verification passed because the quotes did occur in the supplied (wrong) text. It proves the model did
not invent text; it cannot prove the packet is right. Packet integrity needs its own checks: title-in-source and
source-page hash.

## 5. News classification: results

### 5.1 Independent evaluation, evalg250 (scored once)

Primary: P2 × `gemini-3.1-flash-lite`.

| Arm | Published | Correct | Incorrect | Unsure | Precision | Wilson 95% | Clustered 95% | Pool coverage | Company coverage | V3.1-correct retention | V3.1 errors removed | Errors added |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V3.1 (deterministic) | 161 | 66 | 77 | 18 | 46.2% | 38.2–54.3 | 25.2–70.3 | 66/140 | 14/16 | 66/66 | — | — |
| A filter | 105 | 60 | 32 | 13 | 65.2% | 55.0–74.2 | 33.6–97.2 | 60/140 | 13/16 | 60/66 | 45/77 | 0 |
| A lenient | 107 | 60 | 33 | 14 | 64.5% | 54.4–73.5 | 32.8–97.2 | 60/140 | 13/16 | 60/66 | 44/77 | 0 |
| B LLM-only | 171 | 117 | 38 | 16 | 75.5% | 68.2–81.6 | 48.8–95.7 | 117/140 | 15/16 | 60/66 | 45/77 | 6 |
| **C hybrid** | 165 | 117 | 35 | 13 | **77.0%** | 69.7–83.0 | 50.0–97.3 | **117/140** | 15/16 | 60/66 | 45/77 | 3 |
| D conservative | 160 | 115 | 34 | 11 | 77.2% | 69.8–83.2 | 49.4–98.0 | 115/140 | 15/16 | 59/66 | 45/77 | 2 |
| D filter | 102 | 59 | 32 | 11 | 64.8% | 54.6–73.9 | 32.5–97.2 | 59/140 | 13/16 | 59/66 | 45/77 | 0 |

Model comparison: P2 × `gemini-3.5-flash-lite` on the same units.

| Arm | Precision | Wilson 95% | Correct published | V3.1-correct retention |
|---|---|---|---|---|
| A filter | 60/94 = 63.8% | 53.8–72.8 | 60/140 | 60/66 |
| B LLM-only | 120/160 = 75.0% | 67.8–81.1 | 120/140 | 60/66 |
| C hybrid | 119/157 = 75.8% | 68.5–81.8 | 119/140 | 60/66 |
| D conservative | 118/156 = 75.6% | 68.3–81.7 | 118/140 | 60/66 |

The two models agree on publish/withhold for 300/338 units. `3.1-flash-lite` is cheaper and, at the time of the
final runs, as fast. The intervals overlap, so neither model is better on this evidence.

**Reading the arms.**
* The *filter* (A) can only remove, so its coverage is capped at V3.1's 66/140 correct units. It removed 45 of V3.1's
  77 errors and lost 6 of V3.1's 66 correct units.
* The *hybrid* (C) also lets Gemini rescue soft-withheld units. That is where the coverage gain comes from: 51 more
  correct units than V3.1 (57 more than the filter), with only 3 errors added relative to V3.1.
* Keeping the deterministic hard gates (C vs B) prevents 3 errors.
* Requiring an explicit stated development with low uncertainty (D vs C) changes almost nothing: −2 correct,
  −1 incorrect. "Conservative evidence" adds no precision here because the residual errors are entity errors, not
  weak-evidence errors.

### 5.2 Label sensitivity (primary model)

| Labelling variant | V3.1 | A filter | C hybrid | C correct coverage |
|---|---|---|---|---|
| As labelled | 46.2% | 65.2% | 77.0% | 117/140 |
| FrP statements relabelled as opinion (incorrect) | 39.2% | 56.5% | 61.8% | 94/99 |
| Excluding VALMET AS | 58.4% | 90.9% | 92.9% | 117/140 |
| Both | 49.6% | 78.8% | 74.6% | 94/99 |

The improvement over V3.1 holds in every variant (+22 to +35 points, coverage about doubled). The level depends on
two judgment calls, which is why owner re-labelling is a prerequisite (§9).

### 5.3 Per error category (incorrect units removed; primary model)

| Category | In census | V3.1 removes | A filter | C hybrid |
|---|---|---|---|---|
| Advice / educational | 66 | 44 | 66 | 66 |
| Other entity / unrelated | 43 | 6 | 14 | 13 |
| Structural / default | 19 | 18 | 19 | 17 |
| Product / service marketing | 15 | 7 | 13 | 13 |
| Opinion / promotional profile | 13 | 6 | 12 | 12 |
| Project / property listing | 9 | 9 | 9 | 9 |
| Job advertisement | 5 | 3 | 5 | 5 |
| Misdated | 1 | 1 | 1 | 1 |

Of the 35 hybrid errors, 30 are other-entity: 26 VALMET AS, plus national/regional federation items on a club's
site. The other 5 are 2 product-improvement announcements, 2 structural, and 1 appeal.

### 5.4 Per company type (precision; correct units published / correct in the census)

| Company type | V3.1 | A filter | C hybrid |
|---|---|---|---|
| Limited companies (AS/ASA; includes Valmet) | 18.5% (10/10) | 25.7% (9/10) | 25.7% (9/10) |
| Foundations, associations, cooperatives | 69.4% (25/73) | 84.6% (22/73) | 88.5% (54/73) |
| Sole proprietorships, partnerships, foreign | 68.8% (11/30) | 100% (10/30) | 100% (29/30) |
| Other forms | 54.1% (20/27) | 90.5% (19/27) | 92.6% (25/27) |

### 5.5 Examples (primary run; `results/evalg250-final.json` lists all)

* **Correct withhold.** 133 incorrect units were withheld in total, for example:
  - the advice post "Slik gjør du din BMW klar for vinteren" ("advice_or_educational");
  - a church's static welcome page that V3.1 published ("product_service_marketing").
* **Correct rescue.** Gemini published MPEnergi's "Signert avtale for EU/EEA prosjekter i Slovakia" and many
  club, association and municipality items that V3.1 withheld as `not_anchored_to_the_company` or
  `feed_item_outside_news_section`.
* **Wrong publish.**
  - "Change in Valmet's Executive Leadership Team: Pia Aaltonen-Forsell appointed CFO", judged a
    `press_release_or_announcement` about `target_company`. The text says "Valmet Oyj's stock exchange release"; the
    subject is the parent group.
  - Product-improvement posts (Sureplay "ännu bättre") were judged product launches.
* **Wrong withhold.**
  - 18 of the 23 misses are FrP (political party) statements judged "political opinion". I labelled them as the
    party's own statements. This is a rubric ambiguity, but Gemini is also inconsistent here: it published about as
    many near-identical FrP statements as it withheld.
  - A completed client project (tennis-to-padel conversion) was called a "reference project".
  - A researcher's own report was attributed to its publisher (NKVTS).

### 5.6 Prompt strategies and model thinking (diagnostic, corrected dev80, `gemini-3.1-flash-lite`)

All five prompt strategies are statistically indistinguishable on dev80 (40 correct, 40 incorrect).

| Prompt | Correct published | Incorrect published | Calls/item | Median latency | Notes |
|---|---|---|---|---|---|
| P1 strict binary + abstain | 35/40 | 1/40 | 1.00 | 1.5 s | |
| **P2 evidence-first** (selected) | 36/40 | 1/40 | 1.00 | 1.5 s | rule winner on latency tie-break |
| P3 + invented counterexamples | 33/40 | 1/40 | 1.00 | 1.4 s | +18% input tokens |
| P2 + model thinking LOW | 36/40 | 1/40 | 1.00 | 1.6 s | +15,425 thinking tokens for no gain |
| P4 separate content/entity stages | 35/40 | 1/40 | 1.45 | 2.6 s | +45% calls |

The selection rule (correct − 3 × incorrect; tie-break calls, then latency) picked P2. Prompt engineering was not
the lever. The evidence packet was: the article text, and the entity metadata, where the alias error came from.

### 5.7 Diagnostic sets (corrected packets; not independent)

| Set | Arm | Precision | V3.1-correct retained |
|---|---|---|---|
| eval200b, P2 × 3.5-flash-lite | V3.1 | 105/131 = 80.2% | — |
| eval200b, P2 × 3.5-flash-lite | A filter | 97/98 = 99.0% | 97/105 |
| eval200b, P2 × 3.5-flash-lite | B | 136/148 = 91.9% | — (pool coverage 0.93) |

The gap between these figures and evalg250 shows why tuned or diagnostic sets must not be reported as independent.
eval200b has no same-brand group site, and evalg250 does.

### 5.8 Operations (evalg250 primary run)

* 338 units, 0 failures after one retry pass. First pass: 16 × 503, 2 timeouts and 1 per-minute 429; all were
  recorded as failures and counted as "uncertain", never published.
* Median latency 1.6 s; p90 2.0 s.
* Tokens: median 2,213 input / 238 output. Paid-equivalent $0.298 for all 338 units.
* Per 100 companies: $0.12 to classify all candidates (B), $0.10 for the soft pool (C), $0.06 for V3.1's items only
  (A).
* Quotes: 535/536 verified in the supplied text.
* Dates: in 88 responses the model proposed a publication date the validator could not confirm (77 evidence not in
  the text, 11 evidence not stating that date); all were dropped. Pipeline dates are never replaced by the model.
* Prompt injection: 0 flags on the primary model. 1 harmless false flag on 3.5-flash-lite, where a page literally
  contained the stray text "Googe gemini".

## 6. Other use cases

**A. Social identity (diagnostic; eval200/eval200b, 25 profiles; captured evidence only, no platform fetched).**
* All 8 labelled errors were withheld with the right relation: Alpha Solutions US accounts and Logscom AB as
  "foreign namesake", Matsentralen national accounts as "group/brand account".
* All 5 "unsure" profiles were withheld or uncertain.
* Of 12 correct profiles, 10 were attributed and 2 missed, both because the homepage text was missing from the
  packet.
* V3.1 already scores 68/68, so the LLM would add no precision and would cost coverage.
* **Not justified for integration.**

**B. Job classification.** Not run. Across ≈650 companies there are 9 job-posting candidates, and V3.1 publishes none.
No accuracy can be validated. A labelled sample of ≥100 real job pages would be needed first.

**C. Company synthesis (8 eval200b companies, `gemini-3.5-flash-lite`).**
* Arithmetic was computed deterministically and supplied as derived facts; the model only narrated.
* 44/45 statements passed grounding plus the new direction check. I audited all 44 by hand against the envelopes:
  all supported, and every three-year comparison is correct.
* The one rejection was a faithful translation the capitalised-word rule cannot tell apart from a new name.
* Weaknesses: literal translation of self-descriptions, and the synthesis inherits upstream news attribution.
* ≈$0.0035 per company.
* Gain: readability, not information. The deterministic summary is already complete and fully keyed.

**D. What's New (9 real cases + 1 labelled synthetic correction).**
* 0 fabricated changes; 0 explanations for the 3 real no-change pairs; the synthetic correction was classified
  correctly.
* Both real source-outage explanations were **wrong**: they said the outage "occurred on" the last-verified
  timestamp.
* A validator artefact (timestamp fragments such as `T01` look like names) rejected 6 explanations.
* **Not recommended yet.**

**UX.** Designed, not built (`docs/v32-llm-architecture.md` §6).

## 7. Prompt versions and models

| Prompt id | Strategy | sha256 (prefix) |
|---|---|---|
| news-p1-binary-v1 | strict binary with abstain | b058be3b |
| **news-p2-evidence-v1** | evidence-first (selected) | 6c18d63d |
| news-p2-evidence-think-v1 | evidence-first + model thinking LOW (no chain-of-thought requested or stored) | 18c84afa |
| news-p3-counter-v1 | evidence-first + invented counterexamples | 781dc288 |
| news-p4-twostage-v1 | separate content and entity stages | 15e3bbb8 |

Models (free tier; caps per project):

| Model | Daily cap | Status |
|---|---|---|
| `gemini-3.1-flash-lite` | 500/day | primary |
| `gemini-3.5-flash-lite` | 500/day | comparison |
| `gemini-3.6-flash` | ≈20/day | too small for an experiment |
| `gemini-3-flash-preview` | ≈20/day | too small for an experiment |
| `gemini-3.8-flash` | 20/day | too small; rejects MINIMAL thinking |
| `gemini-2.5-flash-lite` | — | not available to new users |

A comparison against a larger model (3.6/3.8 Flash) was not possible on the free tier. Given that the residual errors
come from entity metadata, a larger model is not the obvious next step anyway.

## 8. Security and privacy

See `docs/v32-gemini-api-report.md` §5–6.
* No key in any file or commit (scanned, including the two added keys).
* Header-only transport; redaction now also covers the `AQ.` key format.
* No tools, no model-controlled I/O; untrusted web text fenced; validation can only lower a decision.
* The daily-quota circuit breaker stopped calls at the first daily 429 on every model and project.
* The work was completed across three free-tier projects at the owner's request. Using several projects to exceed
  free-tier limits may conflict with Google's terms on circumventing usage limits; production should use one billed
  project.
* Free-tier content may be used for training and read by human reviewers.
* **Production for Norwegian (EEA) users requires the paid tier.**

## 9. Recommendation

**Should LLM assistance be integrated into a future Signalpost release? Yes, as an opt-in hybrid, after four
prerequisites. Not now, and not in the competition release.**

The case for it:
* On independent data the hybrid raised precision from 46% to 77% and correct coverage from 66 to 117 of 140 units.
* It removed entire error classes that deterministic rules have not managed to remove (advice, explainers, listings,
  job ads).
* It costs about $0.10 per 100 companies.
* The default pipeline can stay $0 and unchanged.

Before integration:
1. **Fix the entity contract.**
   - Never derive aliases from a bare brand token.
   - Pass explicit registry evidence: "the site's operator is a different legal entity (parent group), so items
     naming the brand are presumed the group's".
   - Fix the deterministic website identity rule that accepted valmet.com on one name token. That alone removes the
     largest single error source for V3.1 as well.
2. **Measure again on a new independent sample.** evalg250 is consumed. Use the same pre-registered protocol, with
   ≥300 units across more companies to narrow the clustered interval.
3. **Owner re-labelling** of a random 25% of that sample, to quantify labeller disagreement. The FrP case shows the
   rubric needs a ruling on organisations' political and position statements.
4. **Paid tier, DPIA, a spend cap per run, and the packet-integrity checks from §4.**

Then integrate as `C_hybrid`, with V3.1's hard gates unchanged, behind `SIGNALPOST_LLM=gemini`, recording
`llm_assessment` per claim as in `docs/v32-llm-architecture.md`. The filter (A) is the more conservative fallback: it
never adds a unit V3.1 would not publish, but it cannot recover coverage.

## 10. Files, commits, experiment ids

New code (no release file modified):
* `src/norway_company_agent/llm/gemini.py`
* `src/norway_company_agent/llm_experiments/__init__.py`
* `src/norway_company_agent/llm_experiments/capture.py`
* `src/norway_company_agent/llm_experiments/datasets.py`
* `src/norway_company_agent/llm_experiments/news_contract.py`
* `src/norway_company_agent/llm_experiments/prompts.py`
* `src/norway_company_agent/llm_experiments/policies.py`
* `src/norway_company_agent/llm_experiments/runner.py`
* `src/norway_company_agent/llm_experiments/scoring.py`
* `src/norway_company_agent/llm_experiments/social.py`
* `src/norway_company_agent/llm_experiments/synthesis.py`
* `scripts/run_gemini_news_experiment.py`
* `tests/test_llm_gemini_experiment.py`

Measurements: `measurements/v32-gemini-2026-11-04/`
* sampling: `draw_sample.py`, `inputs/`
* capture and packets: `build_diag.py`, `build_evalg250.py`, `replay_with_reasons.py`, `capture-evalg250/`,
  `datasets/`
* labels: `audits/evalg250/`
* pre-registration: `PREREGISTRATION.json`
* runs and cache: `runs/`, `cache/` (all responses; every result re-scores offline)
* scoring: `evaluate.py`, `compare_dev.py`, `final_report.py`, `ops_summary.py`
* secondary experiments: `run_synthesis.py`, `run_social.py`
* results: `results/evalg250-final.json`, `results/evalg250-deterministic-baseline.json`,
  `results/dev80v2-grid.json`, `results/diagv2-eval200b-p2-35fl.json`, social, synthesis
* drivers: `run_*.sh`, `run_completion.sh`

Docs: `docs/v32-gemini-api-report.md`, `docs/v32-llm-architecture.md`, this file.

Experiment ids:
* final: `final-evalg250-news-p2-evidence-v1-gemini-3.1-flash-lite` (primary),
  `final-evalg250-news-p2-evidence-v1-gemini-3.5-flash-lite` (model comparison)
* grid: `dev80v2-<prompt>-gemini-3.1-flash-lite` (5)
* diagnostic: `diagv2-eval200b-news-p2-evidence-v1-gemini-3.5-flash-lite`
* secondary: `synth-v1`, `whatsnew-v1`, `social-v1`
* withdrawn: `runs/invalid-aid-misalignment/`
