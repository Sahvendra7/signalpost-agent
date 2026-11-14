# Signalpost V3.1.2 — final optimization: audit, changes, measurements and release decision

Branch `final/v3.1.2-optimization` (local; **not pushed, not submitted**), based on `e0786d3`
(`memory/v311-final-review`, documentation on top of the V3.1.1 submission commit `408f415`, code `38ff24c`).
Code under test: **`95a5464073054b6717b963f3839541590ecdba52`**. No dependency change
(`git diff 38ff24c 95a5464 -- pyproject.toml uv.lock` is empty). No LLM, no Gemini, no paid API, $0.
Every number below is a local measurement with the assistant's own labels. None is a Builderr score.

## 1. Challenge and scoring, as read on 2026-11-14

Sources read in full: the challenge page, the starter brief, the evaluation contract (scoring version 2), the agent
playbook, the learning harness, the source policy, the starter kit (`README.md`, `OUTPUT_CONTRACT.md`,
`scripts/score_competition_v3.py`).

| Point | Current official wording | Note |
|---|---|---|
| Score | 50 recall and coverage, 30 precision and evidence, 12 synthesis, 8 UX | unchanged |
| Coverage formula | per information type: 70% share of companies covered + 30% share of checked facts found, against the verified union of all entrants and Builderr's crawlers | unchanged |
| Recall scaling | "scaled so the top tenth of entries earns about 80% of the recall points" (leaderboard footnote) | the conversion to points is otherwise unpublished |
| Qualification | an official run, at least 65/100 **and** at least 95% of checked published claims correct and attributed to the right company; a material wrong-company match blocks the run from becoming official | matches Soham's email |
| **Deadline** | **"New entries and revisions are open through November 22"** (page, brief and contract) | **Differs from the 16 November date in the task brief.** 16 November is the closing date of the JBOX site *vote*. The rescore deadline in Soham's email (Sunday 15 November 09:00 IST) is a separate, earlier, personal deadline; whether it still binds should be confirmed with him. |
| Revisions | version 1 plus up to four revised commit hashes, five versions in total; a revision applies only to later batches | unchanged |
| Ranking | mean over every scheduled daily batch while a frozen version is active; an entrant-caused failed batch scores zero; ties: fewer wrong-company publications, then weighted company recall, then lower third-party cost | |
| Batch | 1,000 companies now, may grow to 1,100; the leaderboard round of 13 November used a 500-company set; leading agents will be tested on a larger set | fixed time and resource budget, unpublished |
| LLM | allowed with an evaluator-supplied key; a credential tied to the entrant's own account cannot be used | Gemini stays out |
| UX | "whether a user can find, compare and verify company information on desktop and mobile" | **what artefact is graded is not published** (§6) |
| JBOX prize | separate, sites due 7 November | closed; not pursued |

Leaderboard reviewed 13 November 2026 (104 scored, none qualified): rank 2, 68.70 = recall 34.88, evidence 26.20,
synthesis 7.02 (the highest synthesis on the board), UX 0.60. Rank 1 is 69.27 with UX 4.40 and synthesis 5.28.
The evaluated commit was `ff3b515`.

## 2. Repository and submission state

| Version | Commit | Status |
|---|---|---|
| 1 (initial) | `104c3c4`, tag `submission-candidate-1` | submitted; C12 57.87 |
| Revision 1 | `05d7566` (code `a5e06ce`) | submitted by the owner; C300 row 56.85 |
| Revision 2 | `ff3b515` | submitted; the commit Builderr evaluated (68.70, 75/86 claims correct, 11 wrong-company) |
| Revision 3 | `408f415` (code `38ff24c`), branch `revision/v3.1.1-builderr-rescore` | pushed; the email is drafted for the owner to send. **Whether it was sent is not recorded in the repository.** |
| This candidate | `95a5464` on `final/v3.1.2-optimization` | local only |

Revision count, from the repository's own records: **two revisions submitted for certain (`05d7566`, `ff3b515`); a
third if the V3.1.1 email was sent.** So two revisions remain if it was not sent, one if it was. Only the owner can
confirm this; an unsubmitted local candidate or pushed branch does not count. Verified in this session: the remote
`revision/v3.1.1-builderr-rescore` is `408f415`, `claude/awesome-sagan-m2lppu` is `139e23c`, `claude/c300-refresh-fix`
is `ff3b515`, tag `submission-candidate-1` is present; nothing was pushed, merged or rewritten.

## 3. Diagnostic audit

A diagnostic live rerun of V3.1.1 (`38ff24c`) on eval-r200c (200 organisations with a registry-listed website) gave
the family funnel below. Every external family depends on a verified website, so the website stage is the recall
bottleneck.

| Registry-listed website outcome (200) | Count |
|---|---|
| Published as `official_website` | 61 |
| Held for identity (`ambiguous`) | 51 (+9 held as a related manager or group site) |
| Hostname does not resolve (checked: dead on bare and `www` hosts) | 35 |
| "robots.txt unreachable" | 25 |
| robots disallow / 401 / 403, HTTP 404, platform host, other | 19 |

| Scoring category | Weakness | Code | Evidence | Change | Risk |
|---|---|---|---|---|---|
| Recall | **Confirmed defect.** The http fallback for a bare registry host was unreachable when the https `robots.txt` request got no connection; the site was reported "robots.txt unreachable" | `website.py` `fetch_website`, `_robots_check` | 25/200 on r200c; several answer over http | fallback when https gives no connection at all (not on 5xx/429/401/403, not for an explicit scheme) | reaches more dead and parked hosts (handled below) |
| Recall | **Recall opportunity.** Own sites held because the name is written together in the domain, carries another legal-form word, or is a sole proprietor's trade or personal name | `identity.py` `assess_website_identity` | about 15 of the 51 held sites on r200c were evidently the entity's own | four narrow rules (§4) | wrong-company and placeholder pages (two audit rounds, §5) |
| Precision | **Confirmed defect, also in V3.1.1.** Registrar "is parked" pages published as the official website when the title repeats the domain | `identity.py` single-word rule | `råde.skytterlag.no` (r300d, baseline), `www.reva.no` (r300e) | registrar, host and error pages are never websites; on a thin page the domain is not identity text | 2 baseline claims withheld on 800 organisations, both parked pages |
| Precision | **Confirmed defect, also in V3.1.1.** A foreign-registered "… AB" whose registry site is its Norwegian parent "… AS" | `attribution/operator.py` | SVELVIK MASKIN AB on r300f (both arms) | mirror of the V3.1 foreign-namesake rule | narrow: needs 3 statements and a 3:1 ratio |
| Synthesis | **Missing feature.** A company with a verified site had `overview: null`; only registry-only companies had a lead paragraph | `synthesis.py` | 61/200 on r200c | lead paragraph = the cited "At a glance" statements | none (no new statement) |
| UX | **Unknown rubric.** The viewer (search, compare up to four, source and date of every fact, desktop and phone) is written by the documented command and still scored 0.60 | `viewer.py` | leaderboard clusters at 0–1.6 and 3.8–4.6 | none in code; see §6 | — |
| Recall | **Not changed.** News and job coverage low by design (7–11 news per 200–300 organisations, 0–5 job ads) | `attribution/news.py`, `jobs.py` | r200c, r300d–f | none: no rule with measured precision near 95% is available | stays the largest unrealised recall |
| Operational | "Hostname did not resolve" is reported as `blocked` | `website.py` | 35/200 | none (a state rename would create refresh changes) | low |
| Needs external data | The other 9 of Builderr's 11 rejected claims; the precision-to-30-points conversion; the UX and synthesis rubrics; the run budget | — | not available | ask Builderr | — |

## 4. Code changes (`38ff24c` → `95a5464`)

All rules are general; no company, domain or URL is named in code. Tests: `tests/test_v312_coverage.py` (24 tests, 15
subtests: each rule, its limits and positive controls).

**`website.py`** — `_robots_check` tells "no connection" (TLS failure, reset, refusal, timeout) apart from a server
answering 5xx/429. For a registry value without a scheme, `fetch_website` then tries `http://` under that host's own
`robots.txt`. No fallback for an explicit scheme, a server error or a 401/403.

**`identity.py`** — for the registry-listed website only, after every earlier rule:
* the homepage states the legal name, its trailing legal-form word aside (registered "… AKTIEBOLAG", written "… AB");
* the domain label is the legal name written together (two or more name words), the page's own text writes the name,
  and the domain is `.no` or the pages carry the registered postcode or town;
* sole proprietorship: the domain is exactly the trade name (the legal name without the registered owner's name, from
  the roles register) and the page writes it; or the domain carries the owner's name and the homepage states it.

Guards on those rules: a page naming another company with a legal form and a word of this entity's name is that
company's (a clinic's AS, the AS a proprietorship became); soft placeholder wording.
For **every** name rule: `host_placeholder` (registrar, web-host or error wording on a one-page capture under 600
characters) is never a website; on such a thin capture the hostname and the domain written in the title are not
identity text.

**`attribution/operator.py`** — `norwegian_namesake_named`: a foreign-form company whose site writes its name as a
Norwegian AS/ASA at least three times and three times as often as its own form; the site is held as
`related_not_exact`.

**`synthesis.py`** — the lead paragraph for companies with a verified site.

## 5. Measurements

Samples are organisations with a registry-listed website, drawn with `draw_sample.py` (disjoint from every
organisation number on every branch) and committed before any run on them. Arms ran live, one after the other, on
the same day. A replay of both code versions on the same capture confirms that the candidate loses no claim; the
few claims that differ between live arms in the other direction are run-to-run variation of the web.

| Sample | Role | What happened |
|---|---|---|
| eval-r200c | **diagnostic** (consumed by V3.1.1; used here to find the gaps) | 61 → 70 websites on a re-assessment of the capture |
| eval-r300d (seed 20261116) | first run of `f59c46a`; **diagnostic** after it | 12 websites added; reading them found a clinic's site, a host placeholder and a foreign parent's name-shaped `.com` → guards `af47dee` |
| eval-r300e (seed 20261117) | drawn after the `af47dee` freeze; **diagnostic** after it | 13 added, 5 of them parked, expired or broken pages → structural placeholder rules `34b7336` |
| eval-r300f (seed 20261118) | drawn after the `34b7336` freeze; **independent** for code `2fdd64d` | below |

### 5.1 eval-r300f — independent check of the frozen `2fdd64d` against V3.1.1 `38ff24c`

Every published external claim of both arms was labelled on one sheet (`audit-r300f/`, 202 units).

| Family | V3.1.1 published / companies | V3.1.2 published / companies | V3.1.2 correct / incorrect / unsure |
|---|---|---|---|
| Websites | 98 / 98 | 101 / 101 | 99 / 1 / 1 |
| Social profiles | 84 / 49 | 85 / 50 | 83 / 0 / 2 |
| News | 8 / 5 | 7 / 5 | 5 / 1 / 1 |
| Careers pages | 4 / 4 | 4 / 4 | 3 / 0 / 1 |
| Job ads | 0 | 0 | — |
| **All** | **194** | **197** | **190 / 2 / 5** |

* **V3.1.2: 190/192 decided claims correct = 99.0% (Wilson 95% CI 96.3–99.7).** Counting the 5 unsure as wrong:
  190/197 = 96.4% (92.8–98.3). Wrong company: 1/192.
* V3.1.1 on the same sample: 186/188 = 98.9% (96.2–99.7); 95.9% (92.1–97.9) with unsure as wrong; wrong company 1.
* The two incorrect claims are in **both** arms: SVELVIK MASKIN AB's site is Svelvik Maskin AS's (wrong company;
  fixed after the audit in `95a5464`, so that fix is diagnostic on this sample), and a public-health notice published as
  a kindergarten's news (not company news; not changed).
* **Limits.** Labels are the rule author's, from the organisation name, URL, page title and, for doubtful claims, the
  captured text; they were not made by reading every page and were not reviewed by a second person. The sample is
  300 organisations. The 95% threshold is not claimed; only Builderr's check can establish it.

### 5.2 Coverage: the official 70/30 formula against the local union (relative proxy only)

Reference = claims published by either arm and not labelled incorrect or unsure-excluded as stated in
`compare_runs.py`. This is **not** Builderr's pool, so the values compare the two versions; they are not recall.

| Family (r300f) | Reference facts / companies | V3.1.1 weighted | V3.1.2 weighted |
|---|---|---|---|
| Websites | 103 / 99 | 0.958 | 0.988 |
| Social profiles | 83 / 50 | 0.982 | 1.000 |
| News, careers | 5 / 3, 3 / 3 | 1.000 | 1.000 |

Websites published, V3.1.1 → candidate, by sample: r300f 98 → 101; r300e 94 → 106 with the frozen `af47dee`, of which
5 were placeholder pages now withheld (about 94 → 100); r300d 112 → 124 with `f59c46a`, of which 3 are now withheld
(about 112 → 121). **The gain is about 3–8% more verified websites, with the social profiles that follow.** It is
real but small; it does not change news or job coverage.

### 5.3 Score sensitivity (no prediction)

* Known: 68.70 on `ff3b515`; the qualification gates (65 and 95%).
* Measurable here: claim precision on our samples, relative website and profile coverage, completeness, runtime.
* Unpublished: the pool, the recall scaling beyond the footnote, how precision maps to 30 points, the synthesis and
  UX rubrics, the run budget.
* What moves the result most: (1) the 95% gate — it decides qualification, and no entry has passed it; (2) UX, where
  7.4 points are open and the leader's whole margin over us is UX; (3) synthesis, 5 points open; (4) recall, where
  we are already within 0.1 of the best value on the board, so a few percent more websites is worth little and
  recall can only fall if others add verified news and jobs we do not publish.

## 6. UX: finding and zero-cost options

The viewer was checked again on the candidate (Chromium, 1366×900 and iPhone 13: no page error, no horizontal
scroll, lead paragraph shown). It lets a user find a company, compare up to four and open the source and retrieval date
of every fact, and the documented command writes it on every run. It scored 0.60 all the same, and 0.60 is the
value most entries have. Entries at 3.8–4.6 are a separate cluster. The likely explanation, **not confirmed**, is
that the grade is taken from something reachable (a hosted page or link) and not from an HTML file among run outputs.

Options that cost nothing, in order:
1. **Ask Soham what artefact the UX grade is taken from** (one line in the email, §9). This is the only way to
   know.
2. Host the committed 100-company viewer (`measurements/v312-final-2026-11-14/runs-final-95a5464/live-100.envelopes.viewer.html`,
   1.4 MB, static, no server) on a free static host (GitHub Pages or a free Vercel project) and give the link in the
   email. It publishes only public registry and company-website data. This needs the owner's go-ahead because it
   publishes a page; it was not done.

## 7. Release validation of `95a5464`

| Check | Result |
|---|---|
| Full suite, working tree | **594 passed, 208 subtests passed** |
| Clean room (fresh clone, empty uv cache) | `95a5464`: `uv sync --locked` exit 0; **594 passed, 208 subtests**; documented command (987832827 LØWEHJERTE + 923609016 Equinor, live) exit 0, source sha256 `b92b72a8…` = the smoke run; LØWEHJERTE publishes no profile, Equinor keeps its 3 accounts and careers page. (`2fdd64d` earlier: 592 passed.) Logs in `measurements/v312-final-2026-11-14/cleanroom/` |
| 100-company smoke (live, fixed input `measurements/submission-smoke-2026-10-03/input-companies.jsonl`) | 100/100 `completed` in input order; report validation passed; **0 contract findings; 3,969 evidence hashes re-verified, 0 mismatches** (4 website-module entries without a stored snapshot, as before); 197 hosts, **no social-platform host**; $0; no LLM; 0 unsupported summary statements; 100 s. Published: 16 websites, 11 profiles, 2 news, 4 careers pages (identical counts to `38ff24c`) |
| Refresh through the run history | baseline = published envelopes for 100/100; **1 `unavailable` event**, no removal, no false change |
| Reproductions (20, live) | as V3.1.1: LØWEHJERTE publishes no profile; Tyin, Bartec, Logscom, Valmet held as related; Bergknapp 3, BK Bygg 2, BioMar 3, Grønsand 2, Eleda Rail Norge 2, Three60 1, Birkeland 2, Fundraising Norge 2 profiles kept; BE Kraftsalg's own-number site kept |
| Independent sample | eval-r300f, 300/300 `completed`, §5.1 |
| Runtime | 300 organisations in 9–10 minutes in this environment (about 1.9 s each); smoke 1.0 s each |
| Secrets | no key-shaped string added; no new environment variable |
| Dependencies, cost | unchanged from V3.1.1; $0 |

Not done: a batch above 300 in this session; a second-person label review; a rerun of eval-r300f after the
post-audit fix as a new independent sample.

## 8. Limitations and risks

* The new website rules needed two rounds of guards before a clean independent sample. A third unseen class is
  possible. On r300f they published 2 sites, both correct; across the three samples about 20, with no wrong company
  after the guards.
* The http fallback reaches hosts V3.1.1 never read. Most are dead or parked and are now withheld, but each is a new
  page to judge.
* Labels are not independent; CI lower bounds sit near or below 95% when unsure claims count as wrong.
* News and job coverage is unchanged and low. If Builderr's pool holds many verified news items and job ads from
  other entrants, recall falls relative to them whatever this candidate does.
* The remaining incorrect class seen: a notice that is not company news passing the announcement tier.
* UX and synthesis rubrics are unknown; the lead paragraph is a guess at what a grader reads first.
* The 9 unidentified claims of Builderr's 11 remain unknown.

## 9. Release decision

**Recommendation: keep `408f415` (V3.1.1) as the commit for the rescore that is due now, and submit `95a5464` as the
next revision only after the owner has (a) confirmed how many revisions are left and (b) had the eval-r300f labels
looked at by a second person, or accepted that they are not.**

Why, against the scoring rules:
* Qualification is decided by the 95% gate. On the one independent sample, both versions measure the same
  (99.0% and 98.9%); V3.1.2 removes two confirmed error classes that V3.1.1 still has (parked pages, the Norwegian
  namesake) and adds one new source of risk (the new identity rules and the http fallback).
* The recall gain is small (3–8% more websites) on a component where the entry is already at the top of the board.
* A revision is scarce (one or two left) and "applies only to later batches". Spending one for a few percent of
  website coverage is poor value unless it also carries a UX or synthesis gain that Builderr confirms is graded.
* If V3.1.1 has **not** been sent yet, sending `95a5464` instead is defensible: it is a superset of V3.1.1's fixes,
  validated on a fresh sample, and costs the same one revision.

Submission details for `95a5464`, if the owner chooses it: `docs/v312-builderr-email.md`.
