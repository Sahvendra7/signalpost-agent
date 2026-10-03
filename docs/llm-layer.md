# Optional LLM layer (prepared, not enabled)

Status 2026-10-03: implemented and tested offline with mocked model responses. **Not enabled anywhere.**
No provider is hard-coded, no API key is used, and the evaluator-facing command
(`scripts/run_competition_batch.py`) does not load the layer at all. No score change is claimed. The
A/B measurement runs only after Builderr supplies model details.

## Guarantees

| Requirement | How it holds |
|---|---|
| LLM off ⇒ exactly V2 | `run_batch(..., llm_layer=None)` is the default. A disabled layer (`LLM_ENABLED` unset/false, or any credential missing) takes the same branch. Test: envelopes, profiles and report are equal to V2's, field for field (timestamps and timings aside). |
| Never the identity authority | The layer runs only on companies whose website the deterministic gate (`site_identity.classify_site` / v1 registry gate) already verified. Model output never reaches the gate. Profiles the model finds still pass `assess_social_identity`. Test: a fan site gets zero LLM calls even with a model that labels everything FIRST_PARTY. |
| Classification cannot override the gate | The model's page class (FIRST_PARTY / THIRD_PARTY / FAN_COMMUNITY / DIRECTORY / AMBIGUOUS, with evidence spans) only *removes* LLM output: a page not classified FIRST_PARTY with a span found on that page yields no LLM facts. Disagreements with the gate are recorded, never acted on. |
| No new retrieval | Pages come from the run's `SiteSession` cache (`cached()` is read-only) and are re-hashed against the recorded `content_sha256` before use. A mismatch means the page is not sent. |
| Provenance | Every LLM-derived claim cites the captured page: `source_url`, `retrieved_at`, `content_sha256`, plus the verbatim `evidence_span` (also the evidence entry's `claim_span`). Claims carry `derivation: "llm_extraction"` and `llm_model`. The model is never a source. |
| LLM failure never fails a company | The provider never raises (it returns error codes). The layer catches its own exceptions, and the pipeline has one more boundary around it. Any failure leaves the deterministic profile untouched (`profile.llm.status = "fallback"`). |

## Validators (deterministic, in `llm/tasks.py`)

Everything the model returns is re-checked against the same text it was given. Failures are rejected with
a reason code and counted. Nothing is repaired by guessing.

* **Evidence span**: required. It must be 3–300 characters and occur in the cited page (case- and whitespace-folded).
* **Value support**: every word (≥3 characters) and every whole number in a value must occur in its span.
* **Dates**: kept only when the span states that exact calendar date. Supported forms: ISO,
  `12.09.2026`, `12. september 2026`, `September 12, 2026`, in Norwegian and English. Otherwise the date is
  dropped (`date_if_explicit: null`). A dated activity without a verifiable date is not published.
* **Profiles**: LinkedIn, Facebook, Instagram and YouTube only. The URL must be an `href` on the cited
  verified page. A URL mentioned only in text is rejected. Each profile is normalized with V2's
  `normalize_social_url`, which rejects sharer links. Profiles V2 already found are not re-added.
* **Roles**: a fixed synonym table decides the category whenever it knows the title, so `Daglig leder`,
  `CEO` and `Chief Executive Officer` all map to `ceo`. The model's category is used only for titles not
  in the table, and only from the closed set. Equal (name, category) statements are merged and keep every
  span. Different names are never merged (`Ingrid Berg` ≠ `Ingrid Bergström`).
* **Conflicts**: single-valued facts that disagree are all rejected, for example a founded year of 2009
  and of 2011. A website CEO or chair who does not match the registry role holder is rejected
  (`conflicts_with_registry_role`).
* **Synthesis**: a presentation layer, emitted as `company_synthesis` with `presentation_only: true`. It
  is never a claim. Each section must cite fact ids. Every number, e-mail, URL and capitalised name it
  contains must appear in the facts it cites. Sections without supporting facts are omitted. The prompt
  forbids inventing anything, inferring unsupported facts or adding facts absent from the evidence. It
  also requires the model to preserve uncertainty and omit unsupported sections. Completeness is the
  share of sections, among those with available facts, that survived validation.

## Call budget: 0–2 calls per company

```
verified website? ── no ──> 0 calls (synthesis too, unless LLM_SYNTHESIS=all)
      │ yes
deterministic extraction (V2, unchanged)
      │
extraction_triggers(): no deterministic description / role words in text /
                       explicit dates but no V2 activity / social host in HTML but no V2 profile
      ├─ none ──> skip call 1
      └─ any  ──> call 1: one combined request for page classification, facts, profiles,
                          dated activities and role normalization, over ≤3 captured pages
                          (homepage, then news-like pages), ≤ LLM_MAX_INPUT_CHARS characters
call 2: synthesis from verified claims only (≥3 facts), if LLM_SYNTHESIS allows
```

On the V2 measurements (11.5% of companies have a verified site), the default `verified_site` mode
works out to an expected ≈0.2–0.25 calls per company. This is an estimate, not a measurement.

Hard limits are enforced in code. The values below are defaults.

* `LLM_MAX_CALLS_PER_COMPANY`: default 2, capped at 2.
* `LLM_MAX_CALLS_PER_RUN`: default 1000.
* `LLM_COMPANY_BUDGET_S`: default 60. The time for LLM work on one company, retries included.
* `LLM_TIMEOUT_S`: default 20. The timeout for each request.
* `LLM_MAX_RETRIES`: default 1. Retries happen only on transport errors, 429 and 5xx, and never after the
  call's deadline.
* `LLM_MAX_CONCURRENCY`: default 2. This is a semaphore shared by all batch workers.
* `LLM_MAX_RESPONSE_BYTES`: default 64 KiB. A larger response is discarded.
* `LLM_MAX_OUTPUT_TOKENS`: default 1200.
* Each response list is capped at 40 items.

## Configuration

`LLMProvider` → `DisabledProvider` (default) | `ConfigurableProvider`. The provider is chosen only by
environment:

```
LLM_ENABLED=false          # true/1/yes, and the three below must all be present, else disabled
LLM_MODEL=
LLM_API_KEY=               # never logged; report.llm.config shows only the base URL host
LLM_BASE_URL=              # e.g. https://host/v1
LLM_API_FORMAT=openai_chat # openai_chat -> {base}/chat/completions | anthropic_messages -> {base}/messages
LLM_SYNTHESIS=verified_site  # verified_site | all | off
```

The two wire formats cover most hosted and self-hosted endpoints. Adding another means adding one
request/response mapping in `ConfigurableProvider`. Requests use `temperature: 0` and ask for a single
JSON object. A fenced ```json block is tolerated, but prose is a failure (`model_output_not_json_object`).

## A/B experiment (when model details arrive)

```bash
# one arm at a time
uv run python scripts/run_llm_experiment.py --llm-disabled --organisations S.jsonl --out out/llm-ab/S/disabled
LLM_ENABLED=true LLM_MODEL=... LLM_API_KEY=... LLM_BASE_URL=... \
  uv run python scripts/run_llm_experiment.py --llm-enabled --organisations S.jsonl --out out/llm-ab/S/enabled

# or both arms plus the comparison, on the same samples as docs/v2-results.md
uv run python scripts/compare_llm_ab.py --sample fixed=... --sample s1=... --out out/llm-ab
```

`--llm-enabled` refuses to run with an incomplete configuration, so a mislabeled arm is impossible.
`comparison.json` reports the following for each sample:

* total LLM calls, by task and per company
* input and output tokens (when the endpoint reports them)
* runtime for each arm
* facts added: available claims B − A, and LLM-derived claims by field
* public-footprint companies for each arm, and how many reach it only through LLM claims
* synthesis count and mean completeness
* rejected LLM items by reason, and LLM failures by reason
* precision:
  * `llm_grounding_failures`: each LLM claim's span is searched for again in the snapshot bytes. Must be 0.
  * `llm_identity_changes`: `official_website` differs between the arms. The LLM cannot cause this, so
    a non-zero value means live-web drift between the two runs, and each case is listed.
  * `wrong_company_llm_claims`: left `null` until the manual audit of `enabled/llm-audit.jsonl`.

## Tests

`tests/test_llm_layer.py` runs offline with fixtures in `tests/fixtures/llm/`:

* genuine page
* fan page
* directory
* ambiguous reseller page
* multilingual team page
* multiple social links
* dated news
* malformed HTML
* conflicting content

The tests cover:

* hallucination rejection
* missing dates staying missing
* social link extraction
* fan and directory pages yielding no LLM facts, and getting no calls at the pipeline level
* evidence spans and provenance on every item
* fallbacks for HTTP errors, timeouts, non-JSON output, exceptions and hash mismatches
* call budgets
* both wire formats, the retry limit and call deadline, the response size limit, and bounded concurrency
* the A/B metric computation, including detection of tampered spans
* disabled-mode equivalence with V2
