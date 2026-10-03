"""Batch input reader: every input row becomes exactly one InputRow, valid or not. Never aborts.

Accepted formats: JSONL (objects, strings or numbers), a JSON array (or {"organisation_numbers": [...]}),
plain text (one number per line) and CSV/TSV/semicolon files with a header row. Gzip is accepted for all.

Identifier columns/keys accepted (case-insensitive): organisation_number, organization_number,
organisasjonsnummer, orgnr, org_no, organisationNumber, organizationNumber. No other column is
reinterpreted as an identifier. A row naming two different identifiers is never guessed: it gets a
`conflicting_identifiers` error. A value must be exactly nine digits, optionally grouped as 3-3-3 with
spaces, dots or dashes; anything else is `invalid_organisation_number` (no digit scavenging from free text).
The original row is preserved as `record`.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ORG_WEIGHTS = (3, 2, 7, 6, 5, 4, 3, 2)
IDENTIFIER_KEYS = ("organisation_number", "organization_number", "organisasjonsnummer", "orgnr", "org_no", "organisationNumber", "organizationNumber")
_IDENTIFIER_LOOKUP = {key.lower() for key in IDENTIFIER_KEYS}
_ORG_PATTERN = re.compile(r"^\d{9}$|^\d{3}([ .\- ])\d{3}\1\d{3}$")
ANNOTATION_KEYS = ("evaluation_split", "sample_slice")
RECORD_LIMIT = 4000
CSV_DELIMITERS = (",", ";", "\t", "|")


@dataclass
class InputRow:
    position: int
    raw: Any
    organisation_number: str | None
    errors: list[dict[str, Any]] = field(default_factory=list)
    annotations: dict[str, Any] = field(default_factory=dict)
    record: Any = None


def mod11_valid(org: str) -> bool:
    if len(org) != 9 or not org.isdigit():
        return False
    remainder = sum(int(digit) * weight for digit, weight in zip(org[:8], ORG_WEIGHTS)) % 11
    check = 0 if remainder == 0 else 11 - remainder
    return check != 10 and check == int(org[8])


def normalise_organisation_number(value: Any) -> str | None:
    """Nine digits, or None. Accepts ints and 3-3-3 groupings; never extracts digits from other text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _ORG_PATTERN.match(text):
        return None
    return re.sub(r"\D", "", text)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _identifier_fields(record: dict[str, Any]) -> list[tuple[str, Any]]:
    return [(key, value) for key, value in record.items() if isinstance(key, str) and key.strip().lower() in _IDENTIFIER_LOOKUP and not _is_blank(value)]


def _bounded(record: Any) -> Any:
    text = json.dumps(record, ensure_ascii=False, default=str)
    return record if len(text) <= RECORD_LIMIT else {"truncated": True, "text": text[:RECORD_LIMIT]}


def _row_from_value(position: int, value: Any, record: Any, parse_error: str | None = None) -> InputRow:
    if parse_error:
        row = InputRow(position, None, None, record=_bounded(record))
        row.errors.append({"code": "malformed_input_row", "stage": "input", "message": parse_error})
        return row
    if isinstance(value, dict):
        identifiers = _identifier_fields(value)
        row = InputRow(position, None, None, record=_bounded(record))
        row.annotations = {key: value[key] for key in ANNOTATION_KEYS if value.get(key) is not None}
        if not identifiers:
            row.errors.append({"code": "missing_organisation_number", "stage": "input", "message": f"No organisation-number field (accepted: {', '.join(IDENTIFIER_KEYS)})"})
            return row
        normalised = {key: normalise_organisation_number(item) for key, item in identifiers}
        distinct = {normalised[key] if normalised[key] is not None else f"invalid:{str(item).strip()}" for key, item in identifiers}
        if len(distinct) > 1:
            row.errors.append({"code": "conflicting_identifiers", "stage": "input", "message": "Row names different organisation numbers; not guessed: " + "; ".join(f"{key}={str(item)[:20]!r}" for key, item in identifiers)})
            return row
        key, item = identifiers[0]
        row.raw = item
        row.organisation_number = normalised[key]
    else:
        row = InputRow(position, value, normalise_organisation_number(value), record=_bounded(record))
    if row.organisation_number is None:
        row.errors.append({"code": "invalid_organisation_number", "stage": "input", "message": f"Input is not a 9-digit organisation number: {str(row.raw)[:40]!r}"})
    return row


def _csv_dialect(first_line: str) -> str | None:
    """The delimiter of a header line that names an accepted identifier column, else None."""
    for delimiter in CSV_DELIMITERS:
        if delimiter in first_line:
            cells = next(csv.reader([first_line], delimiter=delimiter))
            if any(cell.strip().lstrip("﻿").lower() in _IDENTIFIER_LOOKUP for cell in cells):
                return delimiter
    return None


def _csv_entries(text: str, delimiter: str) -> list[tuple[Any, Any, str | None]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header: list[str] | None = None
    entries = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        if header is None:
            header = [cell.strip().lstrip("﻿") for cell in cells]
            continue
        record = {name: cells[index] if index < len(cells) else None for index, name in enumerate(header)}
        if len(cells) > len(header):
            record["_extra_fields"] = cells[len(header):]
        entries.append((record, record, None))
    return entries


def _line_entries(text: str, as_json: bool) -> list[tuple[Any, Any, str | None]]:
    entries = []
    for line in text.splitlines():
        if not line.strip():
            continue
        stripped = line.strip()
        if as_json or stripped.startswith(("{", "[", '"')):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                if stripped.startswith(("{", "[", '"')):
                    entries.append((None, stripped, f"Malformed JSON line: {exc.msg} at column {exc.colno}"))
                    continue
                value = stripped  # a bare value in a .jsonl file, e.g. 923 609 016
            if isinstance(value, list):
                entries.append((None, stripped, "A JSON array is not one input row"))
                continue
            entries.append((value, value, None))
        else:
            entries.append((stripped, stripped, None))
    return entries


def read_input_rows(path: str | Path) -> list[InputRow]:
    """Tolerant reader: every non-blank input line (or JSON array element, or CSV record) is one row."""
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    kind = (Path(source.stem).suffix if source.suffix == ".gz" else source.suffix).lower()
    entries: list[tuple[Any, Any, str | None]] | None = None
    if kind == ".json":
        try:
            body = json.loads(text)
            values = body if isinstance(body, list) else body.get("organisation_numbers", []) if isinstance(body, dict) else [body]
            entries = [(value, value, None) for value in values]
        except (json.JSONDecodeError, AttributeError):
            entries = None  # fall back to line-by-line so one bad byte cannot abort the batch
    if entries is None:
        first = next((line for line in text.splitlines() if line.strip()), "")
        delimiter = _csv_dialect(first) if not first.lstrip().startswith(("{", "[")) else None
        if delimiter is not None:
            entries = _csv_entries(text, delimiter)
        else:
            entries = _line_entries(text, as_json=kind in {".jsonl", ".ndjson", ".json"})
    rows: list[InputRow] = []
    first_seen: dict[str, int] = {}
    for position, (value, record, error) in enumerate(entries):
        row = _row_from_value(position, value, record, error)
        if row.organisation_number is not None:
            if not mod11_valid(row.organisation_number):
                row.errors.append({"code": "checksum_mismatch", "stage": "input", "message": "Organisation number fails the mod-11 check; researched anyway"})
            if row.organisation_number in first_seen:
                row.errors.append({"code": "duplicate_input", "stage": "input", "message": f"Same organisation number as input row {first_seen[row.organisation_number]}; researched once"})
            else:
                first_seen[row.organisation_number] = position
        rows.append(row)
    return rows
