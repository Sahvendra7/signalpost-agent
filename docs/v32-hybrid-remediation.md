# V3.2 — Hybrid remediation and independent validation

Status: experimental, branch `experiment/v3.2-hybrid` (from `a025a98`). Nothing is pushed, merged or submitted. The
release candidate `v3.1-candidate-2` (code `334a085`, branch `claude/awesome-sagan-m2lppu`) is unchanged: no file under
the release run path was modified, the identity gate is a new module the run path does not import (tested), and Gemini
stays off unless explicitly enabled.

## 0. Answers for the release decision

| Question | Answer |
|---|---|
| Does the hybrid stay better after the VALMET fix? | **On the consumed diagnostic set, yes; on the independent set, not yet measured.** On evalg250 (diagnostic — the gate was built from its errors), the gated hybrid `C_hybrid_v2` scores 92.9% precision (Wilson 87.0–96.2%) under rubric v1, against 46.2% for V3.1 and 77.0% for the ungated hybrid reported earlier. The pre-registered independent test on evalh400 has not been run: every available Gemini key is an exposed key that has not been rotated, and the runner refuses them (§5). |
| Are wrong-company publications eliminated? | **No.** On evalg250 the gate removes the VALMET-type group-site errors (wrong-company FPs in the hybrid: 30 → 4). On the independent evalh400, V3.1 publishes **23** wrong-company items and the frozen gate removes **0**, because they are a different kind (§4.3). Whether Gemini catches them is the open question of the pending run. |
| Coverage retained | evalg250 diagnostic: `C_hybrid_v2` keeps 117/140 correct items (V3.1: 66/140) and 15/16 companies with any correct news; the gate removed no correct item from the hybrid. evalh400: V3.1 publishes 86/138 correct items, 29/37 companies; the LLM arms are pending. |
| FrP agreement with the adjudicated rubric | Provisional: Gemini (prompt v1) agrees with the rubric-v2 relabel on 32/45 FrP units (71%); it publishes all 10 correct units but also 13 opinion items. Prompt v2 adds the organisations rule but has not been run. The second-person review that would make the rubric-v2 labels adjudicated is prepared but not done (§3). |
| API cost per 100 companies | Measured (prompt v1, 338 calls): $0.12 per 100 sampled companies, about $1.06 per 100 companies that have news candidates, paid-equivalent list price. Estimated for prompt v2 (+~320 input tokens per call): $0.11 per 100 sampled companies, $0.76 per 100 companies with candidates at the 12-unit cap, about $1.04 uncapped. Actual spend so far: $0 (free tier). |
| Privacy and deployment requirements | Norway is in the EEA: production use requires the **paid** tier (free-tier prompts may be used to improve Google products). Also: a data-processing assessment, one billed project with a budget alert and a request quota, minimised packets (contacts masked; only the item's own text), and the off-by-default switch (`GEMINI_ENABLED`, default false) (§5–§6). |
| Opt-in or experimental? | **Remain experimental.** Do not ship as opt-in until the evalh400 run meets the pre-registered bar with a rotated key, the FrP rubric is adjudicated, and the wrong-company classes in §4.3 have a deterministic answer validated on a fresh sample. |

## 1. What was preserved

* Release candidate, tags and branch untouched. Experiment history `experiment/v3.2-gemini` stays at `a025a98`.
* Every cached response, prompt (v1 kept beside v2), run record and label file is kept. Rubric-v1 labels for eval120,
  eval200, eval200b and evalg250 are not changed, and every metric reported earlier stands as reported. evalg250 is
  diagnostic from now on.
* Withdrawn results stay marked as withdrawn in `docs/v32-gemini-results.md`.

## 2. The VALMET attribution problem and the identity gate

**Root cause.** The VALMET AS (Norwegian subsidiary) entry pointed at the Finnish group's global site. Three things
compounded:
1. *Bare-brand alias:* the target was represented by the bare brand "Valmet", which every release on the group site
   mentions.
2. *Single-name website identity:* V3.1 accepted the site as the company's own because the brand matched. In one
   case the English phrase "Valmet as a partner" was even read as the legal form "Valmet AS" after case-folding.
3. *Parent-group site:* nothing distinguished the group's releases ("Valmet Oyj's …", "Valmet Technologies Oy") from
   news of the Norwegian legal entity.

Gemini accepted the parent releases because the packet told it the company was "Valmet" and the site was the company's.
Its quotes verified because they did occur in the wrong text. Quote verification proves provenance, not identity.

**Fix: `src/norway_company_agent/identity_gate.py`.** A deterministic, reusable gate with no company names in the source
(tested).

* The **legal name and organisation number** are primary. A legal form must appear in its written form ("AS" uppercase,
  so "Valmet as a partner" is English), and curly apostrophes are normalised.
* **Site status** is one of `target_operated` (organisation number, exact legal name with form, or registered address),
  `other_entity` (another brand+form entity or another organisation number), `group_site` (brand only, plus registry
  parents that are foreign, or a non-.no domain, or group members sharing the brand), `brand_only`, or `unresolved`. A
  regional unit on a bare-brand network domain, with address-only evidence, is `group_site`.
* **Item decision.** Withhold when the item names another legal entity under the brand without naming the target
  exactly. Withhold on an `unresolved` site. Withhold when a `group_site`/`other_entity` item does not name the exact
  target. A bare brand never establishes identity. Parent and group relationships come only from the registry.
* **Gemini cannot override it.** In `policies.arm_members_v2` the gate is a hard stage. A missing gate entry counts as
  withhold, and the LLM can never publish an item the gate or a V3.1 hard gate withheld.

**Fixtures and tests** (`tests/test_identity_gate.py`, `tests/fixtures/identity_gate/`, trimmed real captures with
sha256 and retrieval time):

| Fixture | Case |
|---|---|
| `valmet_global_group_site` | foreign parent's global site → `group_site`, group releases withheld |
| `logscom_foreign_namesake_site` | foreign namesake company's site → withheld |
| `matsentralen_ost_network_unit` | regional unit on the network's brand domain → `group_site` |
| `rosim_own_site_with_sister_item` | own site; item about a sister AB withheld |
| `fram_marine_own_site` | positive control: own site, items pass |
| `rybak_brand_only_own_site` | positive control: brand-only own site stays presumed own |

There is also a synthetic positive control: an item naming "Valmet AS" with the organisation number passes. 566 tests
pass in the full suite.

**Effect on evalg250 (diagnostic, no API call).** The gate withholds 31 VALMET-type errors, 28 network-unit errors
and 10 namesake errors. It loses 1 correct item: a Rosim framework agreement whose text names "Rosim AB".

## 3. Gemini's role, rubric v2 and FrP

* **Role.** Gemini stays a content classifier. Deterministic stages own source eligibility, identity, date
  verification, provenance and legal-entity restrictions. Packet v2 states the operator status, marks brand tokens
  as "not identity", and passes the gate's facts. Prompt v2 (`news-p2-evidence-v2`) adds entity rules and the
  organisations rule. Strict JSON schema, exact quote verification and structured-output validation are unchanged.
  The prompt invents no dates, facts or relationships.
* **Rubric v2** (`docs/v32-news-labelling-rubric.md`) separates an organisation's *stated action* (a proposal
  submitted, a vote, a meeting held, a campaign launched) from opinion, policy explanation, relayed speech and
  promotional profiles. "Krever" alone is opinion. It also adds an explicit `wrong_company` category.
* **FrP relabel (diagnostic, provisional).** Of the 45 FrP units, 10 are correct under rubric v2, 3 are
  `wrong_company`, 1 is a job ad and 1 is a profile. The rest are opinion or policy items.
* **Second-person review.** Prepared but not done, because it needs a second person. Kits: evalg250
  (`audits/evalg250/review_kit/`, 87 units from 28 companies, ≈25%) and evalh400 (`audits/evalh400/review_kit/`,
  112 units from 57 companies). Each kit has a blind sheet, `form.csv`, `adjudication.csv` and instructions. Until
  then, every rubric-v2 figure is labelled provisional, and agreement (kappa) is not reported.

## 4. Independent evaluation: evalh400

### 4.1 Design (pre-registered before drawing)

`PREREGISTRATION_v2.json` freezes the following before the sample was drawn:
* implementation hashes;
* model `gemini-3.1-flash-lite` and prompt `news-p2-evidence-v2`;
* arms `ARMS_V2`, with `C_hybrid_v2` as primary and `A_filter_v2` as secondary;
* the sample: 400 companies, seed 20261106, from Brreg units with a website, disjoint from every organisation
  number in the repository (overlap with evalg250: 0);
* a cap of 12 news units per company;
* rubric v2.

One addendum, made before any label or model call, fixes a minimisation bug: dotted dates were being masked as phone
numbers. The packets were rebuilt. The scorer checks every frozen hash (with the addendum) before it scores a run.

### 4.2 Status

| Step | Status |
|---|---|
| Draw (400 companies) | done (`9879b00`) |
| Capture, V3.1 replay with reasons, packets v2, gate | done: 433 units from 57 companies (census 593; 160 capped out) |
| Blind labels (rubric v2) | done, committed before any model call (`28c71e9`): 138 correct, 279 incorrect, 16 unsure |
| Second-person review of 112 units | **owner action** |
| Gemini run (433 calls) | **blocked**: keys not rotated (§5) |
| Scoring | deterministic arms done; LLM arms run in one command once the run exists |

### 4.3 Deterministic results (final for these arms)

| Arm | Published | Correct | Incorrect | Unsure | Precision | Wilson 95% | Company-clustered 95% | Item coverage | Company coverage | Wrong-company FP |
|---|---|---|---|---|---|---|---|---|---|---|
| v31 | 190 | 86 | 92 | 12 | 48.3% | 41.1–55.6% | 35.5–61.1% | 86/138 | 29/37 | 23 |
| v31_gate | 190 | 86 | 92 | 12 | 48.3% | 41.1–55.6% | 35.5–61.1% | 86/138 | 29/37 | 23 |

V3.1's false positives on evalh400:

| Category | Count |
|---|---|
| Opinion or promotional profile | 26 |
| Wrong company | 23 |
| Product or service marketing | 22 |
| Structural or default | 7 |
| Advice or educational | 6 |
| Project listing, unrelated, misdated, job ad | 8 in total |

**The gate removes nothing on evalh400.** All 433 units sit on sites the gate rates `target_operated` (312) or
`brand_only` (121). The sample contains no group or foreign-namesake sites. Its wrong-company errors are of kinds the
gate does not model:

| Company | In pool / published by V3.1 | Kind |
|---|---|---|
| TEQT NORGE AS | 11 / 9 | acquisitions announced by the parent group (sister companies), on a site rated target-operated |
| SANDNES TAEKWON-DO KLUBB | 8 / 8 | club subdomain on the federation's platform; federation and other clubs' events |
| ELEDA RAIL NORGE AS | 6 / 4 | group and sister-entity acquisitions on a target-operated site |
| NORINNOVA AS | 2 / 1 | other entity's item |
| ÅKRA BIL AS | 2 / 1 | car manufacturer's news relayed by the dealer |
| STUDIEFORBUNDET NÆRING OG SAMFUNN | 2 / 0 | member organisations' items |

These labels have now been seen, so the gate is **not** tuned on evalh400. Any rule for these classes (for example,
a federation-platform subdomain treated like a network unit, or a group-acquisition item naming only the parent) must
be validated on a new sample.

### 4.4 Running the pending step (owner)

After the conditions in §5 are met:

```bash
uv run python scripts/run_gemini_news_experiment.py --packets measurements/v32-gemini-2026-11-04/datasets/evalh400.packets.jsonl.gz --prompt news-p2-evidence-v2 --model gemini-3.1-flash-lite --experiment-id final-evalh400-news-p2-evidence-v2-gemini-3.1-flash-lite --out measurements/v32-gemini-2026-11-04/runs/final-evalh400-news-p2-evidence-v2-gemini-3.1-flash-lite.jsonl --live --max-calls 450 --max-usd 1.00 --rpm 10
```

```bash
uv run python measurements/v32-gemini-2026-11-04/score_evalh400.py measurements/v32-gemini-2026-11-04/runs/final-evalh400-news-p2-evidence-v2-gemini-3.1-flash-lite.jsonl
```

The scorer refuses a run with another model or prompt, with missing units, or after implementation drift. It reports
precision with both CIs, item and company coverage, FP/FN, wrong-company FPs separately, tokens, paid-equivalent cost
and p50/p90 latency. The 433 calls fit one free-tier project's 500 requests per day. At list price they cost about
$0.43.

## 5. API compliance and security

* **One authorised project.** The runner reads only `GEMINI_API_KEY`. `--key-env` was removed, and no further
  multi-project runs were made.
* **Exposed keys.** All three keys in the environment are still the ones shown in the earlier screenshot (checked by
  sha256 against `out/v32/revoked_key_sha256.txt`, a gitignored file of hashes only). The runner refuses them, so
  **no API call has been made since the remediation started.** The owner must revoke them in Google AI Studio / Cloud
  Console and set one new key.
* **Git history.** A scan of all refs for `AIza…`/`AQ.…` key patterns finds only the synthetic redaction-test strings
  in `tests/test_llm_gemini_experiment.py`; none matches a real or revoked key. One older test string (`a025a98`)
  shared a 6-character prefix with a real key. It was replaced forward with `FAKEKEY`. History was not rewritten,
  because nothing has been pushed and the real keys will be revoked.
* **Spend controls.** `--live` requires both `--max-calls` and `--max-usd`. The runner stops when the paid-equivalent
  cost reaches the cap, and every record carries tokens and cost. Billing cannot be checked from here. If the paid
  tier is used, the owner must confirm an active billing account, a budget alert and a request quota on that one
  project.
* **Minimisation.** Emails and phone numbers are masked; dates, numbers and organisation numbers are kept (tested).
  Packets carry the item's own text and registry facts only.
* **Kill switch.** The provider is disabled unless `GEMINI_ENABLED` is true and a key is set (default: disabled).
  The research runner calls the API only with an explicit `--live` plus both caps. Without them every path is
  deterministic and cache-only, and the release path never calls Gemini.

## 6. Privacy and deployment requirements (unchanged from the API report, restated)

1. Paid tier only for any EEA-facing use. The free tier is acceptable only for this research on public website text.
2. A data-processing assessment covering the following points:
   * public company texts can contain personal names;
   * prompts are logged by Google for a limited period for abuse detection;
   * which processor terms apply.
3. One billed project, a budget alert, a request quota and per-run caps.
4. Minimised packets, and no free-text personal data beyond what the public item contains.
5. Opt-in per deployment, with deterministic fallback and per-item audit records (model, prompt hash, packet hash,
   decision, verified quotes).

## 7. Recommendation

Keep Gemini **experimental**. The identity gate is a sound deterministic improvement and can be considered for V3.1
independently of the LLM, after its own validation on a fresh sample, since it is not yet integrated. The hybrid's
apparent >90% precision exists only on the consumed set from which the gate was built. Three conditions come before
any opt-in:
1. the evalh400 run (primary `C_hybrid_v2`, bar ≥90% precision with useful coverage, wrong-company errors reported
   separately);
2. the second-person adjudication of rubric v2;
3. a deterministic, validated answer to group-acquisition items and federation-platform sites.

Do not merge into V3.1.

## 8. Owner actions

1. Revoke the three exposed keys. Create one key in one project. If paid, confirm billing, a budget alert and a
   quota. Then run §4.4 once.
2. Second-person review: fill `audits/evalg250/review_kit/form.csv` and `audits/evalh400/review_kit/form.csv` blind,
   then adjudicate in `adjudication.csv`.

## 9. Files and commits (this phase)

* `ab98854` — identity gate, fixtures, tests.
* `da6a3a3` — rubric v2, FrP relabel, review kit, packet/prompt v2, gated arms, spend cap, key guard.
* `7744a15` — `PREREGISTRATION_v2.json`.
* `9879b00` — evalh400 draw.
* `4f3f9f0` — evalh400 census, packets, gate results.
* `fb02ca9` — minimisation date fix, rebuild, addendum.
* `28c71e9` — evalh400 blind labels.
* `68b8273` — scorer, evalh400 review kit, deterministic score.
* Diagnostics: `measurements/v32-gemini-2026-11-04/results/evalg250-gate-rescore-diagnostic.json`,
  `evalg250-identity-gate.json`. Independent set: `results/evalh400-score-deterministic.json`.
