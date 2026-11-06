# Signalpost and Gemini: experiment disclosure

**Summary.** Signalpost as submitted is fully deterministic. Gemini (Google's LLM API) was tested as an optional
classifier for company news, at no cost, on Gemini's free tier. Everything is on an experimental branch, and it is
**disabled by default**. This document reports what was tried, what was measured on which data, the known failure
cases, and how an evaluator can reproduce or extend the experiment with their own key and budget.

## 1. Why we experimented with Gemini

Signalpost's deterministic pipeline finds dated news on a company's own website. On data it was not tuned on, it
also publishes many items that are not news *about that legal entity*. Two kinds of item get through:

* **Wrong content:** advice articles, product pages, opinion pieces, vacancies and theme demo posts.
* **Wrong entity:** news of a parent group, a sister company, a federation or a manufacturer, published on or near
  the company's site.

Telling these apart from genuine company news needs reading comprehension that rules handle poorly. The question was
whether a small, cheap LLM, kept on a short leash, raises precision without destroying coverage.

**The leash:**
* Deterministic stages own source eligibility, identity, dates, provenance and legal-entity restrictions.
* The LLM only classifies the content of one item. It returns strict JSON and must quote its evidence verbatim; the
  quotes are checked against the captured text.
* It has no tools and no network access. Validation can only lower a decision, and the LLM can never publish an item
  a deterministic hard gate withheld.

## 2. The deterministic baseline (V3.1, the submitted release)

The release (`334a085`) does not call any LLM. Its news precision depends strongly on the sample:

| Sample | Role | V3.1 news precision (Wilson 95%) |
|---|---|---|
| eval200b | used while tuning V3.1, so optimistic | 80.2% |
| evalg250 (250 new companies) | independent | 46.2% (38.2–54.3%) |
| evalh400 (400 new companies) | independent | 48.3% (41.1–55.6%) |

The drop on new data is itself a finding about the deterministic release, independent of any LLM.

## 3. Results so far: diagnostic versus independent

"Independent" means:
* the sample was drawn after the method was frozen;
* the labels were committed before any model call;
* the result was scored once, with no prompt or rule changed afterwards.

"Diagnostic" means the data informed the method, so its scores are optimistic.

| Sample | Role | Configuration | V3.1 | Gemini filter | Hybrid |
|---|---|---|---|---|---|
| eval200, eval200b, dev80 | diagnostic | prompt and model selection | — | — | — |
| **evalg250** (338 news units) | **independent** (at the time) | prompt v1, no identity gate | 46.2% | 65.2% (55.0–74.2) | **77.0%** (69.7–83.0); clustered 50.3–97.4 |
| evalg250 re-scored with the identity gate | **diagnostic** (the gate was built from evalg250's errors) | cached prompt-v1 outputs + gate | 46.2% | 90.9% | 92.9% (87.0–96.2) |
| evalg250, same, FrP items relabelled under rubric v2 | diagnostic, provisional | — | 40.3% | 81.8% | 82.5% |
| **evalh400** (433 news units) | **independent, pre-registered** | prompt v2 + identity gate | 48.3% | see §4 | see §4 |

On evalg250, Gemini removed almost every content-type error: advice, listings and job ads. It failed on
legal-entity boundaries. One subsidiary whose registered website is its foreign parent's global site produced most of
the remaining errors. That led to the deterministic identity gate (§6), which the 92.9% figure includes. The 92.9% is
**not** an independent result.

## 4. Final independent evaluation (evalh400)

_Status: to be completed from `measurements/v32-gemini-2026-11-04/results/evalh400-score.json` once the run and
scoring finish. A partial run is never reported as a complete result._

## 5. Expenditure and estimated operating cost

* **Actual spend on this research: $0.** Every call used Gemini's free tier, and no billing account was linked.
* **Estimated paid operating cost: about $0.12 per 100 sampled companies.**
  * Measured on evalg250: 338 calls cost $0.298 at list price (`gemini-3.1-flash-lite`: $0.25 per million input
    tokens, $1.50 per million output tokens). That is $0.12 per 100 sampled companies.
  * Most companies have no news candidates. Per 100 companies that do have candidates, the cost is about $1.
  * The cost scales with the number of news items, not companies, at roughly $0.001 per item.

**Disclosures on API use.**
* Part of the earlier evalg250 work was spread across three free-tier projects to stay within daily limits. That may
  conflict with Google's terms on circumventing usage limits, so it was not repeated. The evalh400 run uses one key
  in one project, and the runner refuses to start if other key variables are set.
* The key used for evalh400 had been shown in a screenshot during the research. The owner chose to keep using it.
  The run records that decision, and the key value appears in no file or log.

## 6. Known failure cases and limitations

1. **Legal-entity boundaries under a shared brand.** Gemini accepted a foreign parent group's releases as its
   Norwegian subsidiary's news, because the packet named the bare brand. Exact quote verification did not catch it:
   the quotes were genuine, but about another entity. Quote verification proves provenance, not identity.
2. **The identity gate does not cover every wrong-entity pattern.** On evalh400, V3.1 published 23 wrong-company
   items, and the frozen gate removed none of them:
   * acquisitions announced by a parent or sister company on the target's own site;
   * a club subdomain on a sports federation's platform carrying federation and other clubs' events;
   * a dealer relaying a car manufacturer's news.

   These were seen during labelling, so the gate was deliberately **not** tuned on evalh400.
3. **Opinion versus action.** For political parties and associations, Gemini published opinion pieces as news. On
   the diagnostic FrP set it agreed with the stricter rubric on 32 of 45 items. Prompt v2 adds an explicit rule;
   its effect is measured only on evalh400.
4. **Labels.** All labels come from one labeller, the same assistant that wrote the prompts. A blind second-person
   review kit is prepared (about 25% of each sample) but not yet completed, and agreement is not reported.
5. **Small samples, wide uncertainty.** evalh400's 433 news units come from only 57 companies. Company-clustered
   confidence intervals are much wider than item-level ones.
6. **Free-tier conditions.**
   * Latency is variable, about 1.6 s median on evalg250, with occasional 503 "overloaded" retries.
   * Daily request caps limit experiment size.
   * Larger models had too small a free quota to compare.
7. **Model drift.** Hosted model versions change and are retired. Results are pinned through a response cache keyed
   by model, prompt, schema and packet hashes, not through the live API.
8. **Other uses tested and not recommended yet:**
   * social-account attribution, where the deterministic release is already correct;
   * job classification, which had too few examples;
   * "What's New" explanations, which misdescribed source outages;
   * company synthesis, which improves readability but adds no information.

## 7. Why Gemini is disabled by default

* The deterministic release is complete without it and is the submitted system.
* Production use for Norwegian (EEA) users requires Gemini's **paid** tier: free-tier inputs may be used to improve
  Google's products. It also needs a data-processing assessment.
* The improvement is established on one independent sample at most (§3–4), with known entity-boundary failures (§6).
* The provider is enabled only when `GEMINI_ENABLED` is true and a key is set. The release's run path never imports
  the experimental code (tested).

## 8. How to reproduce or extend the experiment

All inputs and outputs are committed on the experimental branch:
* captured packets and labels;
* pre-registrations with file hashes;
* run records;
* the response cache (2,141+ responses).

**A. Reproduce every reported number offline (no key, no cost).** The runner is cache-only by default:

```bash
uv sync
```

```bash
uv run python scripts/run_gemini_news_experiment.py --packets measurements/v32-gemini-2026-11-04/datasets/evalg250.packets.jsonl.gz --prompt news-p2-evidence-v1 --model gemini-3.1-flash-lite --experiment-id final-evalg250-news-p2-evidence-v1-gemini-3.1-flash-lite --out /tmp/replay-evalg250.jsonl
```

```bash
uv run python measurements/v32-gemini-2026-11-04/evaluate.py --set evalg250 /tmp/replay-evalg250.jsonl
```

This replay was checked: 338/338 decisions identical to the committed run, 0 API calls. evalh400 works the same
way, scored with `score_evalh400.py`. The scorer refuses a run whose model, prompt or frozen code differs from the
pre-registration, or whose calls did not all complete.

**B. Re-run live with your own key and budget.**

```bash
export GEMINI_API_KEY=...   # your key, in one project; nothing is read from files
```

```bash
uv run python scripts/run_gemini_news_experiment.py --packets measurements/v32-gemini-2026-11-04/datasets/evalh400.packets.jsonl.gz --prompt news-p2-evidence-v2 --model gemini-3.1-flash-lite --experiment-id builderr-evalh400 --cache /tmp/builderr-cache --out /tmp/builderr-evalh400.jsonl --live --max-calls 450 --max-usd 1.00 --rpm 10
```

```bash
uv run python measurements/v32-gemini-2026-11-04/score_evalh400.py /tmp/builderr-evalh400.jsonl
```

Notes for a live run:
* A separate `--cache` directory forces fresh calls instead of replaying ours.
* `--live` requires both a call cap and a cost cap.
* The run stops at the first daily-quota refusal. Rerunning resumes from the cache.
* Expect a paid-equivalent cost of about $0.45 for the 433 evalh400 calls.
* LLM outputs are not bit-for-bit deterministic, so expect small differences from our run.
