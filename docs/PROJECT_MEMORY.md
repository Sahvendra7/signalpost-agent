# Signalpost — project memory

Updated 2026-11-14 at the end of the **V3.1.1 Builderr rescoring revision** session, so a new session can resume
without the old chat. Read this first, then the documents it points to. (The V3.2 Gemini research memory, written
2026-11-13, is on branch `experiment/v3.2-hybrid` in `docs/PROJECT_MEMORY.md`; its essentials are in §6 below.)

## 0. Where we are right now (read this first)

* **Builderr feedback (Soham Sinha) on the evaluated commit `ff3b515`:** rank 2/104, about 69/100, 86 claims checked,
  75 correct, **11 belonged to another company** (87%). Qualification needs ≥65/100 **and** ≥95% correct attribution.
  Asked for: (1) remove every claim belonging to another company; (2) add genuine dated company news and open job
  postings linked from the company's own site ("we have nothing verified from you there").
  Confirmed examples: LØWEHJERTE DESIGN AS (987832827) →
  `https://www.linkedin.com/company/squarespace/mycompany/verification/` and `http://facebook.com/squarespace`.
  The other 9 are unknown (Builderr's sample is not available); do not invent them.
* **Deadline for giving Builderr repository + branch + exact commit: Sunday 2026-11-15, 09:00 IST (03:30 UTC).**
* **Revision done:** branch `revision/v3.1.1-builderr-rescore`, based on `139e23c`.
  * **Release commit `9d99cba61493e99664db16c78fd37e84408e4408`** (docs/measurements) — code-identical to
    **`38ff24c48e989a987529f4f7d6ca3fa107bce75d`**. A later commit on the branch adds only this memory file and
    `CLAUDE.md` (no code). Check with `git diff 38ff24c <commit> -- src tests scripts pyproject.toml uv.lock` (empty).
  * Full report: `docs/v311-rescore-revision.md`. Email draft: `docs/v311-builderr-rescore-email.md`.
  * **Status: awaiting the owner's review.** Push only if the owner says so in that session; submit to Builderr only if
    the owner says so. As of this writing it had **not** been pushed or submitted (see §5 for whether a push happened).
* **Before sending the email:** replace `<RELEASE_COMMIT_SHA>` with the release commit, add the owner's name, and fix
  one sentence: the draft says "3 belonged to a related entity"; it should say "4 were incorrect, 3 of them belonging to
  a related entity" (the fourth was a careers-page article).

## 1. Standing rules from the owner (always apply)

* **Release.** Never modify the V3.1 release branch `claude/awesome-sagan-m2lppu` (`139e23c`, code `334a085`), the
  evaluated commit `ff3b515`, or tag `submission-candidate-1`. Do not rewrite history.
* **No automatic actions.** Never push, merge or submit to Builderr without an explicit owner instruction in the
  current session. Make local commits as work progresses.
* **Determinism and cost.** Default execution: no LLM, no paid API, $0, no social-platform fetching (LinkedIn,
  Facebook, Instagram, YouTube, X, TikTok are never fetched). Only the Brønnøysund registry APIs and companies' own
  websites.
* **Gemini.** Disabled by default and kept out of the release path; no code from `experiment/v3.2-hybrid` in a
  release. Free tier only, one project, one key (`GEMINI_API_KEY`), $0 spend; the owner accepted the exposed key on
  2026-11-06 (`--owner-accepts-exposed-key`). Never print, log or commit a key value; check by sha256 only.
* **Accuracy first, then genuine coverage.** Never fabricate or weaken evidence; never remove valid claims just to
  improve a ratio; no company-specific allowlists, URL exclusions or hardcoded exceptions.
* **Evaluation honesty.** Do not tune on a labelled set and call its score independent. Never report a partial run as
  complete. Do not change committed labels. Report only results of tests actually run. Never claim a Builderr score
  or the official 95% threshold from local tests. Labels so far are by the assistant (the rule author), not the owner.
* **Repo convention.** `AGENTS.md` asks to explore code with the Graphify MCP tools (`query_graph`, `get_node`) when
  available (they were not available in the V3.1.1 session; grep was used).

## 2. V3.1.1 — what changed (details: `docs/v311-rescore-revision.md`)

* **Root cause of the confirmed error:** `ff3b515` accepted any profile in `sameAs` of the site's own Organization
  JSON-LD; Squarespace templates fill it with Squarespace's own accounts. Other `ff3b515` wrong-company classes found
  on a new sample: business manager websites (usbl.no, vestbo.no…) published as a borettslag's/sameie's own, group
  websites, group social accounts, parent news on a subsidiary's site, job boards of other employers.
* **Social** (`attribution/social.py` `owner_check`, runs before the handle decision; sameAs cannot override):
  platform/builder accounts; admin/verification URLs; national-unit handle without its marker on a group site;
  foreign registry parent (konsernstruktur, UTLA); profile localised abroad on a group site; brand shared with other
  registry-group companies (Moelven); CamelCase handles ending in a legal form (Birkeland Tyse Bergsprenger As).
* **Websites** (`claims.py` `_annotate_site_operator`): a business manager's, another company's or a group's site is
  held as `ambiguous` with `relation: related_not_exact`, `related_url`, reason (Builderr's sample uses
  "related_not_exact · withheld"); a group-named site stating the company's own org number stays (BE Kraftsalg).
* **News** (`attribution/news.py` `announcement_decision`; default tier "announcement";
  `SIGNALPOST_NEWS_PUBLICATION=anchored` reproduces V3.1 exactly): after every V3.1 rule, only headline announcements
  (acquisition, appointment, agreement, opening, award, anniversary, launch, certification, annual meeting, new name,
  grant) that name the company and have their own article URL; launch headlines must name the company; group/parent
  rules (foreign parent on a non-.no site, national unit's bare group brand, international brand site never writing
  the legal name). The **Søknadsfrist defect is fixed** (labels in a separate element before the date are read).
* **Jobs** (`attribution/jobs.py`, `site_facts.py`, `site_research.py`): employer named in the title is checked; off-site
  ads (Finn, Jobbnorge, ATS) need a verified employer (named, or ATS address carries the name, or title names the
  company); several unlinked postings on one page are not individual ads; job boards of other employers are not the
  careers page; crawler follows up to 3 undated positions on the own domain to date them (`MAX_JOB_FETCHES`).
* Tests: `tests/test_v311_rescore.py` (37 tests), fixture `tests/fixtures/v311/987832827/` (LØWEHJERTE),
  `tests/conftest.py` (legacy V3.1 test modules run under the anchored news tier). Four V3.1 tests were updated to the
  new website behaviour (Tyin, Logscom, Bori, viewer).

## 3. V3.1.1 — results (all measured; assistant labels; not Builderr scores)

* **Independent: eval-r200c** (200 new companies, seed 20261115, drawn before the final code ran on it; code
  `7a88046`, replays show `38ff24c` identical on it): **134/138 decided published external claims correct = 97.1%
  (Wilson 92.8–98.9)**; 93.7% if the 5 unsure count as wrong; wrong company 3/138. Websites 60/60, social 60/62,
  news 6/7, careers 8/9, job ads 0. **The 95% threshold is not claimed.**
* **eval-r300** (300 new companies, seed 20261114): post-freeze audit of the frozen candidate `44d0cd3`, then
  **diagnostic** (fixes made on it). `ff3b515` there: websites 97/110, social 70/77, news ~46% of 446, careers 9/18,
  jobs 2/6. Frozen V3.1.1: websites 97/110, social 67/70, news 15/20, careers 11/11. After fixes (diagnostic): all
  decided claims correct; 98.9% of `ff3b515`'s correct non-news claims retained.
* **Release validation of `38ff24c`:** suite 570 passed + 193 subtests (working tree and clean room); smoke100 100/100,
  0 contract findings, 3,968 hashes 0 mismatches, no platform host, $0; refresh 1 `unavailable` event (AUTO24 outage),
  no false change; 21 reproductions as intended (positive controls Logscom, ASAK, Ashtead, Tyin, Bergknapp, Bartec,
  BioMar, Grønsand etc.); viewer OK on desktop and phone.
* **Known limitations:** news and job coverage low by design (job ads rarely publish: undated cards); a chain's accounts
  on one member's site when the chain is no registry group (WANG); same-name related entities (Oslo Klatresenter);
  parish sites shared by several sokn labelled correct; samples small.

## 4. Where things are

| Item | Location |
|---|---|
| V3.1.1 revision (current) | branch `revision/v3.1.1-builderr-rescore`; release `9d99cba`, code `38ff24c` |
| V3.1.1 report / email draft | `docs/v311-rescore-revision.md`, `docs/v311-builderr-rescore-email.md` |
| V3.1.1 measurements | `measurements/v311-rescore-2026-11-14/` (inputs, `audit/` = eval-r300, `audit-r200c/`, `runs*/`, `cleanroom/`, scripts `draw_sample.py`, `run_validation.sh`, `analyse_run.py`, `build_audit.py`, `score_audit.py`) |
| Manifest / handoff | `docs/final-submission-manifest.md` (V3.1.1 section on top), `HANDOFF.md` |
| V3.1 release (stable, unchanged) | branch `claude/awesome-sagan-m2lppu` (`139e23c`, code `334a085`) |
| Evaluated by Builderr | `ff3b515` (branch `claude/c300-refresh-fix`) |
| V3.2 Gemini research | branches `experiment/v3.2-gemini`, `experiment/v3.2-hybrid` (memory there: `docs/PROJECT_MEMORY.md`) |
| Fixture builder from a live run | `scripts/build_fixture_from_snapshot.py` |

## 5. Open items (owner decisions)

1. **Review the V3.1.1 release** (`docs/v311-rescore-revision.md`).
2. **Push** `revision/v3.1.1-builderr-rescore` — only on explicit instruction. Until pushed, the branch exists only in
   the container it was made in. *(If this memory file is being read from GitHub, the branch was pushed.)*
3. **Send the rescore email** (after the fixes in §0) before 2026-11-15 09:00 IST — the owner sends it, not Claude.
4. Optional: owner/second-person review of the eval-r200c labels (`measurements/v311-rescore-2026-11-14/audit-r200c/`).
5. V3.2 open items (second-person review kits, Builderr disclosure if Gemini is ever mentioned) — see the hybrid branch.

## 6. V3.2 Gemini research — essentials (full memory on `experiment/v3.2-hybrid`)

* evalh400 (independent, pre-registered) news precision: V3.1 48.3%, Gemini filter 84.0%, hybrid 82.3%; the 90% target
  was not met. 433/433 free-tier calls, $0 spent. Recommendation: develop the hybrid only as a future opt-in; not the
  default. evalg250 and evalh400 are consumed (used as diagnostic sets in V3.1.1).

## 7. How to work in this repo (gotchas)

* Install: `uv sync --locked`. Tests: `uv run --with pytest python -m pytest -q -p no:cacheprovider` (a bare
  `uv run pytest` picks up a system pytest). Expect 570 passed, 193 subtests on `38ff24c`.
* Documented run command: `uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output
  out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots
  --run-id <RUN_ID>`.
* **`*.jsonl` is gitignored repo-wide**: commit inputs/labels with `git add -f` (an un-added input broke a run once).
* Replay a capture offline: `scripts/replay_run.py` (needs the captured profiles + snapshots). Replay is not perfect
  for every site (a few pages are not re-served); compare a replay with a replay of the same code, not with the live run.
* `ff3b515` has no `replay_run.py`; measure it with a live run the same day. Its host-audit hook must be run from its own
  tree (`<tree>/measurements/final-validation-2026-10-03/host_audit.py`).
* New samples: `measurements/v311-rescore-2026-11-14/draw_sample.py REGISTRY.csv.gz OUT.jsonl SEED COUNT` excludes every
  organisation number on every branch. Registry CSV: `https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv`.
* Commit trailers:

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01HeMZx7A5oSDmfaACHXU2oJ
  ```
