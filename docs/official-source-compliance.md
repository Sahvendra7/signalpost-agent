# Official source compliance (official-contract audit)

> Historical audit. **Final submission candidate:** `78d1c2f2be0decbb90311f4827b226752c74f317`. **Code under test
> for the final validation:** `4f827ee`, code-identical to `78d1c2f`. See `docs/final-submission-manifest.md`.

Audit date: 2026-10-03. Code audited: `403a9c1` (code identical to `c5c6a32`). Source keys (`BRIEF`, `EVAL`,
`SOURCES`, `PLAYBOOK`, `HARNESS`, `PAGE`, `KIT`, `SAMPLE`, `RULES`) and the SHA-256 of each fetched document are
listed in `docs/official-requirements-matrix.md`.

**Permission rule used here.** A source is **PERMITTED** only when an official Builderr resource names it, or
names its class, as allowed for the way we use it. Anything else is **UNCONFIRMED**. Permission is never assumed
silently. A licence is attributed only where a document states it, and the document is named.

## Official source policy in force

* Preferred official records (`SOURCES`): "Brønnøysundregistrene Enhetsregisteret bulk data and entity API for
  identity, legal form, address, industry and registered employee count"; "Regnskapsregisteret API and
  annual-account copies for filed financial data and history"; "Official roles endpoints for management and board
  roles"; "Official subunit records for registered workplaces". "Official data is the identity anchor. It does not,
  by itself, identify the public brand or website."
* Company-owned (`SOURCES`): "Verified official website"; "Sitemap, news, investor, careers, location and contact
  pages"; "Structured data embedded by the company"; "Social or video profiles linked by the verified company
  site, subject to the destination platform's access terms".
* External (`SOURCES`): "Official or licensed platform APIs"; "Search APIs used to discover candidates"; "Public
  pages whose terms and robots policy permit the submitted access pattern"; "Licensed news, review, jobs, traffic or
  company-data feeds".
* Restricted (`SOURCES`, `PLAYBOOK`): "Do not scrape a platform when its terms, robots policy or applicable law
  prohibit the submitted method. This includes treating unofficial LinkedIn, Meta, Glassdoor, Indeed or Google
  clients as automatically acceptable". Unofficial clients "cannot be the sole support for a published claim".
* Credentials (`PAGE`): "What we cannot use is a credential tied to your own account on another service".
* Source ladder (`PLAYBOOK` §4): official registers → verified company-owned sites and feeds → official or licensed
  platform APIs → permitted public pages with recorded terms and provenance → search for candidates only.

## Source-by-source audit

| Source | Permitted? | Legal / licence basis | Rate limit | Identity strength | Evidence quality | Current use |
|---|---|---|---|---|---|---|
| **Brreg Enhetsregisteret entity API** `/enhetsregisteret/api/enheter/{org}` | **PERMITTED** (`SOURCES`, named) | NLOD 2.0, as stated in `KIT` `docs/external-connectors.md` ("Its open data is available under NLOD 2.0"). The contract text itself does not restate the licence. | None published by Builderr. Brreg's own limit: UNCONFIRMED. We do not throttle on the client (≈4–5 Brreg requests/s at 8 workers). | Authoritative. Keyed by org number, and a response for any other number is discarded (`_apply_live_identity`). | Raw JSON bytes, SHA-256, retrieval time, field-path span. Bytes stored under `--snapshot-dir`. | **Production** (`registry_live`): name, form, industry, employees, addresses, founded and registered dates, activity, purpose, bankrupt and liquidation flags, registry website and e-mail (the latter two only as discovery pointers) |
| **Brreg Enhetsregisteret bulk CSV** `/enheter/lastned/csv` | **PERMITTED** (`SOURCES`, named) | NLOD 2.0 (`KIT` doc) | n/a (one download) | Authoritative snapshot | Whole-file SHA-256 plus row key | **Optional** (`--bulk`). The declared command does not use it. `EVAL`: Builderr "provides the frozen official registry snapshot" (delivery method not published). |
| **Brreg Regnskapsregisteret** `/regnskapsregisteret/regnskap/{org}` | **PERMITTED** (`SOURCES`, named) | NLOD 2.0 for Brreg open data (`KIT` doc says so for the entity registry). Explicit licence wording for the accounts API in Builderr text: UNCONFIRMED. | None published. | Keyed by org number | Raw JSON, hash, span `regnskap[id].field=value (period, currency)` | **Production** (`financials`): 7 figures per returned period (2023–2025 observed) with reporting period, currency and account type |
| **Brreg annual-account copies** `/aarsregnskap/kopi/{org}/aar` and `/{year}` | **PERMITTED** (`SOURCES`, named) | as above | "roughly 30 requests/minute" (`KIT` `docs/norway-sources.md`, starter guidance) | Keyed by org number | Year list JSON. The PDFs were image-only in our test (0 extractable facts in 100). | **Not in production** (`financial_history` is not in `DEFAULT_MODULES`) |
| **Brreg roles** `/enheter/{org}/roller` | **PERMITTED** (`SOURCES` "Official roles endpoints") | as above. Personal data: names are published in a company context. | None published. | Keyed by org number | Raw JSON, hash, span `roller[CODE]=name`. Birth dates (`fodselsdato`) and `erDoed` are removed before hashing and storage (`docs/crawl-safety-and-privacy.md`); neither snapshots nor envelopes contain them. | **Production** (`roles`): active role holders, `roles_last_changed` |
| **Brreg subunits** `/underenheter?overordnetEnhet={org}` | **PERMITTED** (`SOURCES` "Official subunit records") | as above | None published. | Parent org number in the query; each subunit carries its own number | Raw JSON, hash | **Production** (`locations`) |
| **Brreg group structure** `/konsernstruktur/{org}` | **PERMITTED** (part of the Enhetsregisteret API; listed in `KIT` `docs/norway-sources.md` "Official corporate relationships") | as above | None published. | Official | Raw JSON, hash | **Production** (`group`) |
| **Brreg update history** `/oppdateringer/...` | **Source PERMITTED** (Enhetsregisteret API). **Category mapping UNCONFIRMED** (not named for "dated public activity") | as above | None published. +1.8 requests per company measured. | Keyed by org number | Raw JSON, hash | **Experiment only** (`experiments/brreg_activity.py`), not in production |
| **Website discovery: registry `hjemmeside`** | **PERMITTED** as an official pointer (`SOURCES`). It "does not, by itself, identify … the website", so the site must still be verified. | Official registry field | n/a | Pointer only. Verification is done by the site gate. | Registry claim `registry_listed_website` | **Production** |
| **Website discovery: registry e-mail domain** | **PERMITTED** as candidate generation (derived from an official record). Publication evidence comes from the site. | Official registry field | n/a | Pointer only | — | **Production** (V2 `site_research`) |
| **Website discovery: `<legal-name>.no` DNS guess** | **UNCONFIRMED (method not named, not prohibited)**. It generates candidates only, like the permitted "Search APIs used to discover candidates". No third-party content is used; facts come only from the company's own page after the gate. | System DNS resolution | One DNS lookup per candidate | Pointer only. 18 of 27 newly accepted sites (V2) came this way; all were audited correct. | — | **Production** (V2 `site_research`) |
| **Company websites** (home, about, contact, careers pages; robots.txt) | **PERMITTED** (`SOURCES` "Verified official website"; "Public pages whose terms and robots policy permit the submitted access pattern") | Public pages of the company itself. Per-site terms are **not checked** (UNCONFIRMED per site). robots.txt is honoured per RFC 9309 (401/403, 429, 5xx and network failure mean disallow). `Crawl-delay` is honoured within the company budget (`docs/crawl-safety-and-privacy.md`). | Our budget: ≤30 requests and 60 s per company, 15 s per request, 2 attempts, 3 MB per page. Public hosts only, and redirects are re-checked. | C1 org number on the site (strong); C2 legal name + registered address + own-domain mailbox (medium-strong). Fan, directory and parked sites are rejected. | Page bytes, SHA-256, retrieval time, quoted span. Stored under `--snapshot-dir`. | **Production** (`website` V1 gate + `site_research` V2) |
| **Site-linked social profiles** | **PERMITTED as links** (`SOURCES` "Social or video profiles linked by the verified company site, subject to the destination platform's access terms"). `SAMPLE` marks such handles `rightsStatus: "approved"`. | Link taken from the company's own page. The platform is **never fetched**. | 0 platform requests | Inherits the site verification, plus a handle check (`assess_social_identity`). Sharer and intent links are rejected. | Evidence is the company page that contains the `href` | **Production** |
| **Company-site feeds, sitemap, news, JSON-LD** (RSS/Atom, `sitemap.xml`, dated pages, `JobPosting`) | **PERMITTED** (`SOURCES` "Sitemap, news, investor, careers … pages"; "Structured data embedded by the company") | As for company websites | Within the per-company budget above | Only on a verified site | Bytes and hash. Date kind recorded; only source-stated dates are published. | **Production** (dated activity, careers page, job postings) |
| **NAV job feed** (arbeidsplassen public feed) | **UNCONFIRMED.** No official resource mentions NAV. The general classes "Official or licensed platform APIs" / "Licensed … jobs … feeds" might apply, but NAV's terms and token policy are not covered. The token is shared and rotating, and the credential rule (`PAGE`) needs checking. | Not established | Not established | Org-number match on the posting (strong when present) | Measured: 1–2 hiring companies per 100 | **Experiment only**, not imported by the run path |
| **Brave Search API** | Class **PERMITTED** for candidates only (`SOURCES`), but **not usable** with our own key (`PAGE` credential rule). Usable only with a Builderr-supplied key. | Brave terms (storage rights) not reviewed | Paid per query | Candidates only, never evidence | — | **Not used** (experiment code only) |
| **LinkedIn, Meta, Instagram, X, TikTok, YouTube, Glassdoor, Indeed, Google** | **RESTRICTED** (`SOURCES`, `PLAYBOOK`) unless accessed through an official or licensed API | — | — | — | — | **Never fetched**. Only site-linked URLs are recorded. |
| **Directories and aggregators** (Proff, Purehelp, 1881, …) | **UNCONFIRMED** (would need "terms and robots policy permit the submitted access pattern") | — | — | — | — | **Never fetched**. Rejected as website candidates. |
| **publicsuffix.org** (via `tldextract`) | **Not contacted** | Public suffix list (MPL-2.0), bundled snapshot of the pinned `tldextract==5.3.2` | None | n/a | n/a | **Pinned and declared** (`docs/dependencies.md`); no runtime fetch. |

## Findings

1. **No source in the production run is prohibited.** Every fetched source is named or class-named in `SOURCES`.
   The only exception is the `<legal-name>.no` DNS guess, which is a candidate-generation method with no
   third-party content and is not named either way.
2. **Conservative choices that the official text allows:**
   * Site-linked profiles are recorded but never fetched. `SOURCES` permits recording them, and fetching is subject
     to platform terms. Keep.
   * Brreg update history is kept out of production. The source is permitted, but its category mapping is
     unconfirmed.
   * The annual-account filing-year list is not fetched. It is permitted by `SOURCES` ("annual-account copies … and
     history") but rate limited (≈30 per minute in starter guidance). At 1,200 companies that is ≈40 extra minutes
     at the guideline rate, which makes it unaffordable without knowing the budget.
3. **Gaps to close before submission:**
   * Declare the user agent and the per-company crawl budget in the run documentation (`KIT` README: "Follow each
     source's terms, robots policy, rate limits and licence").
   * Honour `Crawl-delay` (capped) and add a small client-side token bucket for `data.brreg.no`. No Brreg limit is
     published, and a 429 storm would degrade filings and roles to `failed` without voiding the batch, because a
     "shared-source failure" is void only when Builderr attributes it to the shared source.
   * Pin `tldextract` to its bundled suffix list (`TLDExtract(suffix_list_urls=())`) so the run makes no undeclared
     request and registered-domain parsing cannot drift between runs.
   * Decide on the birth dates in stored raw roles bytes (keep and declare, or redact). This is starter guidance,
     not a contract rule.
4. **Builderr's pool likely contains facts we cannot lawfully match.** `SAMPLE` includes LinkedIn company pages,
   posts and guest-API job postings marked `rightsStatus: "experimental"` with `sourceClass` `professional_network`
   or `job_board`. If those are in the verified union, our recall on those families is capped. This is a scoring
   observation, not a reason to scrape.

## LLM policy audit (step 10)

| Question | Official answer | Our state | Verdict |
|---|---|---|---|
| Is LLM use explicitly allowed? | Yes. `PAGE`/`PLAYBOOK`: "You think you cannot use an LLM. You can." | Layer implemented, off | Compliant |
| Model or provider restrictions | None published. Must be declared (`BRIEF` Submit "models/APIs/licences") and frozen (`HARNESS` §6 "prompts, models and model versions"). | Provider-agnostic. Model id is passed through verbatim. Two wire formats (`openai_chat`, `anthropic_messages`). | Compliant. The model **version** must be pinned and declared when it is enabled. |
| Budget | "Each run has a small external API budget". The amount is NOT PUBLISHED. | Hard caps: ≤2 calls per company, `LLM_MAX_CALLS_PER_RUN` (default 1,000), per-company 60 s, concurrency 2 | Viability depends on the unpublished budget |
| Key provisioning | "if you need a model key for scoring, ask and we will supply one" | No key in the repository. `LLM_API_KEY` is read from the environment only. | Compliant |
| Can the evaluator inject a key? | `EVAL`: "server-side secrets supplied through documented environment variables only" | `LLM_ENABLED`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_API_FORMAT` are documented in `docs/llm-layer.md` | Mechanism compliant. **But the run command never loads the layer**, so an injected key would have no effect until it is wired (e.g. load it when `LLM_ENABLED=true`). |
| 0–2 calls per company viable? | Not determinable (budget unpublished) | Estimated (not measured) ≈0.2–0.25 calls per company in `verified_site` mode (≈240–300 per 1,200 batch). With `LLM_SYNTHESIS=all` it is ≈1,500 (one synthesis call per company plus extraction on verified sites), which the default `LLM_MAX_CALLS_PER_RUN=1000` would truncate. | Ask Builderr for the call or token budget before enabling |
| Evidence-backed extraction acceptable? | `PLAYBOOK` §6: "model extraction last. Validate every output." "An LLM may summarise supported claims or propose candidates. It must not decide exact identity, invent a missing field, or silently override deterministic evidence." | Runs only after the deterministic gate. Spans are verified verbatim on re-hashed captured pages. Conflicts are rejected. It never overrides deterministic claims. | Fits the rule |
| Does synthesis fit the rules? | Synthesis (12 pts) must explain "without making unsupported claims" and "with sources for its conclusions" | Synthesis cites fact ids; numbers and names are validated against cited facts; `presentation_only` | Fits. A **deterministic** template synthesis meets the same rule at zero cost and zero non-determinism, which is the safer first step. |
| Reproducibility risk | "Re-running the same snapshot is idempotent" (`EVAL`) | LLM output may vary between runs. Extraction claims could then create false changes or duplicate records. | When enabling: temperature 0, cache by `(page sha256, prompt version, model)`, and exclude LLM fields from change detection unless the cited page hash changed. |

**Decision: keep the LLM disabled for the first submission.** Enable it only after (a) Builderr confirms the model,
key and budget, (b) the run command loads the layer from documented env vars, and (c) the A/B test shows no
precision loss and no false changes on rerun.
