"""Check every company_summary statement against the claims it cites (used by tests and measurement scripts).

A statement is supported when every date, every NOK amount and every organisation number in its text occurs in a
claim it cites (value, reporting period, event date or recorded reason), every cited claim and evidence id exists in
the envelope, and its evidence ids are exactly the evidence of its cited claims. No trend or growth wording is
allowed: changes are stated metric by metric against one cited earlier value."""
from __future__ import annotations

import json
import re
from typing import Any

TREND_WORDS = re.compile(r"\b(?:growth|growing|grew|grow|trend|trending|steadily|consistently|declining|decline|improv\w*|deteriorat\w*|surg\w*|plung\w*)\b", re.I)
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
AMOUNT = re.compile(r"NOK (-?[\d,]+(?:\.\d+)?)")
ORG = re.compile(r"\b\d{9}\b")


def _numbers(value: Any) -> set[str]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    found = set()
    for raw in re.findall(r"-?\d+(?:\.\d+)?", text):
        number = float(raw)
        found.add(f"{number:,.0f}" if number == int(number) else f"{number:,.2f}")
    return found


def unsupported_statements(envelope: dict[str, Any]) -> list[str]:
    claims = {claim["key"]: claim for claim in envelope.get("claims") or []}
    evidence = {item["id"] for item in envelope.get("evidence") or []}
    problems = []
    for section in (envelope.get("company_summary") or {}).get("sections") or []:
        for statement in section["statements"]:
            text = statement["text"]
            where = f"{envelope.get('organisation_number')} {section['id']}: {text[:120]}"
            missing = [key for key in statement["claim_keys"] if key not in claims]
            if missing or not set(statement["evidence_ids"]) <= evidence:
                problems.append(f"{where} -> cites a claim or evidence id that is not in the envelope")
                continue
            cited = [claims[key] for key in statement["claim_keys"]]
            if set(statement["evidence_ids"]) != {eid for claim in cited for eid in claim.get("evidence_ids") or []}:
                problems.append(f"{where} -> evidence ids are not those of the cited claims")
            if TREND_WORDS.search(re.sub(r"“[^”]*”", "", text)):  # verbatim source quotes are the source's words
                problems.append(f"{where} -> trend or growth wording")
            if not cited:
                # A change against a previous run may cite no current claim (a removed fact): its source is the
                # envelope's own change event, which carries the earlier evidence.
                events = json.dumps(envelope.get("changes") or [], ensure_ascii=False, default=str) if section["id"] == "what_changed" else ""
                stated = DATE.findall(text) + AMOUNT.findall(text) + ORG.findall(text)
                if any(value not in events for value in stated):
                    problems.append(f"{where} -> states a date, amount or organisation number without citing a claim")
                continue
            source = json.dumps(cited, ensure_ascii=False, default=str) + str(envelope.get("organisation_number"))
            amounts = _numbers([claim.get("value") for claim in cited])
            for day in DATE.findall(text):
                if day not in source:
                    problems.append(f"{where} -> date {day} is not in a cited claim")
            for amount in AMOUNT.findall(text):
                if amount not in amounts:
                    problems.append(f"{where} -> amount NOK {amount} is not a cited claim value")
            for number in ORG.findall(text):
                if number not in source:
                    problems.append(f"{where} -> organisation number {number} is not in a cited claim")
    return problems
