# V3.2 research: Gemini API compatibility, cost, security and privacy

Status: research only, on branch `experiment/v3.2-gemini` (local; not pushed). The release `v3.1-candidate-2`
(commit `139e23c`, code `334a085`) is unchanged; nothing below is used by its run path.

All statements were checked on **2026-11-04** against Google's documentation and against the live API with the
configured key. They change often; re-check before any integration.

## 1. Environment and key handling

| Check | Result |
|---|---|
| Key variable | `GEMINI_API_KEY` present (value never printed; only its presence and that it is a plain token were checked) |
| Other Google variables | none (`GOOGLE_API_KEY`, `GOOGLE_GENAI_API_KEY` not set) |
| Billing tier | **Free Tier.** Verified by one request to `gemini-3.1-pro-preview` (a model with no free tier): `429 RESOURCE_EXHAUSTED`, quota ids `GenerateContentInputTokensPerModelPerDay-FreeTier`, limit 0. No billing account is linked, so no call in this research could be billed. Exceeding a free-tier limit returns 429; it does not bill. |
| Transport | Native REST `POST /v1beta/models/{model}:generateContent`, key only in the `x-goog-api-key` header (never in a URL, log, report, fixture or commit). Errors are stored key-redacted and truncated. A scan of every new file for the key value found none. |

## 2. Models (live `models.list` + docs, 2026-11-04)

| Model | Status (docs) | Context in / out | Free tier | Standard price in / out per 1M tokens | Used here |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` (`3.5-flash-lite-07-2026`) | Stable | 1,048,576 / 65,536 | yes, **500 requests/day** (429 message: `generate_content_free_tier_requests limit 500`); slow on the free tier (median 36 s, p90 80 s) | $0.30 / $2.50 | diagnostic + model comparison |
| `gemini-3.1-flash-lite` (`3.1-flash-lite-05-2026`) | Stable | 1M / 65k | yes, **500 requests/day** (same 429 message); median 8 s; occasional 503 "overloaded" | $0.25 / $1.50 | **primary** |
| `gemini-3.6-flash` (`3.6-flash-07-2026`) | Stable | 1M / 65k | yes, **≈20 requests/day** (stopped at 21) | $0.75 / $3.75 → $1.50 / $7.50 from 2027-01-01 | small comparison |
| `gemini-3-flash-preview` | Preview | 1M / 65k | yes, **≈20 requests/day** | $0.50 / $3.00 | small comparison |
| `gemini-3.8-flash` | New | 1M / 65k | yes, **20 requests/day** (429 message: `generate_content_free_tier_requests limit 20`); rejects `thinkingLevel: MINIMAL` | $0.75 / $3.75 → $1.50 / $7.50 | no successful call |
| `gemini-2.5-flash-lite` | listed, not deprecated in docs | — | **404 "no longer available to new users"** | $0.10 / $0.40 | unusable |
| `gemini-2.5-flash`, `gemini-2.5-pro` | Deprecated; requests route to 3.5 Flash-Lite / 3.8 Flash on 2026-12-01 | — | — | — | not used |
| `gemini-4-argon`, `gemini-3.1-pro-preview` | flagship / preview | 1M | **no free tier** | $2–4 / $10–20 | not used |

**Free-tier daily caps were the binding constraint of this research**: 500 requests/day/model for the two Flash-Lite
models and ≈20 for every Flash model, which ruled out a full multi-model comparison in one day. Free-tier per-minute limits were also hit occasionally (`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`) and
retried after the server's `RetryInfo` delay. Limits are per project, not per key; daily quotas reset at midnight
Pacific time.

## 3. Capabilities relevant to Signalpost

* **Structured output.** `generationConfig.responseMimeType = application/json` with `responseJsonSchema` (JSON Schema
  subset: types, enum, required, nullable via type arrays, min/maxItems). Constrained decoding guarantees syntactically
  valid JSON of the schema's shape, **not** correct content: every value is re-validated in code (quotes, dates,
  decisions). `minLength`/`maxLength` and similar are silently ignored by the API. All 752 successful calls in this
  research returned schema-valid JSON (0 non-JSON responses).
* **Thinking.** Gemini 3.x takes `thinkingConfig.thinkingLevel` (MINIMAL/LOW/MEDIUM/HIGH); 2.5 models take
  `thinkingBudget` (the provider maps it). Thinking content was never requested or stored; only its token count.
* **Determinism.** `temperature`, `topP` and `topK` are *silently ignored* on Gemini 3.6 Flash and newer. Repeat
  calls can differ, so reproducibility comes from the response cache, not from sampling settings.
* **Interactions API.** Google now recommends `POST /v1beta/interactions` for new code; `generateContent` remains a
  documented, non-deprecated method. The provider isolates the wire format in one class.
* **No tools.** The provider sends no tools (no search grounding, URL context or code execution), and the base URL is
  fixed: the model cannot cause any network access.

## 4. Cost model

Prices are the Standard (paid) tier from the official pricing page; output prices include thinking tokens. **Actual
spend in this research: $0** (Free Tier). "Paid-equivalent" figures are what the same calls would cost on a billed
project; they are computed per call from `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`,
`thoughtsTokenCount`).

Measured per news item (evalg250 final records): median 2,213 input and 238 output tokens with MINIMAL thinking, i.e.
**$0.00095 per item on `gemini-3.1-flash-lite`** (≈$0.0013 on `gemini-3.5-flash-lite`). evalg250 has 135 candidate
news items and 64 V3.1-published items per 100 companies, so per 100 companies: Experiment B/C (classify the
candidate pool) ≈ **$0.13**, Experiment A (classify only V3.1's items) ≈ **$0.06**; at 1,200 companies ≈ $1.5 / $0.7.
Total paid-equivalent value of every call made in this research (752 successful calls): ≈ $0.88; actual spend $0. Cost is dominated by input; the prompt (~1,100 tokens) is the same for every
item, so implicit/explicit context caching would cut it further. The 2027-01-01 price rise applies to 3.6/3.8 Flash,
not to 3.5 Flash-Lite.

## 5. Data handling and privacy

From the Gemini API Additional Terms (read 2026-11-04):

* **Unpaid (free tier):** Google uses prompts and responses "to provide, improve, and develop Google products";
  "human reviewers may read, annotate, and process your API input and output"; "Do not submit sensitive,
  confidential, or personal information to the Unpaid Services."
* **Paid:** prompts and responses are not used to improve products; they are logged "for a limited period of time"
  for abuse detection; processed under Google's data-processing terms.
* **EEA, Switzerland, UK:** "You may use only Paid Services when making API Clients available to users in the
  European Economic Area" — and for these regions the paid data terms apply to all services. **Norway is in the EEA:
  a Signalpost feature using Gemini for Norwegian users must use a billed project.**

What this research sent: public registry data (names, organisation numbers, registered relationships) and the text
of public pages on the companies' own websites. That text can contain personal data (employee names, quotes,
photos' captions). It is public, but under the free-tier terms it may be reviewed by humans and used for training.
That was acceptable for a time-boxed research run on public data; it is **not** acceptable for production, which needs
the paid tier, a data-processing assessment, and minimisation (send only the item's own text, as here, never whole
crawls).

## 6. Security assessment

| Risk | Control in this code | Status |
|---|---|---|
| Key leakage | env-only; header-only; `repr=False`; error messages redacted (exact key and `AIza…` pattern); never in reports; repository scanned | no leak found |
| Prompt injection from web text | page text fenced as untrusted data; instruction to ignore embedded instructions and set `injection_detected`; `injection_detected` blocks publish; decision can only be lowered by validation; model has no tools | contained (an injected "publish" can at worst make the model *say* publish; validation still requires category, subject and verified quotes) |
| Fabricated quotes / facts | every quote checked against the supplied text; unverified quote ⇒ no publish | enforced |
| Fabricated dates | a date is kept only if its evidence passage occurs and states that date; the pipeline's deterministic date is never replaced | enforced |
| Model-controlled network access | none: fixed endpoint, no tools; the article capture is deterministic, in-scope URLs only, robots-checked, public addresses only, no social hosts | enforced |
| Silent fallback | an API failure is recorded per item and counts as "uncertain" (never publish); cache misses offline are recorded as `cache_miss_offline` | enforced |
| Cost runaway | `--live` and an explicit `--max-calls` are required; a daily-quota 429 stops the run (circuit breaker) | enforced |
| Release contamination | separate branch; experiment packages not imported by the run path (test); release tests unchanged | verified |
