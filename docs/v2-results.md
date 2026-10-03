# Zero-cost V2 vs V1

Measured 2026-10-03. V2 = commit `abfe93f` (V1 = same code with `--modules` omitting `site_research`).
Both versions ran through the evaluator-facing command `scripts/run_competition_batch.py` with
`--snapshot-dir`, 8 workers, no bulk file, and no paid API. Third-party cost: **$0**. Raw outputs:
`measurements/v2-comparison-2026-10-03/`. No Builderr score is claimed.

Samples (4 × 100 companies, pairwise disjoint): the fixed Phase 4A sample (seed 20261002, sha `80eb79e6…`)
and three new random draws from the 411,160-company universe, seeds 20261101, 20261102 and 20261103
(`select_entry_batch.py`).

## Fixed sample (regression sample)

| Metric | V1 | V2 | Delta |
|--------|----|----|-------|
| Envelopes (100 inputs) | 100, all valid, all hashes verified | 100, all valid, all hashes verified | 0 |
| Filings coverage | 100 | 100 | 0 |
| Leadership coverage | 100 | 100 | 0 |
| Locations coverage | 100 | 100 | 0 |
| Website coverage (verified) | 9 | **15** | **+6** |
| Public-footprint coverage (site-linked profile or dated site activity) | 3 | **10** | **+7** |
| Hiring coverage | 0 | 0 | 0 |
| Companies with all five areas | 3 | **10** | **+7** |
| Verified facts (available claims) | 3,950 | 3,998 | +48 |
| Site-linked profiles / dated activities / careers pages | 4 / 0 / 0 | 9 / 34 / 3 | +5 / +34 / +3 |
| Requests | 596 | 797 | +201 (+34%) |
| Runtime (batch wall) | 59.9 s | 160.8 s | +100.9 s |
| Per-company runtime p50 / p95 / max | — | 4.0 / 40.8 / 55.5 s | — |
| Precision failures (wrong-company publications) | 0 | **0** | 0 |

## All four samples (400 companies)

| Metric | V1 | V2 | Delta |
|--------|----|----|-------|
| Filings / leadership / locations | 400 / 400 / 400 | 400 / 400 / 400 | 0 |
| Website coverage | 19 (4.75%) | **46 (11.5%)** | **+27 (×2.4)** |
| Public-footprint coverage | 8 (2.0%) | **31 (7.75%)** | **+23 (×3.9)** |
| Hiring coverage | 0 | 0 | 0 |
| Companies with all five areas | 8 | **31** | **+23** |
| Verified facts | 15,664 | 15,813 | +149 |
| Site-linked profiles | 11 | 40 | +29 |
| Dated first-party activities | 0 | 84 | +84 |
| Careers pages found | 0 | 9 | +9 |
| Requests | 2,286 (5.7 / company) | 3,011 (7.5 / company) | +725 (+31.7%) |
| Runtime (sum of four batch walls) | 229.4 s | 558.1 s | +328.7 s (+143%); 1.4 s vs 0.57 s of wall time per company at 8 workers |
| Bytes | 35.8 MB | 35.5 MB | ≈ 0 |
| Envelopes failing contract or hash check | 0 | 0 | 0 |
| Precision failures | 0 | **0 / 27 newly accepted sites** (manual audit) | 0 |

### Per seed (V1 → V2)

| Seed | Websites | Public footprint | All five | Requests | Runtime | Precision failures |
|---|---|---|---|---|---|---|
| 20261002 (fixed) | 9 → 15 | 3 → 10 | 3 → 10 | 596 → 797 | 59.9 → 160.8 s | 0 |
| 20261101 | 3 → 9 | 2 → 6 | 2 → 6 | 568 → 711 | 58.4 → 131.3 s | 0 |
| 20261102 | 4 → 12 | 2 → 8 | 2 → 8 | 566 → 779 | 52.6 → 155.3 s | 0 |
| 20261103 | 3 → 10 | 1 → 7 | 1 → 7 | 556 → 724 | 58.5 → 110.7 s | 0 |

The gain holds on all three fresh seeds (+6 to +8 websites and +4 to +6 footprint companies per 100), so
it is not specific to the fixed sample.

## Where the new websites came from (27 newly accepted)

| Discovery source | Accepted | Identity rule |
|---|---|---|
| `<legal-name>.no` guess (DNS-resolving only) | 18 | C1 org number in footer: 6; C2 name + registered address + own-domain mailbox: 12 |
| Registry `epostadresse` domain | 8 | C1: 2; C2 with own or registry mailbox: 6 |
| Registry `hjemmeside` rescued by gate v2 (v1 ambiguous) | 1 | C2 (maaemo.no) |

Precision audit: every one of the 27 was opened and checked against the registry. Each shows the
company's organisation number, or its exact registered street address and postcode plus a mailbox on its
own domain. Brand-titled sites (autoroyal.no for CS NETTHANDEL AS, FAMAC for FDVHUSET AS) carry the
organisation number. The fan site arasenstadion.no (976744667) is rejected in V2, and is also a unit test.

## Bug found by the comparison and fixed before the final numbers

The first V2 run hit one `UnicodeEncodeError` (a URL with "æ") in seed 20261103. Isolation held: the
company kept all its official facts and got a valid terminal envelope. URLs are now IRI→URI encoded
(IDNA host, percent-encoded path; test added) and all four V2 samples were re-run. Final numbers above
are from the re-run: 0 pipeline exceptions.

## What did not improve

- **Hiring stays 0/400.** No verified site published schema.org `JobPosting` data. Careers pages were
  found for 9 companies but are reported as website facts, not hiring. NAV remains the only hiring source
  measured (+1–2 per 100, OPTIONAL, experiment token).
- **Most companies still have no website:** 354/400 in V2. 69 of the fixed sample's companies have no official
  domain pointer at all.
- **Runtime:** V2 costs about 2.4× V1 wall time. Per-company p95 is 24–41 s, driven by slow candidate sites,
  and bounded by the per-company budget (30 requests, 60 s).

## Preserved guarantees (checked)

- One terminal envelope per input on all 8 runs (800/800). Every envelope passes the contract validator,
  including snapshot re-hashing of every cited source.
- Filings, leadership and locations at 100% on every sample.
- Failure isolation: the Unicode crash stayed confined to the site stage of one company.
- Refresh: site-research fields are not in the refresh change set, so V2 cannot introduce false
  changes. Refresh tests pass.
- 190 tests pass. Brave remains optional: `NoSearchProvider` is the default, and the batch command never
  calls a search API.

## Decision: **KEEP V2**

V2 more than doubles verified website coverage and nearly quadruples public-footprint coverage (and
companies covered in all five areas) on 400 companies across four disjoint random samples. It adds 0
wrong-company publications and costs $0, at +31.7% requests and about 2.4× runtime. No measured optimisation
produced more candidates at the cost of precision, so nothing was rejected on that ground.
`SCORING_MAPPING` for public footprint remains UNCONFIRMED (it follows the official sample's footprint
logic, not a written scoring rule).
