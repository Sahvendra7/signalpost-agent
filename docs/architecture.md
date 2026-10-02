# Architecture (V1 proposal)

## The question

> What is the simplest reliable system that can achieve high recall while preserving exact-company
> precision under Builderr's runtime and API budget?

**Answer: a deterministic, organisation-number-keyed pipeline in which every fact is a claim backed by
captured source bytes, where official org-keyed sources are exhausted first and anything resolved by
name must prove the org number (or the full legal name plus a corroborating identifier) on the captured page.**

Why this is the simplest thing that works:

- **The org number is a perfect join key for most of the recall.** Brreg entity, roles, subunits, group,
  accounts, filing years and update feeds are keyed by the number itself. They need no entity resolution,
  so they add recall with no wrong-company risk. In a universe where 86% of companies have no registry
  website, this is where most attainable coverage sits.
- **Name-resolved sources are where precision is lost**, so they enter only through one gate
  (`identity.py`) that is shared, tested adversarially and fails closed (`ambiguous` and no facts).
- **No LLM in the critical path.** Extraction from JSON registries is deterministic; HTML extraction uses
  structured data (JSON-LD, meta tags) and fixed patterns. An LLM adds cost, nondeterminism and a
  fabrication risk with little extra recall on these sources. It can later be an optional, validated
  rewrite of the synthesis (every number, name, date and URL must appear verbatim in claims).
- **Per-company isolation plus a terminal envelope for every input row** removes the risk of a run
  producing nothing. That would score zero across every dimension.

## Pipeline

```
input row ──► validate (9 digits, mod-11) ──► identity anchor (bulk row ▸ live entity API)
          ──► source plan (core org-keyed ▸ website if URL ▸ category-specific)
          ──► retrieval (FetchResult: url, status, bytes hash, retrieved_at, attempts)
          ──► extraction (pure functions: source record ► candidate facts + span)
          ──► verification (org-keyed: implicit; name-keyed: identity gate)
          ──► normalisation (canonical values, periods, dates)
          ──► evidence attachment + dedup (evidence id = hash(url, sha256))
          ──► availability decision per category (available / not_available / blocked / failed / ambiguous / not_applicable)
          ──► change detection vs previous snapshot (available-vs-available only)
          ──► synthesis (template over claims)
          ──► envelope
```

Layers are separate modules so each can be tested alone:

| Layer | Module | Pure? |
|---|---|---|
| Retrieval | `http.py`, `official.py` (fetch part), `website.py` | No (I/O, injectable fetchers) |
| Extraction / normalisation | `official.py` normalisers, `claims.py` | Yes |
| Verification | `identity.py` | Yes |
| Contract | `contract.py` (states, evidence, envelope, validator) | Yes |
| Refresh | `refresh.py` | Yes |
| Orchestration | `pipeline.py` (batch, isolation, budgets) | No |
| Synthesis | `synthesis.py` (later) | Yes |

## Data model

Primary representation is **claims + evidence**, not prose.

- **Evidence** = one captured source response: `id`, `source_url`, `source_class`, `retrieved_at`,
  `content_sha256` (of the exact bytes), optional `snapshot_path`, `effective_at` when the source dates it.
- **Claim** = one fact: `field`, `category`, `value`, `availability`, `confidence`, `evidence_ids`,
  `claim_span` (JSON pointer or text excerpt in the cited source), `period` for financials,
  `method` (extraction method), and `key` (canonical dedup key).
- **Change** = a claim value that differs between two snapshots where *both* sides were `available`.
  An outage, a blocked source or a reordered list is never a change.

## Entity-resolution rules

| Signal | Confidence | Decision |
|---|---|---|
| Source keyed by org number (Brreg, Regnskapsregisteret, org-keyed job feed) | 1.0 | publish |
| Org number appears on the captured page | 1.0 | publish |
| All legal-name tokens (≥2 distinctive) in homepage identity text | 0.95 | publish |
| Single distinctive token plus substantive homepage | 0.95 | publish; candidate for extra signal |
| Most tokens / partial overlap | 0.65–0.85 | `ambiguous`, no derived facts |
| Parked domain, sports-club/parent mismatch, name only in body | ≤0.3 | `ambiguous`, no facts |

Website-derived facts (social links, descriptions, people, news) inherit the website decision and are
never published when it is not `exact`.

## Budgets

- Per-request timeout 10–20 s, bounded retries; per-company wall-clock budget (to be measured; initial
  target 60 s); bounded worker pool; the Brreg filing-history endpoint stays globally rate-limited.
- A company that exhausts its budget gets a terminal envelope with completed categories kept and
  pending ones `failed` with `budget_exhausted`.

## V1 scope (this increment)

1. Contract-conformant envelopes with fact-level claims from existing sources (no new sources).
2. Robust batch: never abort; invalid/duplicate/missing-from-bulk inputs still produce envelopes.
3. Refresh: outage-safe, order-insensitive, idempotent.
4. Contract validator mirroring Builderr's published citation rules; run report.

V2 (recall): live identity fallback when bulk is absent, registry purpose/activity, filing years by default,
registry update history, NAV jobs (after permission check), website contact/people extraction, discovery.
