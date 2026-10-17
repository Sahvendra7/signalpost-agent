# Deterministic company summary

Every envelope carries `company_summary`, built by `src/norway_company_agent/synthesis.py` from that
envelope's own claims. No LLM is used (`llm_used: false`); the optional LLM layer stays off.

## Shape

```json
{
  "method": "deterministic_template_v2", "language": "en", "llm_used": false,
  "sparse": true, "overview": "Public information found was limited to official registry records: …",
  "sections": [{"id": "leadership", "title": "Leadership",
                "statements": [{"text": "Chief executive (daglig leder): Kari Nordmann.",
                                "claim_keys": ["…"], "evidence_ids": ["ev_…"]}]}],
  "text": "plain-text rendering of the same statements"
}
```

The sections, always in this order, are:

1. At a glance
2. What the company does
3. Key company facts
4. Leadership
5. Locations
6. Financial snapshot
7. Website and public footprint
8. What changed
9. What remains unknown

## Rules

- **Facts come only from available claims.** Each statement is a fixed template filled with claim values,
  and lists the `claim_keys` and `evidence_ids` it rests on. That gives the FACT → SOURCE → DATE chain.
- **Every statement cites what it reports.** A statement about something unknown cites the non-available claim
  (its key, state and recorded reason). Only fixed method notes ("No previous run was supplied, …") cite nothing.
  `tests/helpers/summary_check.py` checks that every date, NOK amount and organisation number in a statement occurs in
  a claim it cites.
- **At a glance** repeats the decision-relevant facts in a few cited sentences: what the entity is (legal form in
  English, place, founding date), what it does (registered words and industry), the most recent figures with their
  reporting period, the employee count or that it is unknown, and the verified public footprint. It adds no fact.
- **Source text is quoted verbatim.** Registered activity, statutory purpose and the website description
  are not translated or paraphrased. Long text is cut at a word boundary and ends with `…`.
- **Reporting periods.**
  - "Most recent" means the newest reporting period that has figures, for each account type (company or group
    accounts), with its exact from–to dates and currency. Earlier periods are listed and cited.
  - This is checked against the registry's own last-submitted year (`sisteInnsendteAarsregnskap`). If the two agree,
    the year is called latest. If the registry names a newer year than the figures, the summary says the newer
    figures are missing and lists that under unknowns. If the registry names an older year, it is not called latest.
  - Two different figures for the same metric and period are contradictory evidence. Neither is reported, and the
    conflict is listed under unknowns.
- **What changed** is stated only against a supported earlier observation:
  - a previous run (`--previous-profiles`): the typed change events, citing the current fact;
  - the immediately preceding reporting period, when both are consecutive twelve-month periods in one currency.
    Revenue, operating result, net result and equity are compared one by one ("higher", "lower" or "unchanged",
    with both cited values). There is no trend or growth wording, and no multi-year story. Periods that cannot be
    compared (a short first year, a gap, another currency) are named as not compared;
  - the registry's own dated record of the last change to registered roles, which does not say what changed.

  Without any of these, the section says that nothing can be assessed.
- **Unknown is not the same as absent.**
  - `not_available` means "Checked; nothing found".
  - `failed`/`blocked` means "Could not be checked in this run".
  - `ambiguous` means "Candidates were found but not confirmed as this company".
  - `not_applicable` means "Not attributed to this company" (for example a business manager's own content).
  - A missing employee count is unknown, never zero. The claim's reason records whether the registry says a count is
    registered (`harRegistrertAntallAnsatte`). Only a stated `antallAnsatte` of 0 is shown as 0.
  - Values kept from an earlier run because a source failed are flagged `carried_forward` and listed under
    "What remains unknown".
- **Sparse companies.** When nothing was verified beyond the official registers (no website, linked profile,
  dated activity or job posting), `sparse` is true. The summary then opens with "Public information found was
  limited to official registry records: …". When registry identity itself is unresolved, the overview says
  so and no facts are reported.
- **Deterministic.** The summary has no timestamps and uses stable ordering. The same claims always give
  byte-identical output.
- **Never fatal.** If the summary fails, the error is recorded as `summary_failed` and the row still gets
  its terminal envelope.

Tests: `tests/test_synthesis.py` and `tests/test_c300.py` (`SynthesisRegression`). The tests cover:

- a null employee count versus zero;
- FY2024 versus FY2025 figures;
- most-recent-period selection;
- contradictory trend evidence;
- incomparable periods and unsupported conclusions;
- a missing previous snapshot.

They also summarise 200 measured live envelopes and check every statement against its cited claims.
