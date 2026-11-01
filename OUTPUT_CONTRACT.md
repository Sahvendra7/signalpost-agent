# Minimal output contract

Emit one JSON object per input organisation number.

```json
{
  "organisation_number": "123456789",
  "run": {
    "run_id": "2026-08-24-a",
    "started_at": "2026-08-24T06:00:00Z",
    "completed_at": "2026-08-24T06:00:08Z",
    "terminal_status": "completed"
  },
  "claims": [
    {
      "field": "official_website",
      "value": "https://example.no/",
      "availability": "available",
      "confidence": 0.99,
      "evidence_ids": ["ev-1"]
    }
  ],
  "evidence": [
    {
      "id": "ev-1",
      "source_url": "https://example.no/",
      "source_class": "company_owned",
      "retrieved_at": "2026-08-24T06:00:04Z",
      "content_sha256": "...",
      "claim_span": "Example AS, organisation number 123 456 789"
    }
  ],
  "changes": [],
  "errors": [],
  "operations": {
    "requests": 4,
    "runtime_ms": 8120,
    "third_party_cost_usd": 0
  }
}
```

Allowed availability states are `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous` and `failed`. A checked source that has zero jobs or zero locations is different from a source that was not checked.

## Additive fields (V3)

V3 only adds fields; no existing field changes meaning, except `removed` (below). A consumer that ignores unknown
fields reads V3 envelopes as before. `contract.validate_envelope` checks the two new structured values.

| Where | Field | Meaning |
|---|---|---|
| `run` | `code_version` | `{source_sha256, package_version, git_commit, git_dirty}`: which code produced the envelope. `source_sha256` hashes the runtime source files, so it identifies the code even without git. |
| social, news, job claims | `attribution` | `{code, basis}`: the rule that attributed the item to this company, in plain words. |
| social, news, job claims | `first_seen_at`, `first_seen_run_id` | When this item was first published for this company, carried over from the baseline run. These are set only when known. |
| social, news, job claims | `is_new` | `true` only when a baseline existed and the item was not in it. With no baseline, nothing is new. |
| job claims | `currency` | `{state: open / recently_posted, basis}`: why the advertisement counts as current. The deadline itself is in `value.valid_through`. |
| job claims | `value.hiring_organization` | The employer the advertisement names, when it names one. |
| `official_website` claim | `site_role`, `operated_by` | `operated_by_other_company` (with that company's organisation number) or `group_or_brand_site`. The site's jobs, careers page and social profiles are then held back. |
| `refresh` | `baseline` | `{kind: published_envelope / previous_profiles, run_id, started_at, code_version}`. |
| `refresh` | `counts.retracted`, `new_items` | Per-family counts. |
| `changes[]` | `change_type: retracted` | The previous run published the item, this run still found it, and a rule now withholds it. Carries `rule`, `basis`, `code_version` and `previous_code_version`. It never says the earlier item was verified. |
| `changes[]` | `change_type: not_rechecked` | The page the item came from was not read in this run. Informational; not a removal. |
| `changes[]` | `change_type: removed` | Now strictly: the page was read again and the item is gone. |
| `changes[]` | `change_type: first_observed` | The previous run could not read the company's website, so a site item seen now is a first observation, not necessarily new. Informational. Such items get no `is_new`. |

Held-back items stay visible as non-available claims, for example `ambiguous` or `not_applicable` social profiles,
with a `reason`. They are never published as facts.

The batch report adds `code_version`, `baseline`, `new_items`, `checks` (candidates withheld by rule — automatic
checks, not accuracy), `manual_audit` (`not_audited` unless `--audit-results` is given) and `history`.
