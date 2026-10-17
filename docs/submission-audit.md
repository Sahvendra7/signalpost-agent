# Signalpost V1 submission audit

> **Historical audit, superseded.** This audit tested code `c5c6a32`. It is not the final submission
> candidate. **Final submission candidate: the commit tagged `submission-candidate-1`.** **Code under test for the final
> validation:** `4f827ee`. The tagged commit is code-identical to `4f827ee` and differs only in documentation. See
> `docs/final-submission-manifest.md` and `measurements/final-validation-2026-10-03/README.md`. Test counts,
> runtimes and limitations below are as measured on `c5c6a32`. Some limitations listed here were later fixed
> (`docs/official-submission-checklist.md`, "Status after validity hardening").

**Result: PASS.** All 20 checks pass after one blocking defect was fixed (check 18 below).

| | |
|---|---|
| Audited 2026-10-03 against | https://builderr.ai/challenges/signalpost and its evaluation contract (`/docs/signalpost-evaluation-harness.md`, scoring version 2) |
| Target commit requested for this audit (historical) | `99d09d9cd05e9a8b09f4ec322351a5ad08529e7d` |
| **Code commit tested (clean room)** | **`c5c6a32a6a25fe7205d48b72701af2291d721b82`**. This is `99d09d9` plus the outbound-URL-policy fix. This document and `measurements/submission-smoke-2026-10-03/` are added in the next commit, `403a9c1`, which changes no code. |
| Test count (clean room) | **224 passed, 5 subtests passed** (`uv run --with pytest pytest -q`) |
| Smoke-test location | `measurements/submission-smoke-2026-10-03/` (`report.json`, `envelopes.jsonl.gz`, `refresh-report.json`, `refresh-envelopes.jsonl.gz`, `input-companies.jsonl`, `refresh-replay.json`, stdout logs) |
| Third-party cost | **$0** per official run |

## Declared install and run command

Prerequisites: Python ≥ 3.12, [`uv`](https://docs.astral.sh/uv/), and outbound HTTPS to `data.brreg.no` and to
company websites. No API key and no environment variables are needed.

```bash
# install (pinned by uv.lock)
uv sync --locked

# run: the one evaluator command
uv run python scripts/run_competition_batch.py \
  --organisations <BATCH.jsonl> \
  --output out/envelopes.jsonl \
  --profiles-output out/profiles.jsonl \
  --report out/report.json \
  --snapshot-dir out/snapshots \
  --run-id <RUN_ID>
```

`--organisations` accepts JSONL (`{"organisation_number": "…"}`; `organisasjonsnummer` is also accepted), a
JSON list, or plain text with one number per line. Two flags are optional:

* `--previous-profiles <earlier profiles.jsonl>` adds the material changes since that run (refresh).
* `--expected-count N` is a reported guard; it never drops rows.

Do not pass `--bulk` unless the file is the gzip-compressed Brreg CSV (see Known limitations). The exit code
is 0 when the batch validation passes.

## Clean-room test (exactly what the evaluator does)

1. `git clone https://github.com/sahvendra7/signalpost-agent.git repo && git checkout c5c6a32…` into a new
   folder. No `.venv` existed, no universe or Brreg file was present, and `UV_CACHE_DIR` pointed to an empty
   directory.
2. `uv sync --locked`: installed 40 pinned packages from PyPI in 2.1 s (uv 0.8.17, CPython 3.13.14).
   `uv lock --check` was consistent.
3. `uv run --with pytest pytest -q`: 224 passed, 5 subtests passed.
4. `uv run python scripts/run_refresh_replay.py --manifest tests/fixtures/refresh-snapshots.json …`: 2/2
   expected changes, 0 false positives, `idempotent_rerun: true`.
5. The run command above on 100 companies: the fixed regression sample, sha256 `80eb79e6…`, the same sample
   as `docs/v2-results.md`. It was run live, with no `--bulk`.
6. The same command again with `--previous-profiles` from step 5 (the refresh run).

## Checks

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | Exact commit clean and reproducible | PASS | Working tree was clean. Local `HEAD` = `origin/claude/awesome-sagan-m2lppu`. `uv lock --check` passed. The clean clone at the SHA reproduced the tests and the run. |
| 2 | Clean-machine install from scratch | PASS | Fresh clone, no venv, empty uv cache, then `uv sync --locked`. Every dependency resolved from `uv.lock`; nothing relied on previously installed packages. |
| 3 | Declared install command works | PASS | `uv sync --locked` exit 0. `uv sync`, which the README uses, is equivalent with a consistent lock. |
| 4 | Exactly one run command, documented | PASS | `scripts/run_competition_batch.py` (above, and in README "Next: research live companies"). The other README commands are labelled practice (refresh replay) or local testing. The LLM A/B scripts are experiment-only. |
| 5 | Official batch read from evaluator input | PASS | Companies come only from `--organisations` (`pipeline.read_input_rows`). The agent never picks its own companies. |
| 6 | No dependency on the local 411,160-company universe | PASS | The universe file is not read by the run path (import graph: `pipeline, batch, claims, contract, evidence, http, identity, official, operations, refresh, sampling, site_identity, site_research, website`). The clean-room run had no universe or bulk file. Identity is anchored on the live Brreg registry. |
| 7 | Exactly one terminal result per input | PASS | Clean-room run: 100 inputs, 100 envelopes, 100 `completed`, `validation.passed: true`, 0 error codes. Tests also cover invalid rows, duplicate rows, network outage and per-company exceptions: every input line yields one envelope. |
| 8 | Input order preserved | PASS | Envelope order equals input order (`envelopes_follow_input_order: true`, also checked independently). |
| 9 | No secrets committed | PASS | The full git history (`git log -p --all`) was scanned for API-key, token, private-key and credential patterns and for secret-like file names: no hits. The only key-shaped string is the test literal `sk-test-not-real`. |
| 10 | LLM disabled unless configured | PASS | `run_competition_batch.py` never loads `llm/`. The layer needs `LLM_ENABLED=true` and model, key and base URL, and is reachable only from `scripts/run_llm_experiment.py`. Clean-room report: `llm_calls: 0`, no `llm` key, no LLM-derived claims. |
| 11 | No Brave dependency | PASS | Brave appears only in experiment code (`experiments/search.py`, `scripts/run_brave_discovery.py`). That code is not imported by the run path, is not in the default modules, and needs a key nobody supplies. |
| 12 | NAV optional, absent ≠ failure | PASS | NAV is not in `DEFAULT_MODULES`, and no NAV code is imported by the run path. No token is required. The run completed without any NAV access. |
| 13 | Source dependencies and licences documented | PASS | See [Sources, rights and licences](#sources-rights-and-licences) below. |
| 14 | Expected third-party cost documented | PASS | $0. No paid API, no LLM and no search provider. `report.operations.third_party_cost_usd = 0`. Only public Brreg APIs and company websites are used. |
| 15 | Evidence: URL, retrieval time, hash, span | PASS | 3,995 evidence entries; 0 lack `source_url`, `retrieved_at`, `content_sha256` or `claim_span`. 0 envelopes fail the contract validator with every snapshot hash re-verified. 3,991 entries have stored snapshot bytes. All 1,877 financial claims carry a reporting period. |
| 16 | Wrong-company safeguards intact | PASS | The registry response must carry the requested organisation number. The website gate requires a control signal (C1 organisation number or C2 name + address + own mailbox), and fan, directory and parked sites are rejected. Social handles are checked. The clean-room run verified the **same 15 websites with identical URLs** as the V2 fixed-sample run that was manually audited at 0 wrong-company matches. The adversarial identity tests pass. |
| 17 | Refresh idempotent | PASS | Replay fixture: `idempotent_rerun: true`, 0 false positives. Live rerun with `--previous-profiles`: **0 changes**, 0 duplicate claims, validation passed. The only deltas were live-source bytes (5 sites served new bytes). One of these (frisknaa.no) was not re-verified and was correctly *not* reported as a change. |
| 18 | URL encoding / handling safe | PASS, after fix | IRIs are encoded to URIs (IDNA host, percent-encoded path; test). **Defect found and fixed in `c5c6a32`:** the V2 site fetcher bypassed the public-host and redirect guard that the V1 website module enforces, so a registered domain resolving to a private or metadata address, or a redirect to one, could have been fetched. The live fetcher now applies `website.assert_public_url` (global addresses only, per origin) and `SAFE_OPENER` (each redirect re-checked). Three tests were added. Public sites are unaffected: same 15 websites, same URLs. Platform pages are never fetched, and robots.txt is honoured (401/403 means disallow). |
| 19 | Runtime and resources documented | PASS | See [Runtime and resources](#runtime-and-resources). |
| 20 | 100-company smoke report present | PASS | `measurements/submission-smoke-2026-10-03/report.json` (+ envelopes, refresh run). |

## Sources, rights and licences

**Data sources used by the run command.** There are no models and no paid APIs.

| Source | Use | Rights |
|---|---|---|
| Brønnøysundregistrene: Enhetsregisteret API (`/enheter`, `/underenheter`, `/roller`) | Identity, roles, subunits, registry website and e-mail | NLOD 2.0 (Norwegian Licence for Open Government Data) |
| Brønnøysundregistrene: Regnskapsregisteret API | Annual-account figures with reporting period | NLOD 2.0 |
| Brønnøysundregistrene: group structure | Group relationships | NLOD 2.0 |
| The company's own website | Identity verification, site-linked social profiles, dated first-party activity, JobPostings | Public pages of the company itself. Fetching is limited: robots.txt honoured, at most 30 requests and 60 s per company, own pages only. |

The following are never fetched: LinkedIn, Facebook, Instagram, YouTube, X and TikTok (a profile is
recorded only from the verified site's own link), directories and aggregators (Proff, Purehelp, 1881, …),
and search engines.

**Secrets:** none are used. The optional LLM layer is off and would read only server-side environment
variables (`LLM_*`), which are documented in `docs/llm-layer.md`.

**Python dependencies** (40, pinned in `uv.lock`; versions installed in the clean room). All are
permissive or weak-copyleft open-source licences:

annotated-types 0.8.0 MIT · babel 2.18.0 BSD · beautifulsoup4 4.15.0 MIT · certifi 2026.7.22 MPL-2.0 ·
charset-normalizer 3.5.1 MIT · courlan 1.4.0 Apache-2.0 · dateparser 1.4.2 BSD-3 · extruct 0.18.0 BSD ·
filelock 3.32.3 MIT · html-text 0.7.1 MIT · html5lib 1.1 MIT · htmldate 1.10.0 Apache-2.0 · idna 3.19 BSD-3 ·
jstyleson 0.0.2 MIT · justext 3.0.2 BSD · lxml 6.1.2 BSD-3 · lxml_html_clean 0.4.5 BSD-3 · mf2py 2.0.1 MIT ·
pydantic 2.13.4 MIT · pydantic_core 2.46.4 MIT · pyparsing 3.3.2 MIT · pypdf 6.16.1 BSD-3 · pyrdfa3 3.6.5 W3C ·
python-dateutil 2.9.0.post0 BSD/Apache-2.0 · pytz 2026.3.post1 MIT · rdflib 7.6.0 BSD · regex 2026.7.19
Apache-2.0 AND CNRI-Python · requests 2.34.2 Apache-2.0 · requests-file 3.0.1 Apache-2.0 · six 1.17.0 MIT ·
soupsieve 2.9.2 MIT · tld 0.13.2 MPL-1.1/GPL-2.0/LGPL-2.1 (multi-licence) · tldextract 5.3.2 BSD-3 ·
trafilatura 2.2.0 Apache-2.0 · typing-inspection 0.4.4 MIT · typing_extensions 4.16.0 PSF-2.0 · tzlocal 5.4.4
MIT · urllib3 2.7.0 MIT · w3lib 2.4.1 BSD-3 · webencodings 0.6.1 BSD.

`tldextract` downloads the public-suffix list on first use and falls back to its bundled snapshot. The
optional extras (`crawler`, `sentiment`) are not installed by `uv sync` and are not used.

## Runtime and resources

Measured on the clean-room run (100 companies, 8 worker threads, which is the default):

| Metric | Value |
|---|---|
| Batch wall time | 164.9 s (report `runtime_ms` 163,686). The refresh run took 162.2 s. |
| Per-company runtime | p50 4.1 s · p95 38.9 s · max 56.9 s |
| Peak memory (RSS) | 222 MiB |
| Network requests | 791 total (7.9 per company); 17.7 MB received |
| Request latency | p50 660 ms · p95 1,041 ms |
| Disk | Snapshots ≈ 30 MB per 100 companies (only with `--snapshot-dir`); envelopes 3.2 MB |
| CPU and GPU | No GPU. The run is network-bound. |

Built-in limits:

* Brreg requests: 20 s timeout and 3 attempts.
* Site research: 15 s per request, 2 attempts, 30 requests and 60 s per company, 3 MB per page.
* Each company is isolated, so one failure never ends the batch.

For a 1,000-company batch, scaling linearly suggests about 27 min of wall time at 8 workers and roughly
300 MB of snapshots. This is an estimate, not a measurement. Runtime is dominated by slow company
websites (the p95), and `--workers` can be raised if the evaluator's budget allows.

## Smoke-test results (clean room, `c5c6a32`)

| Area | Companies with ≥1 available fact (of 100) |
|---|---|
| Filings | 100 |
| Leadership | 100 |
| Locations | 100 |
| Verified website | 15 |
| Public footprint (site-linked profile or dated first-party activity) | 10 |
| Hiring | 0 |

Claim states: available 3,998 · not_available 455 · ambiguous 6 · blocked 1 · failed 1. These are identical
in coverage to the V2 fixed-sample measurement in `docs/v2-results.md`. No score is claimed.

## Known limitations

* **External coverage is low.** Verified websites and public footprint cover about 15% and 10% of
  companies, and hiring coverage is 0 (no job board is integrated; NAV is excluded). Recall will be bounded
  by this.
* **Live-source drift.** Pages served differently between runs can flip a website from verified to
  `ambiguous` (seen once in the refresh run: frisknaa.no). The gate abstains rather than guessing, and
  refresh does not report it as a change.
* **Four evidence entries have no stored snapshot.** These come from the V1 registry-website module. They
  carry a hash, but the bytes are not written to `--snapshot-dir`, so those 4 entries (2 companies) cannot
  be re-hashed offline. They pass the contract validator.
* **`--bulk` is not isolated per company.** It accepts only the gzip-compressed Brreg CSV, and a malformed
  bulk file fails the whole run because it is read before per-company isolation starts. The declared
  command does not use `--bulk`.
* **The outbound host check can be raced.** It resolves DNS separately from the fetch, so a host that
  changes its DNS answer between check and fetch is not caught. Redirects are always re-checked.
* **Network is required.** Without network every envelope is still emitted, but sources are marked
  `failed`.
* The LLM layer and the Brave and NAV experiment code are in the repository but are not part of the
  submitted run.
