# Deterministic company summary

Every envelope carries `company_summary`, built by `src/norway_company_agent/synthesis.py` from that
envelope's own claims. No LLM is used (`llm_used: false`); the optional LLM layer stays off.

## Shape

```json
{
  "method": "deterministic_template_v1", "language": "en", "llm_used": false,
  "sparse": true, "overview": "Public information found was limited to official registry records: …",
  "sections": [{"id": "leadership", "title": "Leadership",
                "statements": [{"text": "Chief executive (daglig leder): Kari Nordmann.",
                                "claim_keys": ["…"], "evidence_ids": ["ev_…"]}]}],
  "text": "plain-text rendering of the same statements"
}
```

The sections, always in this order, are:

1. What the company does
2. Key company facts
3. Leadership
4. Locations
5. Financial snapshot
6. Website and public footprint
7. What changed
8. What remains unknown

## Rules

- **Facts come only from available claims.** Each statement is a fixed template filled with claim values,
  and lists the `claim_keys` and `evidence_ids` it rests on. That gives the FACT → SOURCE → DATE chain.
- **Source text is quoted verbatim.** Registered activity, statutory purpose and the website description
  are not translated or paraphrased. Text longer than 400 characters is cut and ends with `…`.
- **Reporting periods are preserved.** The financial snapshot shows the latest reporting period for each
  account type (company or group accounts), with its exact from–to dates and currency. It also says how
  many earlier periods exist. The latest registered accounts year is a separate statement, because it can
  differ from the latest period that has figures.
- **Unknown is not the same as absent.**
  - `not_available` means "Checked; nothing found".
  - `failed`/`blocked` means "Could not be checked in this run".
  - `ambiguous` means "Candidates were found but not confirmed as this company".
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

Tests: `tests/test_synthesis.py`. They also run the summary over 200 of the measured live envelopes.
