# Refresh semantics

Run the batch with `--previous-profiles <profiles.jsonl from an earlier run>` to refresh. The comparison
is per company, matched by exact organisation number. Code: `src/norway_company_agent/refresh.py`
(`carry_forward`, `claim_changes`), called from `pipeline._envelope_for_row`.

## Rule: a source outage is not a company change

A module (`registry_live`, `financials`, `roles`, `group`, `locations`, `website`, `site_research`) whose
previous record was `available` and whose current attempt is an outage (`source_error`, `blocked`,
`not_fetched`, or missing) keeps its previous record:

- the record is copied unchanged, with `carried_forward: true`, `carried_at` and
  `current_attempt {status, note, retrieved_at}` added;
- every claim from it keeps the **original** evidence (source URL, retrieval time and SHA-256), and is
  marked `carried_forward: true` and `last_verified_at`;
- the module state in `modules` becomes `carried_forward`, and an error
  `source_unavailable_value_retained` names the stage;
- one `unavailable` change event is emitted per module, listing `fields_retained`.

Nothing is deleted, set to null, reported as changed or replaced because a source failed. A source that
stays down over several runs keeps the original retrieval date, so the age of the value stays visible.

A source that **answers** is not an outage. A registry or accounts `404` (`not_found`) is the source
saying the record is gone, so the facts are `removed`.

Company website (site research): when the run cannot re-check the previously verified site (transport
failure, robots, budget), the site facts are carried. When the run reaches the same domain and the site
identity policy now classifies it as non-publishable (`AMBIGUOUS`, `THIRD_PARTY`, `FAN_COMMUNITY`,
`DIRECTORY`), the facts are **not** carried, because re-publishing them could attach the wrong company.
They become `unverified` events instead. The same applies to the registry-linked website (v1) when its
identity gate no longer passes.

## Change events

Each envelope's `changes` list holds typed, claim-level events:

| `change_type` | Meaning |
| --- | --- |
| `added` | The source answered in both runs and the fact is new. |
| `removed` | The source answered in both runs and the fact is no longer there. |
| `changed` | The same single-valued fact (same category, field, period, account type and currency) has a different value. |
| `unverified` | A previously verified website fact can no longer be confirmed under the identity policy. |
| `unavailable` | The source failed in this run; its last supported values are retained (see above). |

`unchanged` facts are counted, not listed. Each event carries `previous_evidence` and `evidence`
(source URL, retrieval time, SHA-256, evidence id), `materiality` (`informational` for activity items and
counts, `material` otherwise) and any reporting-period qualifiers. Multi-valued fields (subunits, role
holders, social profiles, activity items, job postings) are compared by value, so a reordered list is
never a change. The envelope's `refresh` block summarises the counts, `carried_forward_modules` and
`unverified_modules`, or says `compared: false` when no previous profile was supplied for the company.

## Idempotency

Re-running against the same source data yields an empty `changes` list. Tested in
`tests/test_refresh_semantics.py`: RUN1 value A → RUN2 outage keeps A (carried, original evidence) →
RUN3 value B gives one `changed` A→B → RUN4 with B again gives no events.
