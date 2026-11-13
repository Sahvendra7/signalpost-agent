# Signalpost — project memory

Written 2026-11-13 at the end of the V3.2 Gemini research session, so a new session can resume without the old
chat. Read this first, then the documents it points to.

## 1. Standing rules from the owner (always apply)

* **Release.** Never modify the stable V3.1 release: branch `claude/awesome-sagan-m2lppu` (`139e23c`, code
  `334a085`).
* **No automatic actions.** Do not merge experimental work into it, push, or submit anything to Builderr
  automatically. Every push or merge needs an explicit owner instruction in that session.
* **Gemini.** It stays **disabled by default** (`GEMINI_ENABLED` defaults to false) and experimental.
* **No paid usage.** Never link billing or make paid calls. Use the free tier only, with actual spend kept at $0.
* **One project, one key.** Use one Gemini project and one key, `GEMINI_API_KEY`. Do not switch projects or keys
  to get around quota limits.
* **Exposed key.** The owner decided to keep using it (2026-11-06). The runner needs `--owner-accepts-exposed-key`
  and records that choice. Never print, log or commit a key value, and check by sha256 only.
* **Evaluation honesty.**
  * Do not tune prompts or rules on a labelled evaluation set and then call its score independent.
  * Never report a partial run as a complete result.
  * Do not change committed labels.
* **Repo convention.** `AGENTS.md` asks to explore the code through the Graphify MCP tools (`query_graph`,
  `get_node`) rather than grep, when they are available.

## 2. Where things are

| Item | Location |
|---|---|
| Release (deterministic, submitted) | branch `claude/awesome-sagan-m2lppu` |
| First Gemini research phase | branch `experiment/v3.2-gemini` (ends `a025a98`) |
| Remediation + independent validation (current) | branch `experiment/v3.2-hybrid` (from `a025a98`) |
| Results (first phase) | `docs/v32-gemini-results.md`, `docs/v32-gemini-api-report.md`, `docs/v32-llm-architecture.md` |
| Remediation report | `docs/v32-hybrid-remediation.md` |
| **Final independent comparison** | `docs/v32-evalh400-comparison.md` |
| **Builderr disclosure** (ready to adapt for the submission) | `docs/v32-builderr-gemini-disclosure.md` |
| Labelling rubric v2 | `docs/v32-news-labelling-rubric.md` |
| Measurements, datasets, labels, runs, response cache | `measurements/v32-gemini-2026-11-04/` |
| Pre-registration for evalh400 | `measurements/v32-gemini-2026-11-04/PREREGISTRATION_v2.json` |
| Identity gate | `src/norway_company_agent/identity_gate.py`, `tests/test_identity_gate.py`, `tests/fixtures/identity_gate/` |
| Gemini provider / experiment code | `src/norway_company_agent/llm/gemini.py`, `src/norway_company_agent/llm_experiments/`, `scripts/run_gemini_news_experiment.py` |

**Not in git (gitignored, lost with the container unless saved separately):**
* `out/v32/captures/` (58 MB capture store; needed only to recompute the evalg250 gate decisions);
* `out/v32/review_bundles/*.zip` (rebuildable from the review kits);
* `out/v32/revoked_key_sha256.txt` (sha256 hashes of the 3 exposed keys).

## 3. Results to remember

All figures are news precision on labelled samples.

| Sample | Role | V3.1 | Gemini filter | Hybrid |
|---|---|---|---|---|
| evalg250 (prompt v1, no gate) | independent at the time | 46.2% | 65.2% | 77.0% |
| evalg250 + identity gate | **diagnostic** (gate built from its errors) | 46.2% | 90.9% | 92.9% |
| **evalh400** (prompt v2 + gate, pre-registered) | **independent, final** | **48.3%** (41.1–55.6) | **84.0%** (75.3–90.1) | **82.3%** (75.1–87.7) |

**evalh400 detail:**
* Correct items published (of 138): V3.1 86, filter 79, hybrid 116.
* Company coverage (of 37): 29 / 26 / 32.
* Wrong-company items published: 23 / 2 / 2. Gemini removed these; the identity gate passed every evalh400 item.
* 433/433 calls succeeded on the free tier. Paid-equivalent cost $0.417, which is about $0.10 per 100 sampled
  companies; actual spend $0.
* Latency: median 1.5 s, p90 10 s.
* **The 90% target was not met.**

**Recommendation:** the improvement is clear enough to justify developing the hybrid towards a future, opt-in
release. It should not become the default. Required first:
1. a second-person review;
2. a deterministic rule for club subdomains on a federation's platform, validated on a fresh sample;
3. paid tier and a data-processing assessment for EEA use.

**Known failure classes still open:**
* opinion and promotional profiles, plus product pages, make up most of the hybrid's 25 errors;
* federation-platform subdomain items;
* parent/sister acquisitions are caught by Gemini, not by the gate.

## 4. Open items (owner)

1. **Second-person review.** Use the blind kits in `measurements/v32-gemini-2026-11-04/audits/evalg250/review_kit/`
   (87 units) and `.../audits/evalh400/review_kit/` (112 units). Standalone zips are in `out/v32/review_bundles/`.
   Fill `form.csv`, then adjudicate in `adjudication.csv`. Then compute agreement (kappa) and re-report with the
   adjudicated labels, marked as such.
2. **Builderr submission.** Disclose the experiment using `docs/v32-builderr-gemini-disclosure.md`. Submit only
   when the owner says so.
3. **Optional.** Integrating the identity gate or the hybrid into a future release needs a new independent sample;
   evalg250 and evalh400 are both consumed.

## 5. How to work in this repo (gotchas)

* **Dependencies:** run `uv sync`. Tests:

  ```bash
  uv run --with pytest python -m pytest -q -p no:cacheprovider
  ```

  A bare `uv run pytest` picks up a system pytest that lacks the deps. Expect 566 passed.
* **Scoring** of evalh400 (refuses drift, other configurations and partial runs):

  ```bash
  uv run python measurements/v32-gemini-2026-11-04/score_evalh400.py measurements/v32-gemini-2026-11-04/runs/final-evalh400-news-p2-evidence-v2-gemini-3.1-flash-lite.jsonl
  ```
* **Offline replay.** The runner is cache-only unless `--live` is given. Every reported run can be reproduced
  offline from the committed cache at $0; replay of evalg250 was checked at 338/338 identical decisions.
* **Live runs** need `--live`, `--max-calls`, `--max-usd`, `--rpm 10`. The runner refuses when `GEMINI_API_KEY_1`
  or `_2` is set. On a daily-quota 429 it stops, and rerunning resumes from the cache. The `--max-usd` cap applies
  per run, so a resumed run should get only the remaining budget.
* **Gitignore.** `*.jsonl` is ignored repo-wide. Label and run files are committed with `git add -f`.
* **Reproducible CIs.** The scorer re-execs itself with `PYTHONHASHSEED=0` so the company-clustered bootstrap CI is
  reproducible.
* **Commit trailers** used on this project:

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01HeMZx7A5oSDmfaACHXU2oJ
  ```

## 6. Key commits on `experiment/v3.2-hybrid`

| Commit | What it holds |
|---|---|
| `ab98854` | identity gate |
| `da6a3a3` | rubric v2, packet/prompt v2, gated arms, spend cap |
| `7744a15` | pre-registration v2 |
| `9879b00` | evalh400 draw |
| `4f3f9f0` | evalh400 census |
| `fb02ca9` | minimisation fix and addendum |
| `28c71e9` | evalh400 blind labels |
| `68b8273` | scorer and review kit |
| `9ae1478` | remediation report |
| `e3589ba` | partial-run guard |
| `3c61b2f` | single-key runner and owner override |
| `ac1aa2c` | Builderr disclosure draft |
| `40309fa` | **final evalh400 result** |
