# Identity block and company status

Each envelope starts with `organisation_number`, `identity` and `company_status`. Per-source module states stay
under `modules`. Code: `src/norway_company_agent/status.py`. Both fields are derived deterministically from
the envelope's own claims, errors and module states. No LLM touches them.

`identity` holds:

- `organisation_number`: `null` unless anchored.
- `input_organisation_number`.
- `anchored`: true only when the registry returned a record for exactly this organisation number. A record
  for any other number is discarded upstream.
- `method`.
- `legal_name` and `legal_form`.
- `registry_status`: `registered`, `bankrupt`, `under_liquidation` or `unknown`.
- `source_class`, `source_url`, `retrieved_at`, `content_sha256` and `evidence_id` of the anchoring registry
  record.
- `carried_forward`: true when the registry was down in this run and the identity is the last verified one.

`company_status.state` takes one of five values:

| State | Meaning |
| --- | --- |
| `complete` | Identity anchored. Every source answered (`complete`, `not_found` or `not_applicable`). |
| `partial` | Identity anchored. At least one source failed, was blocked, was carried forward or was cut by the deadline. `reasons` lists which. |
| `not_researched` | The batch deadline or an interruption stopped the run before this company's registry record was fetched (`deadline_exceeded` / `interrupted`). |
| `identity_unresolved` | The registry returned no record for this organisation number. |
| `invalid_input` | The row has no usable organisation number (`invalid_organisation_number`, `missing_organisation_number`, `conflicting_identifiers` or `malformed_input_row`). |

The contract's `run.terminal_status` (`completed` or `failed`) is unchanged.

Tests: `tests/test_identity_status.py`.
