# Official requirements matrix (official-contract audit)

Audit date: 2026-10-03. Audited code: `403a9c1`, whose code is identical to `c5c6a32` (`99d09d9` plus the
outbound-URL-policy fix). No research behaviour was changed for this audit. Only Builderr's own
published material counts as support. Our own experiments are engineering measurements, not rules.

## Official sources read (complete text, fetched 2026-10-03)

| Key | Resource | Link label on the challenge page | SHA-256 of the fetched copy |
|---|---|---|---|
| `BRIEF` | https://builderr.ai/starter-briefs/signalpost.md | "Download the full brief (.md)" | `924ff60e1dab437c63806846aa19eaa29d84d8e87132983c4e5d9f7336214c32` |
| `EVAL` | https://builderr.ai/docs/signalpost-evaluation-harness.md | "Full evaluation contract" | `e9f994e2fa34750411487e9fab82dbffd55dc1bb16efe9021906b92896229d45` |
| `SOURCES` | https://builderr.ai/starter-briefs/signalpost-sources.md | "Permitted sources" | `f080470ab29d5c6da243d812e35d0ae0aa3d35f5871d62dfef90422df1b8f630` |
| `PLAYBOOK` | https://builderr.ai/starter-briefs/signalpost-agent-playbook.md | "Company research guide" | `0b165301576e1ad09c210bba48dd61bb2669752a07abaeb1188df4099bd4844e` |
| `HARNESS` | https://builderr.ai/starter-briefs/signalpost-learning-harness.md | "Test and improve your crawler" | `3a3915e312010cb6ab6cf613135aa52acad6245b0db0d1dda3374dc27c2fed9a` |
| `PAGE` | https://builderr.ai/challenges/signalpost | the challenge page itself (traps, states, scoring, public board "Reviewed 3 October 2026") | HTML, varies per render |
| `START` | https://builderr.ai/start | "Agent basics, loops and outcomes" (links to `/start#agent-resources`) | HTML |
| `RULES` | https://builderr.ai/guidelines | "Rules" (platform-wide) | HTML |
| `KIT` | https://builderr.ai/signalpost-starter-kit.tar.gz (`OUTPUT_CONTRACT.md`, `README.md`, `scripts/run_competition_batch.py` "Evaluator-owned Signalpost batch contract", `docs/*`) | "Download the runnable starter" | `d48da9910ea7de07d2bf51ab265539a35fe07002a6c1ca5787df81316dfabbf6` (archive); `OUTPUT_CONTRACT.md` `59a93f8c…` |
| `SAMPLE` | https://builderr.ai/signalpost (100 reference profiles, embedded `DATA`) | "100-company product sample" | HTML |
| `UNIVERSE` | https://builderr.ai/signalpost-company-universe-2025.jsonl.gz | "Full company list" | archive `1c89710e…` and content `b82d6a3e…`, both equal to the published hashes |

Notes on the resource list:

* The challenge page labels the playbook "Company research guide". Its "Agent basics, loops and outcomes" link
  points to `/start#agent-resources`, a generic how-to-enter page. Both were read. `/start` adds one rule: "Each
  challenge page contains the full input format, scoring weights, limits, sample questions, model policy". The
  challenge page does **not** publish numeric limits, an input schema or a model list.
* `KIT/docs/*` (`external-footprint-loop.md`, `poc-design.md`, `competition-control-loop.md`) describe an older
  55/15/10/12/8 rubric. `EVAL` says scoring version 2 (50/30/12/8) applies to every entrant from 26 August 2026,
  so those rubric numbers are treated as superseded. The kit's own `batch.py` also uses a different state
  vocabulary (`complete`, `not_found`, `blocked_policy`, …) from the six official states. The kit is a reference,
  not the contract.
* `PAGE` public board, reviewed 3 October 2026: "every scored entry was recalculated against the same locked
  **1,200-company** set … Each scored entry ran twice … No entry reached 65/100". 28 submissions, 19 assessed,
  0 qualified. The top score is 60.51 (recall 13.59/50).

Status values: **PASS** = verified in this audit (by test, run or direct code reading cited in the row).
**PARTIAL** = part of the rule holds, or the rule is ambiguous and our reading carries a risk.
**FAIL** = does not hold. A status is never inferred from our own coverage experiments alone.

## 1. Requirements matrix

### A. Input and batch handling

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| A1 Read the official batch from the evaluator's file | `PAGE`, `PLAYBOOK` (Common traps) | "We hand it the official company batch at run time … Read them from that file. An agent working from its own list cannot be scored" | Companies come only from `--organisations` (`pipeline.read_input_rows`). The clean clone had no universe file and ran. | PASS | — |
| A2 Unseen companies | `BRIEF` | "Your agent must handle company numbers it has not researched before." | Offline: 1,200 valid numbers that are not even in the public universe. Live: 150 + 1,200 universe companies never measured before. All produced terminal envelopes. | PASS | — |
| A3 Batch size grows | `EVAL`, `PAGE` board | "1,000 companies now; it may grow to 1,100"; board: "locked 1,200-company set" | No batch-size assumption. Offline 2,000-row text batch passed. The live 1,200 run is in `official-submission-checklist.md` §C. | PASS (mechanics) | Runtime: see E1 |
| A4 One terminal envelope per input | `EVAL` | "Exactly one terminal envelope per input organisation number." | Verified: offline 1,200, 1,100, 2,000 and a dirty batch; live 150 and 1,200. `validate_batch` checks the count. | PASS | — |
| A5 No missing rows | `PAGE` | "'I found nothing' is a valid answer. A missing row is not." | Invalid, duplicate or unresolvable rows get a `failed` envelope. Source failures are isolated per company (two isolation boundaries). | PASS | — |
| A6 Input file format | `KIT` README; `BRIEF` | "one documented command that accepts a JSONL batch of organisation numbers"; "Builderr supplies organisation numbers, cutoff and output contract" | JSONL with key `organisation_number` or `organisasjonsnummer`, JSON list or object, plain text, and `.gz`. **Probe:** keys `orgnr`, `org`, `organization_number` and `organisationNumber` turn every row into `failed`. A CSV header line becomes one extra `failed` envelope. | PARTIAL | Accept any key holding one 9-digit number, and skip a non-numeric header line. Ask Builderr for the exact batch schema. |
| A7 Input order | `KIT` (`run_competition_batch.py` orders envelopes by input). Not an explicit contract rule. | — | Envelopes follow input order (`envelopes_follow_input_order` check, verified live). | PASS | — |
| A8 A batch, not one company at a time | `PLAYBOOK` traps | "We need a batch: 100 company numbers in, 100 results out, from one run." | One process, thread pool, one output file. | PASS | — |

### B. Output envelope

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| B1 Envelope contents | `EVAL` Output contract | "Envelopes must contain legal identity, claims, evidence references, availability states, source snapshots, refresh metadata and errors." | `claims`, `evidence`, per-claim `availability`, `errors`, `changes` and `run` are present. Legal identity exists only as `identity`-category claims, with no top-level identity object. Source snapshots appear as `evidence[].snapshot_path` only with `--snapshot-dir`, which the declared command passes. Refresh metadata is limited to `run` and `changes`, with no previous-run id or time. | PARTIAL | Add a top-level `legal_identity` object (copied from claims) and a `refresh` object (`previous_run_id`, `previous_completed_at`, `compared`). |
| B2 Minimal contract shape | `KIT` `OUTPUT_CONTRACT.md` | `organisation_number`, `run{run_id, started_at, completed_at, terminal_status}`, `claims[{field, value, availability, confidence, evidence_ids}]`, `evidence[{id, source_url, source_class, retrieved_at, content_sha256, claim_span}]`, `changes`, `errors`, `operations{requests, runtime_ms, third_party_cost_usd}` | Every key is present (extra keys are additive). Verified on 1,350 live envelopes. | PASS | — |
| B3 Six explicit states | `EVAL`, `BRIEF`, `PAGE` | "Valid states are `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous` and `failed`." `PAGE`: "Each result carries one of these states" | Claims use exactly the six states (the validator rejects others). The envelope carries `run.terminal_status` ∈ {`completed`, `failed`}, like the kit example. There is no envelope-level six-state field. | PARTIAL (interpretation) | Add an envelope-level `availability` (one of the six) next to `terminal_status`. Purely additive. |
| B4 Checked-empty ≠ unchecked | `KIT` `OUTPUT_CONTRACT.md` | "A checked source that has zero jobs or zero locations is different from a source that was not checked." | `not_available` (checked) vs `failed`/`blocked` (not checked). A `_count` of 0 is never coverage. Unrequested modules emit nothing. | PASS | — |
| B5 Never zero for missing | `BRIEF`, `EVAL` | "Never turn absence into zero." / "Missing values are never silently converted to zero." | `claims.py` copies values only. Tests: `test_financial_zero_is_preserved_with_reporting_period`, `test_empty_result_is_explicit_and_distinct_from_unchecked`. | PASS | — |
| B6 Source, retrieval time, reporting period | `BRIEF` official-run checks; `EVAL` | "Claim-level source, retrieval time and reporting period where relevant" | Every available claim references evidence with `source_url`, `retrieved_at` and `content_sha256`. Financial claims carry `period{from,to}`, `currency` and `account_type`. The validator ran on every live envelope: 0 findings. | PASS | — |
| B7 Claim provenance fields | `SOURCES` Publication rules | "Every claim records source URL or source identifier, retrieval time, effective/reporting date where relevant, content hash and extraction method." | `method` is on every claim. `effective_at` is on evidence where the source gives one, and `event_date` on dated claims. | PASS | — |
| B8 Snapshot record detail | `PLAYBOOK` §5 (reference architecture, "not a mandated framework") | "requested and final URL, redirect chain and response status, retrieval timestamp …, content hash, parser and extractor version, source class and access policy" | Content-addressed bytes, hash, URL, time and source class. No redirect chain, status, parser version or access policy in evidence. | PARTIAL (non-mandatory) | Optional: add `final_url`, `http_status` and `extractor_version` to evidence. |
| B9 Span granularity | `PLAYBOOK` §5 | "Every published claim should point to a snapshot plus a selector, character span, table cell or PDF page." | `claim_span` is a text or JSON-path quote, not character offsets. | PARTIAL (non-mandatory) | Optional. |
| B10 §1 Legal identity and public brand | `BRIEF` Required envelope | "1. Legal identity and public brand" | Legal identity: yes. Public brand: not emitted as a claim (no brand or alias field). | PARTIAL | Emit the verified site's `og:site_name`/title as `public_brand` (only when the site is verified). |
| B11 §2 Latest accounts and history | `BRIEF` | "2. Latest annual accounts and available history" | All periods the `/regnskap/{org}` response returns (2023–2025 observed), 7 figures each, plus `latest_filed_accounts_year`. The filing-year list module (`financial_history`) is not in `DEFAULT_MODULES`. | PASS | Optional: enable the filed-years list (it is rate limited, see `SOURCES` audit). |
| B12 §3 Leadership and registered workplaces | `BRIEF` | "3. Leadership and registered workplaces" | Brreg roles (active only) and subunits with addresses. | PASS | — |
| B13 §4 Verified website and company-owned profiles | `BRIEF` | "4. Verified official website and company-owned profiles" | Identity-gated website and site-linked profiles. The mechanism works, but coverage is low (8–15% of companies). | PASS (mechanism) | Coverage: see `official-scoring-model.md` |
| B14 §5 Hiring and dated public activity | `BRIEF` | "5. Hiring and dated public activity from permitted sources" | Hiring comes only from schema.org `JobPosting` on verified sites: 0 found in 650 measured companies. Dated first-party activity: 3–8% of companies. | PARTIAL | See the scoring model (the largest recall gap) |
| B15 §6 Evidence and availability | `BRIEF` | "6. Claim-level evidence and availability state" | Yes. | PASS | — |
| B16 §7 Refresh metadata and changes | `BRIEF` | "7. Refresh metadata and material changes since the previous run" | Changes are emitted only when `--previous-profiles` is passed. See section C. | PARTIAL | See C2–C5 |

### C. Refresh

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| C1 Idempotent re-run | `EVAL`; `PAGE` | "Re-running the same snapshot is idempotent." / "the same source snapshot must not create duplicate records or false changes." | Replay fixture: `idempotent_rerun: true`, 0 false changes. Live, this audit: the identical command re-run on 150 unseen companies gave **0 claim-set differences**. A refresh with `--previous-profiles` gave **0 changes**. | PASS | — |
| C2 Prior snapshots / evidence preserved | `BRIEF`; `EVAL` | "Idempotent refresh with prior snapshots preserved" / "Refresh preserves prior evidence and exposes material changes." | Snapshot bytes are content-addressed and survive a re-run into the same `--snapshot-dir`. **But** re-running the declared command with the same paths **overwrites** the previous `envelopes.jsonl`, `profiles.jsonl` and `report.json` (verified). The new envelope does not carry the previous evidence. | PARTIAL | Make the one command refresh-aware: if `--profiles-output` already exists, archive the previous run under `<out>/history/<run_id>/` and diff against it automatically. |
| C3 Material changes exposed | `EVAL`; `BRIEF` §7 | as above | Diff covers registry fields, financial records, filing years, roles, subunits and the V1 website title, description and social links. **Not diffed:** V2 verified website, site-linked profiles, dated site activity, job postings. | PARTIAL | Add V2 site facts to `TRACKED_FIELDS`. |
| C4 Failed refresh keeps the last supported value | `HARNESS` §5; `PLAYBOOK` §7 | "A failed refresh must not erase the last supported value." / "Failed refreshes keep the last known supported value and expose the failure." | A failed source produces no false change. However, the new profile and envelope replace the value with the failure state. The last supported value is not carried forward. | FAIL | Carry the previous supported claim forward with `carried_forward: true`, its original `retrieved_at` and evidence, plus an `errors` entry for the failed refresh. |
| C5 Typed change record | `HARNESS` §5; `PLAYBOOK` §7 | "emit a typed change such as `new_role`, `closed_job`, `new_location`, `new_filing` or `changed_description`"; "previous supported value, first and last observed timestamps, change type and materiality, sources supporting both sides" | Each change has `field`, `old_value`, `new_value`, current `source_url`/`retrieved_at`, and both hashes. It has no `change_type`, no `materiality`, no previous-side URL or time, and no first/last observed. | PARTIAL | Add those fields. Deterministic mapping, e.g. roles: added → `new_role`. |

### D. Identity and precision

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| D1 Exact entity before publication | `SOURCES` | "A profile or domain must resolve to the exact legal entity before its facts are published." | Website gate: org number on the site (C1), or legal name + registered address + own-domain mailbox (C2). Fan, directory and parked sites are rejected. Social links are taken only from a verified site. Our manual audits: 0 wrong-company publications. This is not Builderr-verified. | PASS (our audit) | Keep |
| D2 Abstain when uncertain | `BRIEF`; `PAGE` | "return `ambiguous` or `not_available` when the company match is uncertain." | `ambiguous` with reasons. | PASS | — |
| D3 Relationships labelled, not collapsed | `SOURCES` | "Group, parent, subsidiary, franchise and public-brand relationships must be labelled, not collapsed." | The Brreg group structure is a claim. A parent or brand site is withheld as `ambiguous` with reasons but not labelled with a relation type. (Builderr's `SAMPLE` uses `related_not_exact · withheld`.) | PARTIAL | Optional: add `relation: related_not_exact` to withheld sites. |
| D4 No fabricated financial values | `BRIEF`; `EVAL` | "No fabricated financial values or material wrong-company publication" | Values are copied verbatim from Regnskapsregisteret. No model is involved. | PASS | — |
| D5 LLM is never the identity authority | `PLAYBOOK` §6 | "It must not decide exact identity, invent a missing field, or silently override deterministic evidence." | The layer is off. By design it runs only after the deterministic gate, and its output is validated against spans. | PASS | — |
| D6 Search is never evidence | `SOURCES`; `PLAYBOOK` §4 | "Search results generate candidates; they are not claim evidence." | No search provider is used. | PASS | — |
| D7 No sentiment from own copy | `SOURCES` | "Company-owned promotional copy may describe the business but cannot provide an independent sentiment claim." | No sentiment is produced. | PASS | — |

### E. Runtime and resources

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| E1 Fixed time and resource budget | `EVAL`; `BRIEF`; `PAGE` | "A fixed time and resource budget supplied equally to every entrant"; "A timeout or missing result is not scored." **The value is not published.** | There is no batch deadline. Envelopes are written only after the whole batch finishes. **Verified:** a run killed at 25 s left **0 envelopes and no report**. Live 1,200 companies: see checklist §C. | PARTIAL (budget unknown; no graceful degradation) | Add `--deadline-seconds` (or an env var). When it nears, skip site research for the remaining companies and emit registry-only envelopes. Write envelopes incrementally. Ask Builderr for the budget. |
| E2 External API budget | `PAGE`; `PLAYBOOK` | "Each run has a small external API budget" (amount not published) | $0. No paid API. | PASS | — |
| E3 Measurement reporting | `EVAL` Measurement | "Report exact-company precision, wrong-company publications, per-field precision/recall/coverage, evidence-span validity, crawl completion, refresh correctness, false-change rate, cost per company, request count, and p50/p95 runtime. Abstention is reported separately" | The run report has requests, cost, p50/p95 company and request latency, category coverage, module states and contract validation. Precision and wrong-company figures exist only in docs (manual audits). Abstentions (`ambiguous`) are not a separate report line. | PARTIAL | Add `abstentions` and `crawl_completion` to the report. Keep the precision audit in docs. |

### F. Setup and reproducibility

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| F1 Pinned dependencies | `BRIEF`; `EVAL` | "Reproducible setup, pinned dependencies and one evaluator command" | `uv.lock`. `uv sync --locked` succeeded in the clean room with an empty cache, and `uv lock --check` passed. | PASS | — |
| F2 One pasteable command | `PLAYBOOK` traps | "Give one command that can be pasted. A list of steps or a notebook cannot be run automatically." | `uv run python scripts/run_competition_batch.py --organisations … --output … --profiles-output … --report … --snapshot-dir … --run-id …` (`docs/submission-audit.md`). The README still leads with the starter's multi-step flow (CSV download, sampler). | PASS | Put the one install line and the one run command at the top of README. |
| F3 Clean-machine install | `PLAYBOOK` traps | "Clone your own repository into a new folder at the pinned commit, make an empty virtual environment, run only your declared install step, then your run command." | Verified: fresh clone at `403a9c1`, no `.venv`, empty `UV_CACHE_DIR`, no universe or bulk file. `uv sync --locked` took 1.9 s. Tests: 224 passed. The run command succeeded live. uv selected CPython 3.13.14; the interpreter is not pinned (no `.python-version`). | PASS | Optional: add `.python-version` (3.13). |
| F4 Builderr's frozen registry snapshot | `EVAL` | "Builderr provides the frozen official registry snapshot used for identity anchoring. External caches must be declared." | The declared command does not consume it; identity comes from the live registry. `--bulk` accepts only gzip CSV. **Probe:** a plain CSV raises `BadGzipFile` outside the per-company isolation, so the whole run fails. How Builderr passes the snapshot is not published. | PARTIAL | Load gzip or plain CSV/JSONL, and fall back to the live registry on any load error (record an `errors` entry). Ask Builderr how the snapshot is provided (path, flag or env var). |
| F5 Undeclared runtime network use | `EVAL` | "External caches must be declared." | `tldextract.extract()` may download the public-suffix list (publicsuffix.org) at runtime and cache it in `~/.cache`. That is not declared, and it is a source of drift. | PARTIAL | Use the bundled snapshot (`TLDExtract(suffix_list_urls=())`) and declare it. |

### G. Secrets, URL safety and source rights

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| G1 Secrets via documented env vars only | `EVAL` | "server-side secrets supplied through documented environment variables only" | No secret is needed. The `LLM_*` variables are documented and not loaded by the run command. | PASS | — |
| G2 Safe outbound URL handling | `BRIEF`; `EVAL` | "Declared source rights, server-side secrets and safe URL handling" / "Source rights, secrets and outbound URL policy are documented and safe." | `c5c6a32` and later: public hosts only, and every redirect is re-checked (`assert_public_url`, `SAFE_OPENER`, 3 tests). **`99d09d9` lacks this:** its V2 site fetcher could fetch private or metadata addresses. A DNS-rebinding race remains (documented). | PASS at `403a9c1`; FAIL at `99d09d9` | Never submit `99d09d9`. |
| G3 Source rights declared | `BRIEF`; `EVAL` | as above | `docs/submission-audit.md` and `docs/official-source-compliance.md`. | PASS | — |
| G4 Restricted platforms | `SOURCES`; `PLAYBOOK` | "Do not scrape a platform when its terms, robots policy or applicable law prohibit the submitted method." | LinkedIn, Meta, YouTube, X and TikTok are never fetched. Only the verified site's outbound link is recorded. | PASS | — |
| G5 Robots, terms and rate limits | `SOURCES`; `KIT` README | "Public pages whose terms and robots policy permit the submitted access pattern"; "Follow each source's terms, robots policy, rate limits and licence." | robots.txt is honoured (401/403 means disallow). `Crawl-delay` is ignored. Per-site terms are not checked. Brreg has no client-side throttle (≈4–5 requests/s at 8 workers). | PARTIAL | Honour `Crawl-delay` (capped). Add a Brreg token bucket. Declare the user agent. |
| G6 No committed secrets | `RULES` | "Never commit API keys, passwords or private data." | Pattern scan of the tree at `403a9c1`: no hits. A full-history scan was done in the previous audit. | PASS | — |
| G7 No account-bound credentials | `PAGE`; `PLAYBOOK` | "What we cannot use is a credential tied to your own account on another service" | None used. Brave and NAV are excluded from the run. | PASS | — |
| G8 Personal data minimised | `KIT` `docs/norway-sources.md` (starter guidance, not contract) | "Person data is only used in the company-centric role context; birth dates are not stored or displayed." | Envelopes contain no birth dates. The raw Brreg roles JSON bytes stored under `--snapshot-dir` do contain `fodselsdato`. | PARTIAL | Either accept this (raw evidence) and declare it, or redact before storage (which changes the hash semantics). Decision needed. |

### H. Scored dimensions (not validity checks)

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| H1 Synthesis (12 pts) | `BRIEF`; `PAGE` | "It should explain the company, changes and unknowns without making unsupported claims." / "with sources for its conclusions." | The run emits no summary at all. LLM synthesis exists but the run command never loads it. | FAIL | Deterministic, claim-cited summary per envelope (template, like `SAMPLE`'s own "Company brief"). No LLM needed. |
| H2 UX (8 pts) | `BRIEF`; `PAGE` | "A user should be able to find, compare and verify the information on desktop and mobile." | The run produces JSONL only. `scripts/build_prototype.py` is starter legacy, untested on our envelopes, and not run. | FAIL | Static HTML viewer generated from the envelopes (search, compare, evidence links, mobile layout). |
| H3 External recall (50 pts) | `EVAL` | "For every external field family, coverage is 70% company recall and 30% individual-claim recall" | Verified website 8–15%, footprint 5–10%, hiring 0%. | PARTIAL | See `official-scoring-model.md` |

### I. Submission

| Requirement | Official source | Exact rule | Current implementation | Status | Action |
|---|---|---|---|---|---|
| I1 Smoke test in a public artifact | `EVAL` | "The submitted public artifact includes a 100-company smoke-test result or report." | The repository is public (`visibility: public`). `measurements/submission-smoke-2026-10-03/report.json` and envelopes are committed. | PASS | — |
| I2 Submission email contents | `BRIEF` Submit; `PAGE` mailto template | "repository URL, exact commit hash, 100-company smoke-test result or report, one run command, models/APIs/licences, expected cost per official batch, agent name and contact for results" | All are prepared except agent name and contact. | PARTIAL | The user supplies the name and contact. |
| I3 Exact commit reachable | `RULES` | "The evaluated version—not a later replacement—is the entry of record." | Commits live on `claude/awesome-sagan-m2lppu`; the default branch is `main`. A clone fetches all branches, so the hash is reachable now. It would become unreachable if the branch were deleted. | PARTIAL | Merge to `main` or push a tag for the submitted hash. |
| I4 Versions and timing | `BRIEF`; `EVAL` | "up to four revised exact commit hashes by 18 October, for five versions total"; "Revisions … never replace earlier batch results." Final ranking is "the mean across every scheduled daily batch while an entrant has an active frozen version". | Not submitted yet. | PASS (nothing used) | See the commit strategy (a weak v1 permanently lowers the mean). |
| I5 Expected cost per batch | `BRIEF` | "expected cost per official batch" | $0 | PASS | — |
| I6 Qualification | `EVAL` | "Qualification is an official run with 65/100 or more." | Unknown. No board entry has reached 65. | — | See the scoring model |

## 2. Open questions answered from the official documents

"NOT PUBLISHED" means no official resource states it. Where the official `SAMPLE` data or the `PAGE` board gives
indirect evidence, it is labelled as evidence, not as a rule.

1. **Does Brreg update history count toward the scored public-activity category?** NOT PUBLISHED. The
   official wording is only "what dated public activity the checked sources reveal" (`BRIEF`) and "Hiring and
   dated public activity from permitted sources" (`BRIEF` §5). No document names the Enhetsregisteret update
   feed. Evidence: in `SAMPLE` the "Hiring & public activity" area is never driven by registry events, only by
   company-owned profiles, posts and jobs. **UNCONFIRMED, leaning no.**
2. **What defines each scored information category?** NOT PUBLISHED. `EVAL` scores "external field
   families" without listing them. The only concrete example of an information type is **job postings**
   (`BRIEF`/`EVAL` worked example). Product content (`BRIEF`): "what it does, who leads it, where it operates,
   how its latest filed numbers look, whether it appears to be hiring, and what dated public activity the
   checked sources reveal". `PAGE`: "company details, people, locations, financial results, jobs and public
   activity". `SAMPLE` coverage areas: Company record, Financials, People & locations, Company website, Public
   footprint ("Hiring & public activity").
3. **Which registry fields count toward recall?** NOT PUBLISHED. The word *external* in "external field
   family" may exclude registry fields from the 50 recall points. Indirect evidence: 12 of 19 assessed board
   entries sit at 12.83–12.91/50 recall (9 at exactly 12.83), consistent with every entrant getting the same registry baseline and
   little external coverage. **UNCONFIRMED.**
4. **Are additional filing figures part of the checked reference collection?** NOT PUBLISHED. In `SAMPLE`,
   financial records carry exactly seven figures (revenue, operating result, profit before tax, annual result,
   assets, equity, debt). These are the same seven we publish. `SAMPLE` reports a "Fresh PDF audit 201 / 203
   fields matched". There is no evidence that further fields are in the pool. **UNCONFIRMED, leaning no.**
5. **Does a registry-linked but uncrawled website count?** `SOURCES`: "Official data … does not, by itself,
   identify the public brand or website" and "A profile or domain must resolve to the exact legal entity before
   its facts are published." `BRIEF` §4 says "**Verified** official website". So a registry URL alone is not a
   verified website. We publish it only as `registry_listed_website`, never as `official_website`. **Answer:
   no, not as a verified website.**
6. **Does a site-linked social profile count as public activity?** `SOURCES` lists "Social or video profiles
   linked by the verified company site" as a company-owned source. `BRIEF` places profiles in §4 ("company-owned
   profiles"), not in §5 (hiring and activity). Evidence: in `SAMPLE` the footprint area is `true` for 25
   companies whose only external evidence is site-linked handles (`rightsStatus: "approved"`). **Permitted; it
   counts toward the sample's footprint area. Whether it is in the "activity" scoring family is UNCONFIRMED.**
7. **Does dated company-site activity count?** Permitted: `SOURCES` names "Sitemap, news, investor, careers …
   pages". In scope: `BRIEF` §5 "dated public activity from permitted sources". Evidence: the official starter
   ships `extract_company_site_activity.py` and `extract_company_site_news.py` (company-site observations from
   identity-verified sites), so Builderr's crawlers plausibly add such facts to the pool. **Permitted and in
   scope; inclusion in the scored pool is UNCONFIRMED.**
8. **May social platforms themselves be fetched, or only links found on company sites?** Only through
   "Official or licensed platform APIs" or "Public pages whose terms and robots policy permit the submitted
   access pattern" (`SOURCES`). "Do not scrape a platform when its terms, robots policy or applicable law
   prohibit the submitted method", and unofficial clients "cannot be the sole support for a published claim"
   (`PLAYBOOK`). Site-linked profiles are recorded "subject to the destination platform's access terms". Note:
   Builderr's own `SAMPLE` includes LinkedIn page, post and job captures marked `rightsStatus: "experimental"`,
   so the pool may contain facts we cannot lawfully match. **Default: links only.**
9. **What exactly is "hiring"?** NOT DEFINED beyond "whether it appears to be hiring" (`BRIEF`), "jobs"
   (`PAGE`), and the scoring example "50 job postings across 20 companies". So individual job postings are the
   facts, and companies with at least one posting are the company recall. `SAMPLE` jobs carry title, location,
   `date_posted` and URL.
10. **What source and licence rules apply to NAV?** NOT MENTIONED in any official resource. The generic rules
    are "Official or licensed platform APIs" and "Licensed … jobs … feeds" (`SOURCES`), and no credential
    "tied to your own account on another service" (`PAGE`). NAV's own terms and token policy are outside
    Builderr's documents. **UNCONFIRMED.**
11. **What model/API policy applies to LLMs?** `PAGE`/`PLAYBOOK`: "You can. Each run has a small external API
    budget, and if you need a model key for scoring, ask and we will supply one. What we cannot use is a
    credential tied to your own account on another service, because we cannot reproduce your run with it."
    `PLAYBOOK` §6: "An LLM may summarise supported claims or propose candidates. It must not decide exact
    identity, invent a missing field, or silently override deterministic evidence." `HARNESS` §6: freeze
    "prompts, models and model versions". `BRIEF` Submit: declare "models/APIs/licences". No provider or model
    restriction is published.
12. **What is the external API budget?** "small" (`PAGE`). The amount is NOT PUBLISHED. Ties break on "lower
    declared third-party cost" (`EVAL`).
13. **What are the time and resource limits?** NOT PUBLISHED: "a fixed time and resource budget supplied
    equally to every entrant" (`EVAL`). No CPU, memory, disk, wall-clock or network numbers are given.
14. **What is the evaluator input format?** NOT PUBLISHED exactly. The `KIT` README says "accepts a JSONL batch of
    organisation numbers". The `KIT` reader accepts `.json`, `.jsonl` or text with key `organisation_number`.
    `PLAYBOOK`: "Read them from that file." `EVAL`/`BRIEF`: Builderr also supplies a "cutoff" and the "frozen
    official registry snapshot"; how they are passed is NOT PUBLISHED.
15. **What output envelope is required?** `EVAL`: "Exactly one terminal envelope per input organisation
    number. Envelopes must contain legal identity, claims, evidence references, availability states, source
    snapshots, refresh metadata and errors." The concrete JSON is the `KIT` `OUTPUT_CONTRACT.md` example.
    `PAGE`: "Builderr supplies the company batch and output format for the run." A per-run format supplement is
    therefore possible but not published.
16. **What happens for each state?** `PAGE` definitions: `available` "you found it"; `not_available` "you looked,
    there is nothing there"; `blocked` "the source refused the request"; `not_applicable` "the question does not
    apply to this company"; `ambiguous` "you could not be sure it is the right company"; `failed` "the run broke
    on this one". All six are valid terminal answers ("I found nothing" is valid), and only a **missing row**
    voids the run. `EVAL`: "Abstention is reported separately and cannot satisfy coverage." No state earns
    recall; only verified facts do. `PAGE`: "It is better to miss some information than publish it under the
    wrong company."
17. **What files and metadata must be submitted?** The email (`BRIEF`) with repository URL, exact commit hash,
    100-company smoke-test result or report, one run command, models/APIs/licences, expected cost per official
    batch, agent name and contact. The repository (`KIT` README) holds the smoke result, one command accepting a
    JSONL batch, one envelope per input, pinned deps, "a previous-snapshot input and material-change output", "a
    machine-readable run report with runtime, request count and third-party cost", and declared models, APIs,
    licences and source-rights assumptions. Suggested docs (`PLAYBOOK` §9, not mandatory): `AGENT.md`,
    `CRAWLERS.md`, `IDENTITY_RESOLUTION.md`, `DATA_SCHEMA.md`, `REFRESH.md`, `EVAL.md`, `LIMITATIONS.md`.
18. **What must the one-command runner do?** Install with the declared step in an empty environment. Then one
    pasteable command reads the official batch file, researches every company, and writes exactly one terminal
    envelope per company within the fixed budget, with source, retrieval time and reporting period per claim. It
    must give an idempotent refresh that preserves prior snapshots and exposes material changes, and secrets
    only via documented env vars (`PLAYBOOK` traps, `EVAL`, `BRIEF`).
19. **Hidden constraints on network access, crawling, robots or rate limits?** `EVAL`: "Every entrant receives
    the same batch, cutoff, **network policy** and resource budget". The network policy is NOT PUBLISHED.
    `SOURCES` requires that terms and robots permit the access pattern. `KIT` README: "Follow each source's
    terms, robots policy, rate limits and licence." `RULES` lists "deliberate service abuse" as invalidating. The
    only numeric rate figure is in starter guidance, not the contract: annual-account copies "roughly 30
    requests/minute" (`KIT` `docs/norway-sources.md`). A "shared-source failure is void and rerun" (`EVAL`).
20. **What source ownership and provenance rules apply?** `SOURCES` publication rules (source URL or id,
    retrieval time, effective date, content hash, extraction method; label relationships; search is not
    evidence). `PLAYBOOK` §4: "Never use search rank or an unofficial scraper response as the evidence for a
    published fact. Re-fetch the underlying permitted source and preserve it." Our verified findings become part
    of the shared pool used to rescore everyone (`EVAL`). `RULES`: "You keep ownership unless separate written
    licensing or transfer terms were agreed before entry", and a provisional winner must give "read-only access
    to that exact agent version".

## 3. Data model vs the evaluator (step 6)

Checked on 1,350 live envelopes from this audit (150 + 1,200 unseen companies) against `KIT`
`OUTPUT_CONTRACT.md` and `EVAL`.

| Element | Evaluator expectation | Ours | Discrepancy |
|---|---|---|---|
| Envelope keys | `organisation_number, run, claims, evidence, changes, errors, operations` | All present, plus `input_organisation_number, input_position, category_coverage, area_coverage, modules` | None (additive). No top-level legal identity or refresh object (B1). |
| `run` | `run_id, started_at, completed_at, terminal_status` (`"completed"` in the example) | Same. `terminal_status` ∈ {`completed`, `failed`}. Per-company `started_at`/`completed_at`. | `failed` is not in the example; a six-state envelope field is absent (B3). |
| Claims | `field, value, availability, confidence, evidence_ids` | Same plus `category, method, key`, qualifiers (`period, currency, account_type`, `event_date`), and `reason` on non-available claims | None. |
| Evidence | `id, source_url, source_class, retrieved_at, content_sha256, claim_span` | Same plus `effective_at` (when known) and `snapshot_path` (with `--snapshot-dir`) | No redirect chain, status or extractor version (B8, non-mandatory). |
| Dates | ISO with timezone | `retrieved_at` is UTC `…Z`. Financial `period.from/to` are dates. `event_date` is a date string. | None. |
| Reporting periods | "where relevant" | On all financial claims | None. |
| Content hashes | SHA-256 | 64-hex, re-verified against stored bytes by the validator | None. |
| Changes | material changes with evidence | field, old, new, current source, both hashes | No change type, materiality, previous source or observed span (C5). |
| Errors | list | `{code, stage, message}` | None. |
| Operations | `requests, runtime_ms, third_party_cost_usd` | Same plus `bytes` | None. |
| States | six | six at claim level | Envelope-level ambiguity (B3). |

## 4. Decision gate (step 12)

| Decision | Classification | Reason (official basis) |
|---|---|---|
| Deterministic identity gate (org number, or name + address + own mailbox) | **KEEP** | `SOURCES` exact-entity rule; "A high score cannot make up for a material wrong-company match" (`BRIEF`) |
| Website discovery without search (registry URL, registry e-mail domain, `<name>.no` DNS guess) | **KEEP** | Candidate generation is allowed. Publication evidence is the company's own page (`SOURCES`). The DNS-guess method is neither named nor prohibited. |
| No Brave | **KEEP** | A Brave key is account-bound, which `PAGE` forbids, unless Builderr supplies one. Search results are never evidence. Revisit only with a Builderr-supplied key. |
| Site-linked social profiles (links only, never fetched) | **KEEP** | `SOURCES` names them. `SAMPLE` marks them `approved` and counts them in the footprint area. |
| Dated company-site activity | **KEEP** | `SOURCES` news and sitemap pages; `BRIEF` §5; the `KIT` ships company-site activity extractors |
| `public_activity` mapping (profiles + dated site activity → footprint area) | **KEEP** (reporting only) | Matches the `SAMPLE` footprint logic. The scoring-family mapping is UNCONFIRMED, so no score is claimed. |
| Brreg update history as public activity | **UNCONFIRMED**, keep **out** of production | Not named by any official document. `SAMPLE` never uses registry events for footprint. It adds 1.8 requests per company. |
| Extra filing figures beyond the seven | **UNCONFIRMED**, keep out | `SAMPLE` uses the same seven figures. Zero network cost if added later. |
| Optional NAV | **UNCONFIRMED**, keep out | Not mentioned officially. Token and terms unclear. Credential rule. |
| LLM disabled by default | **KEEP** (and note: currently not even loadable by the run command) | Allowed (`PAGE`), but a key must come from Builderr. Synthesis can be done deterministically first. |
| Writing outputs only at batch end, with no deadline | **CHANGE** | Fixed budget, and "A timeout … is not scored" (`EVAL`). Verified: 0 envelopes after a kill. |
| Overwrite-on-rerun with no automatic previous-run diff | **CHANGE** | "Refresh preserves prior evidence and exposes material changes" (`EVAL`); "Each scored entry ran twice" (`PAGE`). |
| `--bulk` gzip-only and outside isolation | **CHANGE** | Builderr "provides the frozen official registry snapshot" (`EVAL`). Format unknown. Currently a crash risk. |
| Strict input key set | **CHANGE** | Input schema not published. One unknown key fails every row. |
| No synthesis, no viewer | **CHANGE** | 12 + 8 points (`BRIEF`). Most board entrants score 9.46–12 and 3.2–8 on these. |
| Last supported value dropped on failed refresh | **CHANGE** | `HARNESS` §5 "must not erase" |
| Envelope `terminal_status` only (`completed`/`failed`) | **CHANGE** (additive) | `PAGE` "Each result carries one of these states" |
