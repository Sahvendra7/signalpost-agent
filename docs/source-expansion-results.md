# Source-expansion results

Status 2026-10-02: **the experiments are built and tested; the live measurements have NOT been run.**
The development container's egress policy denies `data.brreg.no`, `pam-stilling-feed.nav.no`,
`builderr.ai`, company websites and `api.search.brave.com` (every request returns proxy 403). The
harness was run end-to-end anyway and correctly reports every source as `UNMEASURED`
(`out/experiments-offline/results.json`); it never reports an unreachable source as zero gain.

To produce the measured version of this table, run from a machine with normal internet access:

```bash
uv sync
curl -L https://builderr.ai/signalpost-company-universe-2025.jsonl.gz -o signalpost-universe.jsonl.gz
uv run python scripts/run_source_experiments.py --universe signalpost-universe.jsonl.gz --count 100 --out out/experiments
# optional, after E1–E4: BRAVE_SEARCH_API_KEY=... uv run python scripts/run_source_experiments.py --organisations out/experiments/sample.jsonl --skip activity,filings,nav --search --out out/experiments-search
```

No permanent architecture choice is made from this table until its *Measured* cells are filled.

## Value legend

- **Measured**: from `results.json` on 100 sampled companies. Currently `pending` everywhere.
- **By design**: exact consequence of the request plan in code (request counts, dollar cost).
- **Documented**: stated by the provider's own documentation or source code (cited below).
- **Expected**: reasoning, explicitly not evidence; listed so the measurement can confirm or refute it.

## Summary table

| Source | Coverage gain (area) | Facts gain | Requests / company | Latency / company | Cost / 1,000 companies | Precision risk | Evidence quality | Implementation cost | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| **W0. Footer identity capture** (bug fix, already applied) | websites: Measured pending. Expected: more registry-listed sites verified by org number instead of left `ambiguous` | website facts on newly verified sites | **0 extra** (by design) | ~0 (parsing) | $0 | **Lower** than before: more decisions rest on the org number | Same page bytes and hash | Done (10 lines) | **Keep** |
| **E2a. Full open-accounts fields** (same response) | filings: 0 (baseline already fetches it) | +8 values/company where filed: sales, operating costs, wage costs, net financial items, fixed/current assets, cash, short/long debt, plus audit opt-out and small-company flags (documented schema) | **0 extra** (by design) | 0 | $0 | None (org-keyed; record org checked) | Exact JSON bytes, reporting period per record | Small | **Integrate** (highest facts-per-cost; no coverage gain) |
| **E1. Brreg update feed** `/oppdateringer/enheter` (+ subunits) | hiring/public activity: Measured pending. Expected: dated event for most of the universe (feed covers entity creation and changes; old rows typed `Ukjent`) | events with date, type and, since 2025-11-13, field-level `endringer` | **1** (+1 when the company has subunits; pages of 100) (by design) | 1 Brreg JSON call; measured pending | $0 | **None**: keyed by org number, each row's org number re-checked | Official, exact bytes, dated, change-typed | Small (module exists) | **Integrate if measured coverage ≥ 50% of companies** with a dated event. It is the only zero-cost source that can cover the activity area for no-website companies. Caveat: whether Builderr's pooled "public activity" counts registry changes is `[OPEN]` |
| **E2b. Filing-year list** `aarsregnskap/kopi/{org}/aar` | filings (multi-year): Measured pending. Expected high: universe = 2025 filers | list of up to 15 filed years + official copy URL per year | **1** (by design) | Shares a per-IP rate limit (bucket4j, 3 tiers, capacities are deployment secrets). Starter observed ≈30/min, so **2.1 s serial each** → +3.5 min per 100 companies | $0 | None | Official JSON bytes | Small | **Integrate selectively** once the measured rate limit allows it within the run budget |
| **E2c. Latest annual-account PDF copy** | filings: none beyond E2b | PDF existence, page count and hash for the latest year; **no figures** | **1** (rate-limited, same bucket) | +2.1 s serial plus download (scan PDFs are large) | $0 | None | Official bytes and hash; **image-only**: Brreg builds copies with `tiffToPdf` (TIFF page images), so text extraction is expected to yield ~0 characters (documented in Brreg's source) | Small to fetch; **OCR would be needed** for any content, so not built | **Fetch-and-hash only if Builderr's PDF matching rewards it**; do not parse. Measure pdf_text_parsed_rate to confirm the image-only finding |
| **E2d. Prior-year structured accounts** `regnskap/{org}?år=Y-1` | filings (multi-year): Expected **0**: open API = latest year only; the 3-year closed part is for public authorities (documented) | — | 1 probe | 1 call | $0 | None | — | Done (probe) | **Drop** unless measurement refutes |
| **E3. NAV job feed** (pam-stilling-feed) | hiring: Measured pending. Expected low: 79% of the frozen sample has no registered employees | active ads verified by `employer.orgnr` = company or a registered subunit | Shared scan: one feed pass per run (≈ pages of 10,000 headers covering 6 months) + 1 detail per name candidate (by design). Full org-number index would cost pages + one request **per active ad** | Shared scan once per run (size measured pending) + one detail call per candidate | $0 | Low **after** orgnr verification (name matches with another orgnr are rejected and counted); names-only would be high | Official NAV JSON, published/expires dates, ad link | Medium (module exists) | **Do not integrate yet.** Public token is documented "for experiments" and rotates; production use requires registering with NAV for a private token the evaluator would not have. Needs a rights decision (below) |
| **E4. Non-search discovery** (subunit `hjemmeside`, open-record e-mail domain if present, NAV-verified employer homepage, `<legal-name>.no` guesses) | websites for the ~86% without a registry URL: Measured pending. Expected small: subunit sites are rare; e-mail is likely not in the open record (the harness inventories the fields) | website + downstream site facts on verified sites | 1 (entity record) + ~2–10 per candidate crawled (robots + homepage + up to 4 pages); guesses cost a DNS lookup first | Crawl-bound, measured pending | $0 | **Medium**: guessed domains have no endorsement, so they need the **strict gate** (org number on page, or exact name + registered postcode + street) | Page bytes and hash; identity reason recorded | Small–medium (module exists) | **Measure first.** Keep official pointers; adopt guesses only if verified/ambiguous ratio is high and adversarial audit finds 0 wrong sites |
| **E5. Brave Search** (optional, never mandatory) | websites: Measured pending, per strategy A–E | as E4 | 1 query + ≤3 candidate crawls | ≈ query latency + crawls | **$5.00** per 1,000 queries per strategy (Brave list price, $5 free credit/month) | Medium–high without gate; candidates only, strict gate required | Same as E4; search output itself is never evidence | Small (interface + provider exist) | **Optional, selective**: only for companies E1–E4 left without a verified website, and only if measured coverage gain per $ justifies it |

## What each experiment measures (harness output)

| Experiment | Metrics in `results.json` |
|---|---|
| Baseline | coverage per official area (filings, leadership, locations, websites, hiring/activity), companies with all five, requests, runtime |
| E1 | companies with ≥1 dated event, informative events, events in last 365 d, events/company, events with change detail, change types, earliest event, identity rejections, evidence completeness, requests, runtime |
| E2 | latest-filing, multi-year, prior-year-structured, revenue, operating result, balance sheet, wage costs, period-correct rates; PDF retrieved / text-parsed / image-only; registry employee and business-description coverage; requests, runtime |
| E3 | companies with ≥1 verified job, job count, jobs via subunit orgnr, name candidates, false employer name matches rejected, ads without orgnr, expired/inactive dropped, shared scan pages/entries/active ads, full-index cost, requests, runtime |
| E4 | verified / ambiguous / rejected per candidate source, registry contact fields actually present, population without a registry website |
| E5 | per strategy: verified new, ambiguous, no result, queries, $ cost, requests and latency per company, coverage gain per request and per $, and a **labelled precision check** on companies whose registry website is known (correct / other domain needing audit / missed) |

## Primary-source findings

### Brreg update feed (E1)
- Official, open (NLOD 2.0, same API as the entity data). Endpoints `/enhetsregisteret/api/oppdateringer/enheter`
  and `/underenheter`. Parameters: `dato` (from timestamp), `oppdateringsid`, `organisasjonsnummer`
  (comma-separated list), `size`, `page`, and since 2025-11-13 `includeChanges` (adds `endringer`).
  Sources: Brreg API documentation (via search index), and NAV's production consumer
  `navikt/amt-enhetsregister` (`/oppdateringer/enheter?oppdateringsid=..&size=500`).
- Row fields: `oppdateringsid`, `dato` (publication time in the API), `organisasjonsnummer`,
  `endringstype` ∈ {Ukjent, Ny, Endring, Sletting, Fjernet}. `Ukjent` is documented by NAV's client as
  "often because the change happened before change types were introduced", so the history predates the typing.
- History depth and default `dato` window: not documented in what could be read. The experiment requests
  `dato=1990-01-01` explicitly and reports the earliest event observed.
- `dato` is when Brreg *published* the update, not the legal effective date. Claims must say so.
- Rate limits: none documented for the entity API.
- A roles update feed (`/oppdateringer/roller`, CloudEvents) exists. Whether it filters by org number is
  unverified, so it is not in E1.

### Accounts register (E2), from `github.com/brreg/regnskapsregister-api`
- Open part = "key figures from the last submitted annual account". The closed part with the last three
  years of near-complete figures is "only for public authorities" (OpenAPIConfig).
- `GET /regnskapsregisteret/regnskap/{org}` accepts `år` and `regnskapstype`. The open schema has no employee count.
- Copies: `/aarsregnskap/kopi/{org}/aar` (years, limited to the last 15), `/aarsregnskap/kopi/{org}/{year}`.
  `AarsregnskapCopyService.getAarsregnskapCopy` reads a `.tif` and calls `PdfConverterService.tiffToPdf`,
  which draws each TIFF page as an image into the PDF: **no text layer**.
- Both copy endpoints sit behind a bucket4j per-IP limit with short/medium/long bandwidths whose
  capacities are environment secrets. The README calls the service a "preview, with no guarantees of quality of service".
- Implication: multi-year *figures* from permitted official sources need OCR of scanned pages. Per the
  brief, OCR is not built. Multi-year *existence* (filed years + copy URLs) is cheap and exact.

### NAV job feed (E3), from `github.com/navikt/pam-stilling-feed` docs and source
- Owner: NAV (Norwegian Labour and Welfare Administration). Free for anyone who accepts the terms at
  `arbeidsplassen.nav.no/vilkar-api` (republish/display or statistical use; remove inactive ads immediately;
  keep ads updated; handle personal data lawfully).
- Authentication: bearer JWT on every request. `/api/publicToken` (unauthenticated) serves a token "that can
  be used for experiments" and "will rotate at irregular intervals". Production consumers email NAV for a
  private token.
- No employer filter. Feed headers (`_feed_entry`) carry `uuid, status, title, businessName, municipal, sistEndret`.
  `employer.orgnr` (and `employer.homepage`) only appear in the per-ad detail. NAV's internal model also has
  `parentOrgnr`, consistent with ads keyed to the subunit (establishment) org number. E3 therefore accepts
  the company's own number or any of its registered subunits.
- Page size default 1,000, max 10,000. Start with `If-Modified-Since` (RFC 1123). An ad is never active more
  than 6 months. Finn.no ads are excluded. Historical data is a separate research request process.
- No numeric rate limit is documented. The service logs consumer IDs per request.

## Decisions needed from you

1. **Network access** for the next session: `data.brreg.no`, `pam-stilling-feed.nav.no`, `builderr.ai`,
   and general web access for company sites. Without it, no cell in the *Measured* column can be filled.
2. **NAV token**: (a) skip NAV jobs, (b) use the rotating public token at runtime (fits the stated
   purpose only for experiments), or (c) register a private token with NAV and pass it to the evaluator
   as an environment variable. (c) is the only clean production option but requires Builderr to inject it.
3. **Is a dated Brreg registry update "public activity" for Builderr's pooled evidence?** If the official
   evaluation contract defines public activity more narrowly (news, jobs, posts), E1's value falls sharply.
   This must be read from the official page, which is blocked here.
