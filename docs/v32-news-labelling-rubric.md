# News labelling rubric v2 (V3.2)

Status: adopted 2026-11-06 for every sample labelled after this date. Earlier labels (eval120, eval200, eval200b,
evalg250) were made under rubric v1 (`docs/v3-accuracy.md` §5) and are **not** changed. Metrics already reported on
them stand as reported. evalg250 is diagnostic from now on.

## 1. The question a label answers

> Is this a dated item in which **the exact target legal entity** reports **its own development, action or event**,
> and is it dated correctly as far as the captured page shows?

Label `correct` only if all three hold: the item is about the target entity, it reports something the entity did or
will do, and its date is the date the page shows. Label `incorrect` if any fails clearly. Label `unsure` only if the
captured text cannot settle it (for example, a title-only card whose subject or role is not shown). Never use
`unsure` for a hard judgment call that the text does settle.

## 2. Entity (who)

| Situation | Label | Category |
|---|---|---|
| The item is about the target entity, by name, organisation number or first person on the target's own site | correct (if §3 holds) | — |
| About a parent, sister, subsidiary or other group company; the group's releases on a group site | incorrect | `wrong_company` |
| About a national federation, chain or network the target is a member or unit of | incorrect | `wrong_company` |
| About a foreign entity with the same brand (Brand AB, Brand Oyj, Brand Inc.) | incorrect | `wrong_company` |
| About a customer, supplier, member or partner where the target only appears as a participant | correct only if the item reports the *target's* action (a delivery, a project it carried out); else incorrect, `wrong_company` | |
| Journalism by a publisher about third parties | incorrect | `unrelated` |

A brand mention alone never makes an item about the target. On a group or network site, the item must name the target
entity (legal name, organisation number, or an unambiguous local unit name stated as that entity) to be `correct`.

## 3. Content (what)

**Counts:** contracts, orders and deliveries; completed projects for named clients; launches, openings and new
locations; appointments and hires announced; acquisitions and ownership changes; partnerships; awards and
certifications; financial results; events the entity holds, takes part in or sponsors; anniversaries; reports, books
and publications the entity itself issues; an artist's, club's or association's own performances, results and
activities; a public body's own service changes and events (vaccination days, new station opened).

**Does not count:**

| Content | Category |
|---|---|
| Guides, tips, explainers, FAQ, thought leadership, regulatory explainers | `advice_or_educational` |
| Product and service pages, offers, price lists, product-improvement marketing | `product_service_marketing` |
| Reference-project portfolios, property listings | `project_or_property_listing` |
| Op-eds, columns, debate posts, testimonials, customer and staff profiles | `opinion_or_promotional_profile` |
| Vacancies and calls for applicants | `job_advertisement` |
| Default posts, landing pages, calendars, theme demo content | `structural_or_default` |

## 4. Organisations' statements (political parties, associations, unions, NGOs, public bodies)

This section resolves the FrP cases. An organisation's statement is **news about the organisation** only when the
text reports an **action the organisation (or an officer acting for it) has taken or will take**:

* **correct** — it formally submits a proposal ("fremmer åtte forslag", representative proposal), asks a formal
  question of a minister, requests a hearing or a control-committee case, votes or decides, elects or appoints its own
  officers, holds a meeting, conference or national-board meeting, launches a campaign, publishes its own report or
  programme, joins with another party in a stated initiative ("går sammen med KrF for å be om …"), wins or loses a
  vote, or announces a candidate;
* **incorrect, `opinion_or_promotional_profile`** — it comments on or criticises others without stating its own
  action ("Ap svikter oljearbeiderne", "Skuffende og arrogant", "Et puslete svar"), explains its general policy
  ("FrP vil ha flere i arbeid"), or reports a politician's opinion of a budget, a report or an event;
* **incorrect, `opinion_or_promotional_profile`** — profiles and interviews promoting a person ("Møt …");
* **news of an affiliated but separate legal entity** (a youth organisation, a local branch with its own
  organisation number) is `wrong_company` unless that entity is the target.

"Krever" (demands) alone is opinion. "Krever svar … og løfter saken inn i kontrollkomiteen" states an action and
counts. A leader's speech counts when the item reports the speech as an event of the organisation (a national-board
meeting held). It does not count when the item only relays the opinions expressed.

## 5. Date

* The label checks the date the pipeline attached against what the captured page shows. A bulk re-publication date
  (many posts sharing one date, contradicted by an earlier event date in the text) is `incorrect`, category `misdated`.
* Event pages (concerts, matches) count, with the event date, when they are the entity's own events.

## 6. Procedure

* Blind: the labeller sees only the captured text sheet. There is no arm, no deterministic reason and no model
  output.
* Every `incorrect` label carries one category from §2–§5. `wrong_company` is reported separately in every
  evaluation.
* A second, independent person labels a random 25% (stratified by company) blind. Disagreements are recorded in
  `adjudication.csv` with both labels, the rubric clause and the adjudicated label. The adjudicated label is used for
  scoring; the first-pass agreement (Cohen's κ) is reported.
