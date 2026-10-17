# Input formats and the registry snapshot

## Input (`--organisations`)

Reader: `src/norway_company_agent/inputs.py`. **Every input row becomes exactly one terminal envelope**, in
input order. A bad row gets a `failed` envelope with an input error and never stops the batch. Each
envelope keeps the original row as `input_record` (rows over 4,000 characters are cut, marked
`truncated`), plus `input_position` and `input_organisation_number`.

| Format | Detection |
| --- | --- |
| JSONL: objects, strings or numbers, one per line | `.jsonl` / `.ndjson`, or a line starting with `{` or `"` |
| JSON array, or `{"organisation_numbers": [...]}` | `.json`. A file that does not parse is read line by line instead of aborting. |
| CSV / semicolon / TSV / pipe with a header row | The first non-blank line names an accepted identifier column, whatever the file extension |
| Plain text, one number per line | Anything else |
| Gzip of any of these | A `.gz` suffix |

- **Identifier keys or columns.** These are accepted, case-insensitively: `organisation_number`,
  `organization_number`, `organisasjonsnummer`, `orgnr`, `org_no`, `organisationNumber`,
  `organizationNumber`. No other column is treated as an identifier. A CSV without one of these headers is
  read as plain lines, so a multi-column line is invalid, not guessed.
- **Values.** A value must be exactly nine digits, or 3-3-3 groups separated by one kind of separator
  (space, dot, dash or no-break space). JSON integers are accepted. Free text with digits in it
  (`"org 923609016 in prose"`, `NO923609016MVA`) is not mined for digits.
- **Errors.** Each of these is a terminal `failed` envelope:

  | Code | Cause |
  | --- | --- |
  | `invalid_organisation_number` | The value is not nine digits, or not 3-3-3 groups. |
  | `missing_organisation_number` | An object or CSV row has no accepted key. |
  | `conflicting_identifiers` | Two accepted keys hold different values. Equal values in different spellings, or one blank, are not a conflict. |
  | `malformed_input_row` | A JSON line does not parse, or a line is a JSON array. |

- **Warnings.** These rows are still researched:
  - `checksum_mismatch`: the number fails the mod-11 check. The row is researched anyway, because the
    registry decides.
  - `duplicate_input`: the number repeats an earlier row. It is researched once, and every row gets its
    own envelope.

The new reader gives byte-identical results to the previous reader on the 100-row sample, the 1,200-row
audit input and the 411,160-row universe file.

## Registry snapshot (`--bulk`, optional)

Brreg's download `https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv` is served as gzip
(`content-type: application/vnd.brreg.enhetsregisteret.enhet.v2+gzip`; the first bytes, `1f 8b`, were
checked on 2026-10-03). The command never requires this file.

| Situation | `report.registry.snapshot_status` | Behaviour |
| --- | --- | --- |
| No `--bulk` | `absent` | Identity comes from the live registry. |
| Gzip CSV that reads to the end | `used` | Bulk rows are used and the live registry is still queried. The snapshot SHA-256 is recorded. |
| Missing file, not gzip, corrupt or truncated gzip, unreadable CSV | `invalid`, with `reason` | Nothing from the file is used. Every company falls back to the live registry. A warning goes to stderr, and each envelope's `registry` module note names the reason. The batch never aborts. |

Tests: `tests/test_input_robustness.py`.
