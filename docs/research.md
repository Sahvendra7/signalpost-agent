# Phase 0 research: Signalpost task definition

Status: 2026-10-02. Written before any behaviour change.

## Provenance of every requirement

The official challenge page (`https://builderr.ai/challenges/signalpost`) and its linked pages could
**not** be fetched from the development container: the environment's egress policy denies
`builderr.ai` (and `data.brreg.no`). Requirements below are therefore tagged by source:

| Tag | Source | Trust |
|---|---|---|
| `[STARTER]` | This repository as shipped by Builderr (`README.md`, `OUTPUT_CONTRACT.md`, code) | Official |
| `[VALIDATOR]` | `github.com/builderr-ai/signalpost-citation-validator` (Builderr-owned public repo) | Official |
| `[SITE]` | Text from builderr.ai pages quoted by web-search snippets | Official text, indirect |
| `[USER]` | The task brief for this repository | Instruction |
| `[2ND]` | Other participants' public repositories | Not authoritative; never relied on alone |
| `[OPEN]` | Not confirmed; must be checked against the official page before submission | Unknown |

Every `[OPEN]` item is listed in `docs/submission-checklist.md` once that file exists.

## A. Task definition

**Product statement** `[SITE]`: "Give it a Norwegian company number. It searches permitted public
sources and returns a company profile with facts, source links and dates." Research covers "official
filings, leadership, locations, websites and public activity". "Every answer is limited to the sources
shown on the company profile, and missing evidence stays missing."

### Input `[STARTER]`
- A batch of 9-digit Norwegian organisation numbers. The starter accepts `.txt` (one per line),
  `.json` (list, or `{"organisation_numbers": [...]}`) and `.jsonl` (`{"organisation_number": ...}` rows,
  optional `evaluation_split`/`sample_slice`).
- The README asks for "one documented command that accepts a JSONL batch of organisation numbers".
- Universe `[STARTER]`: 411,160 active entities whose latest submitted annual-account year is 2025
  (`data/universe-metadata.json`). Public list: `https://builderr.ai/signalpost-company-universe-2025.jsonl.gz`.

### Output `[STARTER: OUTPUT_CONTRACT.md]`
One JSON object per input organisation number:

```
organisation_number
run         {run_id, started_at, completed_at, terminal_status}
claims[]    {field, value, availability, confidence, evidence_ids[]}
evidence[]  {id, source_url, source_class, retrieved_at, content_sha256, claim_span}
changes[]
errors[]
operations  {requests, runtime_ms, third_party_cost_usd}
```

- **Availability states** (closed set): `available`, `not_available`, `blocked`, `not_applicable`,
  `ambiguous`, `failed`.
- "A checked source that has zero jobs or zero locations is different from a source that was not checked."
- `[VALIDATOR]` adds the citation rules Builderr publishes for envelopes: evidence IDs unique per
  envelope; every `available` claim cites >=1 evidence ID; every cited ID exists; `source_url` is
  http(s) without credentials; `retrieved_at` is ISO 8601 **with timezone**; `content_sha256` is
  64 hex chars; optional `snapshot_path` (relative) whose bytes hash to `content_sha256`.
  `0`, `false` and `[]` are real values, never "missing".
- **Starter gap**: `scripts/run_competition_batch.py` emits a *different* legacy shape
  (`run_id/state/modules/profile`) with no `claims`, `evidence[]` IDs, `changes`, `errors` or
  per-envelope `operations`. See `docs/baseline.md`.

### Result envelope / terminal semantics `[STARTER]`
"Exactly one terminal envelope per input", "zero silent drops". The only example
`terminal_status` is `completed`; other values are `[OPEN]`.

### Batch semantics
- `[SITE]` "Solutions are tested on 100 random companies per day." `[STARTER]` "Builderr supplies the
  companies for every official run" and "the 100-row smoke test is practice only".
- Companies are random draws from the public 411,160 universe; whether a day's draw excludes
  previously seen companies is `[OPEN]`. Pre-computed profiles are explicitly not scored `[STARTER]`
  ("their precomputed profiles are not submitted or scored").

### Refresh semantics `[STARTER]`
- Submission must include "a previous-snapshot input and material-change output".
- Public refresh sample (`tests/fixtures/refresh-snapshots.json`): two expected changes, no false
  changes, and no extra changes when the same data is checked again (idempotency).

### Source / evidence requirements
- `[STARTER]` every fact: source, retrieval time, content hash, claim span. Exact-entity matches only:
  "Parent, brand, franchise and similarly named companies are not exact."
- `[STARTER]` "Open-source code does not grant permission to scrape a platform. Follow each source's
  terms, robots policy, rate limits and licence. LinkedIn, Meta and Indeed ... direct automated
  collection may be restricted. Use permitted APIs, licensed providers, company-owned outbound links,
  or return `blocked`/`not_available`."

### Dates / reporting periods
- `retrieved_at` (when we saw it) is mandatory. Financial claims carry the reporting period
  (`regnskapsperiode.fraDato/tilDato`) separately. Refresh changes carry `effective_at` where the
  source states one. Publication dates (news, announcements, job posts) must come from the source,
  never be inferred.

## C. Evaluator assumptions

| Question | Finding | Tag |
|---|---|---|
| How companies are supplied | A JSONL batch passed to the documented command | `[STARTER]` |
| Fresh/unseen? | Random from the 411,160 universe, daily; overlap with prior days unknown | `[SITE]`/`[OPEN]` |
| Batch size | 100 per daily official run | `[SITE]` |
| Missing results | A missing envelope is a silent drop and fails the contract | `[STARTER]` |
| Failures/timeouts | Must still be terminal envelopes; scoring of `failed` claims `[OPEN]` | `[STARTER]` |
| Precomputed profiles | Not scored; live research is what counts | `[STARTER]` |
| Clean environment | "pinned dependencies and reproducible setup"; one install + one run command | `[STARTER]` |
| Inputs the evaluator gives the command | Organisation JSONL. The starter also needs `--bulk brreg-enheter.csv`, which the evaluator may not supply; the command must be able to download or fall back to the live API | `[OPEN]` |
| Runtime limit per run | Not found | `[OPEN]` |
| External API limits | Brreg history endpoint ~30 requests/min (starter rate-limits at 2.1 s) | `[STARTER]` |
| Revision / submission | Email repo URL, run command, models/APIs and expected cost per 100-company run to `submit@builderr.ai`; submissions close Oct 21; 28 submissions at last view | `[STARTER]`/`[SITE]` |

## E. Information taxonomy

`[SITE]` names five categories: **official filings, leadership, locations, websites, public activity**
("48 of 100 sample companies have data in all five categories"). The fact classes below are this
repository's working breakdown of those five; the class set is `[OPEN]` until the official
evaluation contract is read.

| Category | Fact classes |
|---|---|
| Identity (anchor, every category depends on it) | legal name, org number, legal form, status (bankrupt/liquidating), registration/foundation date, NACE industry, registered purpose/activity text, registered address, employees (registry), VAT/Foretaksregister flags |
| Official filings | latest annual accounts (period, currency, revenue, operating result, profit before tax, net result, assets, equity, debt), filed-years list, official PDF copies, auditor (from roles), accounting obligation |
| Leadership | CEO (DAGL), chair (LEDE), board members, deputies, auditor, accountant, signature/prokura where public; role last-changed date |
| Locations | business address, postal address, registered subunits (establishments) with addresses and employees |
| Websites | official website (identity-verified), company-owned social profiles, contact pages |
| Public activity | dated registry announcements and updates, filing events, company-site news/press, job openings (exact org-number feeds), other dated permitted signals |
| Relationships | parent/subsidiary from official group structure, entity-type role holders (e.g. holding company as board member) |

## F. Main scoring bottlenecks (ranked)

1. **Coverage for no-website companies.** In the frozen 1,000 sample only ~14% (138/1000) have a
   registry `hjemmeside`; 79% have no registered employee count. Any website-only strategy leaves
   86% of companies with nothing in "websites" and little in "public activity". Recall must come
   from exact-org-number official sources first (roles, subunits, accounts, announcements, update
   feeds, org-number-keyed job feeds), then from verified discovery.
2. **Contract shape.** The starter's envelope does not match `OUTPUT_CONTRACT.md`; an evaluator
   parsing `claims/evidence` would see zero claims. This risks the whole precision/evidence score.
3. **Wrong-company contamination.** Website identity gate exists (org-number / full-name tokens), but
   discovery paths (search, social, maps) multiply namesake risk. Must stay gated.
4. **Evidence completeness.** Accounting-obligation "evidence" hashes a ruleset string, not captured
   bytes; bulk-registry evidence hashes the whole CSV. Claim spans are absent everywhere.
5. **Batch robustness.** Duplicate or malformed input, a company absent from the bulk file, or one
   exception in a worker aborts the entire batch (zero envelopes). All-sources-failed is reported
   `complete`.
6. **False refresh changes.** An outage (`source_error`) on refresh diffs as a value change.
7. **Throughput.** Up to ~11 sequential HTTP calls per company with 15–20 s timeouts and 3 retries;
   no per-company deadline. 100 companies × 8 workers is fine when sources respond, but a slow
   site can pin a worker for minutes.
8. **Bulk dependency.** The run command requires a ~200 MB bulk CSV the evaluator may not provide.
