# V3.2 research: LLM architecture proposal and recommended integration design

Status: proposal only. Nothing here is enabled; the default pipeline is unchanged and makes no LLM call. Results
that motivate it are in `docs/v32-gemini-results.md`.

## 1. Principles (non-negotiable)

1. **Deterministic first, LLM second, deterministic last.** Identity, website operator, source integrity and dates are
   decided by the existing deterministic gates. The LLM only reads content the pipeline already captured, and only
   for candidates that passed those gates. Its output is validated deterministically, and validation can only
   *lower* a decision (publish → uncertain/withhold), never raise it.
2. **Off by default, $0 by default.** The run path never imports the LLM code unless `SIGNALPOST_LLM=gemini` (or the
   existing `LLM_ENABLED`) *and* a key are present. No automatic paid usage: a billed project and an explicit
   per-run budget are required. The competition release does not enable it without separate approval.
3. **No silent fallback.** Every LLM-assisted unit records whether the model was consulted, its verdict, the model
   and prompt version, and the deterministic verdict; a failure is recorded as `llm_status: failed` and the unit
   falls back to the *conservative* deterministic outcome, visibly.
4. **Evidence, not authority.** The model is never a source. Every model statement that reaches a user cites
   captured evidence (quotes verified in the captured bytes; fact ids for synthesis).
5. **No model-controlled I/O.** No tools, no browsing, fixed endpoint; capture stays deterministic.

## 2. Components

```
                    ┌────────────────────────── deterministic (unchanged) ─────────────────────────┐
registry ─► identity gate ─► website operator ─► site capture (bytes+sha) ─► candidate extraction ─► V3.1 news rules
                                                                                          │                 │
                                                                                 hard rejects        published / soft-withheld
                                                                               (final, no LLM)              │
                                                                                                            ▼
                                                     ┌──────────── optional LLM stage (opt-in) ────────────┐
                                                     │ evidence packet (identity, relations, operator,      │
                                                     │ title, source text, item text, date evidence)        │
                                                     │   → cache lookup (content key)                        │
                                                     │   → Gemini generateContent, JSON schema, no tools     │
                                                     │   → validator: quotes ∈ source, date evidence, enums, │
                                                     │     publish needs category+subject+verified quote     │
                                                     └───────────────────────────────────────────────────────┘
                                                                                                            │
                                                                     policy (configurable arm) ─► claim + llm_assessment
```

* `llm/gemini.py` — provider (exists in this branch). Implements the existing `LLMProvider` interface.
* `llm_experiments/news_contract.py` — packet, schema, validator (exists; would move to `llm/news.py`).
* `llm_experiments/runner.py` — cache and call accounting (exists; the cache would become a run-level store under
  the snapshot directory so a replay is offline and byte-identical).
* `policies.py` — the arms; production would expose one: see §4.

## 3. Data model additions (additive, envelope-compatible)

On a `news_item` claim, when the LLM stage ran:

```json
"llm_assessment": {
  "status": "ok | failed | skipped_budget | cache_hit",
  "model": "gemini-3.1-flash-lite", "model_version": "3.1-flash-lite-05-2026",
  "prompt_id": "news-p2-evidence-v1", "prompt_sha256": "6c18…",
  "packet_sha256": "…", "content_category": "genuine_company_news", "subject_relation": "target_company",
  "decision": "publish", "validated_decision": "publish", "evidence_quotes": [{"quote": "…", "verified": "exact"}],
  "deterministic_decision": "published", "policy": "A_filter", "assessed_at": "…"
}
```

Withheld items keep their deterministic reason and gain `llm_assessment` only when the policy consulted the model.
Historical envelopes are never rewritten; a refresh with a different model/prompt version is a new assessment, and a
change in LLM verdict alone is recorded as `reassessed`, not as a company change.

## 4. Recommended policy if integrated

**Pending the independent result** (the evalg250 evaluation is incomplete; see results §5): the candidate design is
**Experiment A as a filter on V3.1's published items** (`A_filter`): it cannot add an item V3.1 would not publish, and
its cost is proportional to V3.1's output, not to the whole candidate pool. Whether it removes enough errors without
losing too much legitimate coverage is exactly what the unfinished evaluation must show.
The hybrid `C_hybrid` (LLM may rescue soft-withheld items) adds coverage and is the stronger result where a
company's own site is the only news source, but it lets the model's judgment *add* items; it should be a separate,
later opt-in after its own independent measurement.

Configuration:

```
SIGNALPOST_LLM=off|gemini        default off
SIGNALPOST_LLM_POLICY=A_filter   A_filter | C_hybrid
GEMINI_API_KEY=…                 env only
GEMINI_MODEL=gemini-3.1-flash-lite
SIGNALPOST_LLM_MAX_CALLS=…       hard cap per run; the run stops consulting the model when reached (recorded)
SIGNALPOST_LLM_MAX_USD=…         estimated-cost cap per run (from usageMetadata)
```

## 5. Failure behaviour

| Situation | Behaviour |
|---|---|
| No key / disabled | identical to V3.1 (tested: the run path does not import the LLM code) |
| API error, timeout, 5xx after retries | `llm_status: failed`; under `A_filter` the item is withheld as `llm_unavailable` *only if* the operator configured `fail_closed`; default `fail_open_to_v31` keeps V3.1's decision and marks it |
| Daily quota / budget reached | stop consulting; remaining items get `skipped_budget`; run continues |
| Invalid JSON / unverified quotes | treated as "uncertain"; counted in the report |
| Cache hit | identical verdict, `status: cache_hit`, no call |

## 6. Product UX (search application)

Investigated design; not built:

* **"Why is this news?"** — on each news item, a collapsible AI note: category, subject and the verified quotes,
  labelled "AI assessment (Gemini, prompt v…) — quotes verified in the captured page", linking to the snapshot.
* **Evidence-backed answers** — a question box scoped to *one company profile*: retrieval is the profile's claims
  (no web, no pretrained knowledge), the model returns statements with fact ids, and the same synthesis validator
  drops anything ungrounded. Answers show each cited fact inline; unanswerable questions return "not in Signalpost's
  evidence".
* **Comparison of two companies** — the deterministic comparison table stays primary; an optional narrative is
  generated from the two profiles' facts with derived (deterministically computed) differences.
* **What's New** — the deterministic change list stays primary; the LLM wording is optional. In this research the
  LLM added little over templates and misread one event field (see results), so it is not recommended yet.

The existing search and comparison workflows must not depend on any of this; every AI element is additive,
clearly labelled, and hidden when the LLM is off.

## 7. Privacy and compliance prerequisites for production

* Paid tier only (EEA users; free-tier content may be used for training and read by human reviewers).
* Data minimisation: the packet contains only the item's own text, capped (≤6,000 characters), never whole crawls.
* DPIA covering personal data in public website text (names in articles).
* Key in a secret store; rotation; per-project spend cap in Google Cloud.
