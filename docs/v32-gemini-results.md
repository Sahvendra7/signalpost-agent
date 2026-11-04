# V3.2 research: Gemini for Signalpost — results (interim; the independent LLM evaluation is not finished)

Branch `experiment/v3.2-gemini` (local, not pushed), based on `139e23c` (`v3.1-candidate-2`, code `334a085`).
Companion documents: `docs/v32-gemini-api-report.md` (API, cost, privacy, security) and
`docs/v32-llm-architecture.md` (architecture and integration design). All labels are `assistant_blind`.

## 0. Bottom line

1. **The independent LLM news evaluation is incomplete.** The pre-registered run on the new sample evalg250 finished
   64 of 338 units before the free tier's 500 requests/day cap stopped it. No LLM accuracy figure on independent data
   is reported, because 64 units from 10 companies are not a valid sample.
2. **All diagnostic LLM news results are invalid** and have been withdrawn. A data-alignment bug gave the model another
   unit's source excerpt in most diagnostic packets (§4). It was found by inspecting implausible model reasons, then
   fixed, with a regression test. The impressive diagnostic numbers seen during the run (97–100% precision) must
   not be quoted.
3. **The deterministic release does not hold its earlier precision on new data**: V3.1 news precision on evalg250 is
   **66/143 = 46.2%** (Wilson 38.2–54.3%; company-clustered 24.0–69.9%), against 80.2% on eval200b. One company's
   group website (VALMET AS on valmet.com) contributes 30 of the 77 errors; without it, 58.4%. This is a valid,
   independent measurement of `334a085`.
4. What *is* established: the contract works operationally (752 successful calls, 0 malformed JSON, 87/88 quotes
   verified exactly on evalg250), it is cheap (≈$0.13 per 100 companies to classify every candidate), and the
   secondary experiments behaved safely (no fabricated change, no ungrounded synthesis statement after validation).
5. **Recommendation: do not integrate yet.** Finish the pre-registered evaluation first (≈2 more free-tier days, or
   ≈$2 on a billed project, §9).

## 1. Release protection

* Working tree clean at start; `139e23c` (docs) is code-identical to `334a085` (`git diff 334a085 139e23c -- src tests
  scripts pyproject.toml uv.lock` is empty).
* The tag `v3.1-candidate-2` was a *local* tag of the previous machine and does not exist in this fresh clone or on
  the remote (only `submission-candidate-1`). It was **not** recreated. The release branch was not modified.
* Experimental branch `experiment/v3.2-gemini` created from `139e23c`; nothing pushed.
* Release test suite in this container: **533 passed, 175 subtests**. With the V3.2 additions: see §10.
* The release run path never imports the new code (tested: importing `cli`/`pipeline` loads neither
  `llm.gemini` nor `llm_experiments`).

## 2. Data and method

| Set | Role | Units | How |
|---|---|---|---|
| eval200, eval200b | diagnostic only (used in V3.1 tuning) | 211 / 352 news units | existing `assistant_blind` labels; article pages re-captured 2026-11-04 |
| **evalg250** | **independent final evaluation** | 338 news units, 250 organisations | drawn 2026-11-04 (seed 20261104) from 110,821 eligible Brreg entities (registered website, not bankrupt/liquidating), excluding all 10,055 organisation numbers found anywhere in the repository; drawn **before any prompt existed** |

evalg250 procedure (as in V3.1):

1. Captured live through the permissive baseline `ff3b515`; snapshots kept.
2. Replayed through a **clean worktree of `334a085`**. A runtime hook logged every withheld candidate and its
   reason; release code was not modified.
3. Census of every news unit either arm published.
4. Article pages captured deterministically: in-scope URLs only, robots.txt honoured, public addresses only.
5. Prompts, contract, validators and arms frozen and hashed in `PREREGISTRATION.json` before labelling.
6. Labelled blind from captured text only (no arm, no V3.1 reason, no model output). Labels committed (`4ae15b3`,
   sha256 `805606…`) **before any model call on evalg250**.
7. The final-run plan and the prompt-selection rule were added as an addendum before the grid results were read.

Labels: 140 correct, 171 incorrect, 27 unsure. The same assistant wrote the prompts and labelled; that correlation is
a known limitation (owner re-labelling is recommended).

Metrics (`llm_experiments/scoring.py`): precision with Wilson and company-clustered bootstrap 95% intervals; **pool
coverage** = correct published ÷ correct units in the census (a recall *proxy*, not recall); company coverage;
retention of V3.1's correct units; FP/FN; per error category and company type.

## 3. Deterministic baseline on the independent sample (valid)

| Arm | Published | Correct | Incorrect | Unsure | Precision | Wilson 95% | Clustered 95% | Pool coverage | Company coverage |
|---|---|---|---|---|---|---|---|---|---|
| Permissive baseline `ff3b515` | 334 | 136 | 171 | 27 | 44.3% | 38.9–49.9 | 22.3–64.4 | 136/140 | 16/16 |
| **Release V3.1 `334a085`** | 161 | 66 | 77 | 18 | **46.2%** | 38.2–54.3 | 24.0–69.9 | 66/140 | 14/16 |
| V3.1 excluding VALMET AS | 131 | 66 | 47 | 18 | 58.4% | 49.2–67.1 | 41.7–73.6 | — | — |

V3.1's 77 errors by category: other entity / unrelated 37 (30 are Valmet Oyj group releases on valmet.com for the
Norwegian subsidiary VALMET AS), advice/educational 22, product marketing 8, opinion/promotional profile 7, job ads 2,
structural 1. By company type, V3.1 precision is 18.5% (10/54) for limited companies, 69.4% (25/36) for foundations,
associations and cooperatives, and 68.8% (11/16) for sole proprietorships, partnerships and foreign entities.

V3.1 withheld 74 correct units; 72 of them for *soft* content reasons (`not_anchored_to_the_company` 26,
`no_article_evidence` 23, `feed_item_outside_news_section` 17, advice rules 6), only 2 for a hard reason. This is the
coverage an LLM content judgment could recover under the hybrid arm, if it is accurate enough.

## 4. Incident: misaligned evidence in the diagnostic packets (all diagnostic news results withdrawn)

* **Symptom.** Model reasons that described another company: "unrelated content about artist Alexander Rybak" for a
  sports club's item.
* **Root cause.** The labeller aid (`aid.md`) numbers only the units it lists and skips `official_website` rows. The
  packet builder attached excerpts by row position in `items.labelled.csv`.
* **Measured.** The unit's own title occurred in its source text for 8/269 (eval200b) and 17/175 (eval200) packets
  before the fix; 199/352 and 94/211 after.
* **Fix.** Excerpts are matched by header (organisation + value). A missing or ambiguous header raises. Regression
  test added.
* **Not affected.** evalg250 packets, built from the snapshots, are verified: the title occurs in source or article
  text for 329/338. The social, synthesis and What's New experiments are also unaffected.
* **Withdrawn.** The pilot, all eval200/eval200b runs, the dev80 prompt × model grid and the eval200b diagnostic.
  They are kept in `runs/invalid-aid-misalignment/` with an explanation, and no number from them appears here.

The incident is a concrete instance of the risk the strict contract is meant to catch: quote verification passed,
because the quotes did occur in the supplied (wrong) text. Quote verification proves the model did not invent text;
it cannot prove the packet is right. Packet integrity needs its own deterministic checks: title-in-source and
source-page hash.

## 5. News classification experiments A–D: status

| | Status |
|---|---|
| Arms implemented (A filter, A lenient, B LLM-only, C hybrid with deterministic hard gates, D conservative, D filter) | done, pre-registered (`policies.py`) |
| Prompt strategies (P1 strict binary/abstain, P2 evidence-first, P2 + model thinking LOW, P3 counterexamples, P4 separate content/entity stages) | written and frozen; **comparison evidence withdrawn** (§4) |
| evalg250 P2 × `gemini-3.1-flash-lite` | **64/338 units** (stopped by the 500/day cap; 274 to go) |
| evalg250 P2 × `gemini-3.5-flash-lite` (model comparison) | not started (daily cap reached on diagnostic runs) |
| evalg250 primary (prompt chosen by the pre-registered rule) | waiting for the corrected dev80 grid |

Operational facts from the valid evalg250 records (64 units, `gemini-3.1-flash-lite`): median 2,213 input /
238 output tokens, $0.00095 paid-equivalent per unit, 87/88 quotes verified (87 exact), 0 malformed responses. During
the run: 16 × 503, 8 × per-minute 429, 3 timeouts, then the daily cap. All failures were recorded as failures
(`uncertain`, never published), never silently replaced.

## 6. Other use cases

**A. Social identity (diagnostic; eval200/eval200b, 25 profiles; captured evidence only, no platform fetched).**
* All 8 labelled errors were withheld with the right relation: Alpha Solutions US accounts and Logscom AB as
  "foreign namesake", Matsentralen national accounts as "group/brand account".
* All 5 "unsure" profiles were withheld or uncertain.
* Of 12 correct profiles, 10 were attributed and 2 missed. For PEN Underwriting, its site shows the trading name
  Fender Marine AS next to the target's organisation number, and that page text was missing from the packet.
* V3.1 already scores 68/68 on eval200b social, so the LLM would add no precision and would cost coverage.
* **Not justified for integration.**

**B. Job classification.** Not run. Across ≈650 companies there are 9 job-posting candidates, and V3.1 publishes
none (all 8 on evalg250 withheld as `currency_unknown`). No accuracy can be validated on this data. A labelled sample
of ≥100 real job pages would be needed first.

**C. Company synthesis (8 eval200b companies, `gemini-3.5-flash-lite`).**
* Arithmetic was computed deterministically and supplied as derived facts; the model only narrated.
* 44/45 statements passed grounding plus the new direction check. I audited all 44 by hand against the envelopes:
  all supported, and every three-year comparison is correct.
* The one rejection was a faithful English translation of a registered activity ("Christian …"). The
  capitalised-word rule cannot tell a translation from a new name.
* Weaknesses:
  - literal translation of self-descriptions ("an inhabited resting place outside the asphalt");
  - the synthesis inherits upstream attribution: it repeats website items as "the company's website reports", which
    is only as good as the news classification.
* Cost ≈ $0.0035 per company; median 12 s.
* The deterministic summary is already complete and fully keyed, so the LLM's gain is readability, not information.

**D. What's New (9 cases from real envelopes + 1 labelled synthetic correction).**
* 0 fabricated changes; the 3 real no-change pairs got 0 explanations.
* The synthetic same-period revenue change was correctly explained as "corrected".
* Both real source-outage explanations were **wrong**: they said the outage "occurred on" the *last-verified*
  timestamp.
* The validator rejected those two, but for an artefact reason: timestamp fragments such as `T01` look like names.
  The same artefact rejected 4 correct retraction explanations.
* The wording added little over deterministic templates.
* **Not recommended yet.** Keep the deterministic change list; if wording is wanted, pass human-readable fields
  (`checked_at`, `last_verified_at`) under unambiguous names.

**UX.** Designed, not built (`docs/v32-llm-architecture.md` §6): an "AI assessment" note per news item with verified
quotes and a snapshot link, a company-scoped evidence-only Q&A using the synthesis validator, and an optional
comparison narrative over deterministic differences.

## 7. Prompt versions and models

| Prompt id | Strategy | sha256 (prefix) |
|---|---|---|
| news-p1-binary-v1 | strict binary with abstain | b058be3b |
| news-p2-evidence-v1 | evidence-first | 6c18d63d |
| news-p2-evidence-think-v1 | evidence-first + model thinking LOW (no chain-of-thought requested or stored) | 18c84afa |
| news-p3-counter-v1 | evidence-first + invented counterexamples | 781dc288 |
| news-p4-twostage-v1 | separate content and entity stages | 15e3bbb8 |
| social-v1, synth-v1, whatsnew-v1 | secondary experiments | in cache records |

Models on this project (free tier):

| Model | Daily cap | Latency | Status |
|---|---|---|---|
| `gemini-3.1-flash-lite` | 500/day | median 8 s | usable |
| `gemini-3.5-flash-lite` | 500/day | median 36 s | usable |
| `gemini-3.6-flash` | ≈20/day | — | too small for an experiment |
| `gemini-3-flash-preview` | ≈20/day | — | too small for an experiment |
| `gemini-3.8-flash` | 20/day | — | rejects MINIMAL thinking |
| `gemini-2.5-flash-lite` | — | — | not available to new users |

A valid model comparison does not exist yet. The only same-item comparison (14 items) was on the misaligned packets
and is withdrawn.

## 8. Security and privacy

See `docs/v32-gemini-api-report.md` §5–6.
* No key in any file or commit (scanned).
* Header-only transport; errors redacted.
* No tools and no model-controlled I/O.
* Untrusted web text fenced; `injection_detected` blocks publication.
* Validation can only lower a decision.
* Daily-quota circuit breaker worked: it stopped calls at the first daily 429 on every model.
* Free-tier content may be used for training and read by human reviewers.
* **Production for Norwegian (EEA) users requires the paid tier.**

## 9. What is needed to finish (decision for the owner)

Remaining pre-registered work:

| Work | Model | Calls |
|---|---|---|
| Re-run the dev80 grid on corrected packets (P1, P2, P3, P2-think, P4) | `3.1-flash-lite` | ≈450 |
| Finish P2 on evalg250 | `3.1-flash-lite` | 274 |
| Primary prompt on evalg250, if not P2 | `3.1-flash-lite` | 338 |
| P2 on evalg250 (model comparison) | `3.5-flash-lite` | 338 |
| Optional: corrected eval200b diagnostic | `3.5-flash-lite` | 352 |

* **Free tier:** about 2 days, at 500 calls per day per model. Daily quotas reset at 08:00 UTC. All completed
  responses are cached, so nothing is re-requested.
* **Billed project (paid tier):** about 1,750 calls ≈ **$1.6 paid-equivalent** at current prices, within an hour.
  This would also allow `gemini-3.6-flash` on the same sets (≈$3 more).
* The local commits exist only in this container. If it is reclaimed before the work resumes, they are lost unless
  pushed. Pushing was not done, as instructed.

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
* runs and cache: `runs/`, `cache/` (all responses; reruns are offline)
* scoring: `evaluate.py`, `compare_dev.py`, `final_report.py`, `ops_summary.py`
* secondary experiments: `run_synthesis.py`, `run_social.py`, `results/`
* drivers: `run_*.sh`

Docs: `docs/v32-gemini-api-report.md`, `docs/v32-llm-architecture.md`, this file.

Experiment ids:
* `final-evalg250-news-p2-evidence-v1-gemini-3.1-flash-lite` (partial, valid)
* `synth-v1`, `whatsnew-v1`, `social-v1` (cached records in `results/`)
* withdrawn: everything in `runs/invalid-aid-misalignment/`
