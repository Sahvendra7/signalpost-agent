# evalh400: deterministic versus Gemini filter versus hybrid (independent, pre-registered)

**Status:**
* Final, scored once on 2026-11-06.
* Pre-registered in `measurements/v32-gemini-2026-11-04/PREREGISTRATION_v2.json`, with one addendum written before
  any label or model call.
* No prompt, rule, packet or label was changed after the run.

Scored with `score_evalh400.py`, which checks every frozen file hash, the model and prompt, and that the run is
complete. Output: `results/evalh400-score.json`.

## Setup

| | |
|---|---|
| Sample | 400 companies drawn at random (seed 20261106) from Brreg units with a website. Disjoint from every organisation number in the repository. 57 companies had news candidates: 433 units, capped at 12 per company before labelling. |
| Labels | Rubric v2, blind (captured text only), committed before any model call (`28c71e9`): 138 correct, 279 incorrect, 16 unsure. Unchanged. |
| Model / prompt | `gemini-3.1-flash-lite`, `news-p2-evidence-v2` (sha `3f1d2431715f`), thinking MINIMAL, packet v2 |
| Run | 433/433 calls succeeded (13 needed one retry); 0 failures; no budget stop. 601/602 quotes verified verbatim in the captured text. |
| API use | One key (`GEMINI_API_KEY`), one free-tier project, 10 requests/min, cap 450 calls / $1 paid-equivalent. The key was on the exposed list; the owner chose to keep it (`runs/…key_note.json`). |

## Arms (all on identical inputs)

* **V3.1**: the submitted deterministic release, as published.
* **V3.1 + identity gate**: V3.1 minus items the deterministic identity gate withholds. No LLM.
* **Gemini filter** (`A_filter_v2`): V3.1's publications that pass the gate and that Gemini also publishes.
* **Hybrid** (`C_hybrid_v2`, primary): every candidate V3.1 did not hard-reject and the gate passes, published only
  when Gemini publishes it.
* **Conservative hybrid** (`D_conservative_v2`): the hybrid, restricted to explicit events with low uncertainty and at
  least one verified quote.
* **Gemini only** (`B_llm_only`): Gemini over the whole pool with no deterministic gate. Reference only; not a
  deployable design.

## Results

| Arm | Published | Correct | Incorrect | Unsure | Precision | Wilson 95% | Company-clustered 95% | Item coverage | Company coverage | Wrong-company published |
|---|---|---|---|---|---|---|---|---|---|---|
| V3.1 | 190 | 86 | 92 | 12 | 48.3% | 41.1–55.6% | 35.5–61.1% | 86/138 (62%) | 29/37 | 23 |
| V3.1 + identity gate | 190 | 86 | 92 | 12 | 48.3% | 41.1–55.6% | 35.5–61.1% | 86/138 | 29/37 | 23 |
| Gemini filter | 96 | 79 | 15 | 2 | **84.0%** | 75.3–90.1% | 67.6–95.0% | 79/138 (57%) | 26/37 | 2 |
| **Hybrid (primary)** | 145 | 116 | 25 | 4 | **82.3%** | 75.1–87.7% | 70.6–91.7% | **116/138 (84%)** | **32/37** | 2 |
| Conservative hybrid | 139 | 113 | 23 | 3 | 83.1% | 75.9–88.5% | 71.3–92.2% | 113/138 | 31/37 | 2 |
| Gemini only (reference) | 158 | 127 | 27 | 4 | 82.5% | 75.7–87.7% | 70.4–91.5% | 127/138 | 33/37 | 2 |

Definitions:
* Precision counts correct ÷ (correct + incorrect); unsure items are excluded.
* Item coverage is correct published ÷ the 138 correct units in the labelled pool. It is a recall proxy, not recall:
  news that no arm found is not in the pool.
* Company coverage counts companies with at least one correct item published, out of the 37 that have any.

**Hybrid against V3.1:**
* **Genuine items recovered:** 37 correct items V3.1 did not publish. It lost 7 that V3.1 had.
* **Item coverage:** 86 → 116 correct items, with 22 false negatives. Of those, 11 were hard-rejected by V3.1's
  deterministic gates, and 11 were withheld by Gemini.
* **Incorrect items published:** 92 → 25. Of V3.1's 92 errors, 77 were removed, and 10 new errors came from
  candidates V3.1 had withheld.

Errors that remain in the hybrid (25):

| Category | Count | Notes |
|---|---|---|
| Opinion or promotional profile | 13 | 6 designer profiles in one shop's window series; 3 performance programme pages at one theatre |
| Product or service marketing | 6 | |
| Structural or default page | 3 | |
| Wrong company | 2 | both federation events on a club's subdomain of the federation platform |
| Misdated | 1 | |

**Wrong-company publications: 23 → 2.** The identity gate passed all 433 evalh400 units, because the sample has no
group or foreign-namesake sites. Gemini removed:
* every parent-group and sister-company acquisition item;
* every car-manufacturer item;
* 6 of the 8 federation-platform items.

The gate's own effect was shown only on the consumed evalg250 set. It is not demonstrated independently here.

**Operations and cost.**
* Latency: median 1.5 s, p90 10.0 s per item, on the free tier.
* Tokens: 1,055,966 input and 102,197 output.
* Paid-equivalent cost at list price: $0.417, which is $0.10 per 100 sampled companies or $0.73 per 100 companies
  with news candidates.
* **Actual spend: $0.** The project is on the free tier with no billing account linked. The owner confirms this,
  and an earlier probe showed this project at free-tier limits. No call in this run was rate-limited, so the run
  itself carries no tier marker.

## Against the pre-registered bar

* **Target ≥90% precision: not met.** The hybrid reaches 82.3%, and the upper Wilson bound is 87.7%.
* **"Without sacrificing all coverage": met and exceeded.** Coverage rose from 62% to 84% of correct items.
* **Improvement over V3.1: demonstrated.** Precision +34 points with non-overlapping intervals (Wilson and
  company-clustered), and coverage up at the same time.
* **Filter versus hybrid.** The filter is about as precise as the hybrid (84.0% against 82.3%) but recovers far
  fewer items (79 against 116). The hybrid is the better trade-off, as pre-registered.

## Sensitivity and caveats (do not change the result above)

* **One labelling judgment carries much of the remaining error.** A shop's "window takeover" posts profile a designer
  exhibited in the shop window; they were labelled promotional profiles. Counted as the shop's own exhibition events
  instead, the hybrid would be 122/141 = 86.5%. This is a sensitivity figure, not a relabel; the labels stay as
  committed.
* **Single labeller.** The labeller is the same assistant that wrote the prompts, including prompt v2's
  organisations rule. A blind second-person review of 112 units is prepared and not yet done. Until it is, the
  labels and these figures are single-rater.
* **Small sample.** There are 57 companies with candidates. The company-clustered intervals (70.6–91.7% for the
  hybrid) are the honest width.
* **What independence covers.** evalh400 tests the frozen pipeline and prompt v2. It does not validate any rule
  changed after this run, and none will be described as validated by it.

## Recommendation

The hybrid has **demonstrated a clear, independent improvement** over the deterministic release:
* precision 48% → 82%;
* correct coverage 62% → 84%;
* wrong-company publications 23 → 2;
* at about $0.10 per 100 companies.

That is enough to justify developing it towards a **future, opt-in** release. It is not enough to make it a default
or to claim the 90% target. Before such a release:
1. complete the second-person review and report agreement;
2. add a deterministic rule for federation-platform subdomains, validated on a fresh sample;
3. run on the paid tier, with a data-processing assessment for EEA use.

The submitted V3.1 stays deterministic, and Gemini stays disabled by default.
