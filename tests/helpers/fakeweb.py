"""Offline fake Brreg + company web for pipeline and CLI tests (optionally slow, to exercise deadlines)."""
from __future__ import annotations

import hashlib
import json
import time

from norway_company_agent.http import ByteFetch, FetchResult
from norway_company_agent.pipeline import mod11_valid

NOW = "2026-10-03T12:00:00Z"


def valid_orgs(count: int, start: int = 910000000) -> list[str]:
    orgs, number = [], start
    while len(orgs) < count:
        if mod11_valid(str(number)):
            orgs.append(str(number))
        number += 1
    return orgs


def entity(org: str, name: str | None = None, employees: int | None = 3) -> dict:
    body = {
        "organisasjonsnummer": org, "navn": name or f"Testselskap {org} AS", "organisasjonsform": {"kode": "AS"},
        "naeringskode1": {"kode": "62.010", "beskrivelse": "Programmeringstjenester"},
        "forretningsadresse": {"adresse": ["Storgata 1"], "postnummer": "0155", "poststed": "OSLO", "kommune": "OSLO", "land": "Norge"},
        "konkurs": False, "underAvvikling": False, "sisteInnsendteAarsregnskap": "2025", "aktivitet": ["Utvikling av programvare"],
        "stiftelsesdato": "2015-03-01",
    }
    if employees is not None:
        body["antallAnsatte"] = employees
        body["harRegistrertAntallAnsatte"] = True
    return body


ROLES = {"rollegrupper": [{"type": {"kode": "DAGL"}, "sistEndret": "2024-05-01", "roller": [
    {"type": {"kode": "DAGL", "beskrivelse": "Daglig leder"}, "person": {"navn": {"fornavn": "Kari", "etternavn": "Nordmann"}, "fodselsdato": "1980-01-02"}, "avregistrert": False}]}]}
ACCOUNTS = [{"id": 7, "regnskapstype": "SELSKAP", "valuta": "NOK", "regnskapsperiode": {"fraDato": "2025-01-01", "tilDato": "2025-12-31"},
             "resultatregnskapResultat": {"driftsresultat": {"driftsinntekter": {"sumDriftsinntekter": 1000}, "driftsresultat": 100}, "aarsresultat": 80},
             "eiendeler": {"sumEiendeler": 5000}, "egenkapitalGjeld": {"egenkapital": {"sumEgenkapital": 3000}, "gjeldOversikt": {"sumGjeld": 2000}}}]


def json_result(url: str, status: int, body=None) -> FetchResult:
    raw = json.dumps(body, sort_keys=True).encode() if body is not None else b""
    return FetchResult(url, status, 5, len(raw), body if status == 200 else None, error=None if status == 200 else f"HTTP {status}",
                       content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=NOW, raw=raw)


class FakeBrreg:
    """`delay` seconds per call; `overrides[(org, fragment)] = (status, body)` or an exception; `down` = set of fragments failing with 0."""

    def __init__(self, entities: dict[str, dict], delay: float = 0.0, overrides: dict | None = None, down: set[str] | None = None, slow_orgs: dict[str, float] | None = None):
        self.entities, self.delay, self.overrides, self.down, self.slow_orgs = entities, delay, overrides or {}, down or set(), slow_orgs or {}
        self.calls: list[str] = []

    def __call__(self, url: str) -> FetchResult:
        self.calls.append(url)
        org = next((org for org in self.entities if org in url), None)
        time.sleep(self.slow_orgs.get(org, self.delay))
        if any(fragment in url for fragment in self.down):
            return FetchResult(url, 0, 0, 0, error="URLError", retrieved_at=NOW, attempts=1)
        for (match_org, fragment), outcome in self.overrides.items():
            if match_org == org and fragment in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return json_result(url, *outcome)
        if org is None:
            return json_result(url, 404)
        if "/roller" in url:
            return json_result(url, 200, ROLES)
        if "konsernstruktur" in url:
            return json_result(url, 404)
        if "underenheter" in url:
            return json_result(url, 200, {"_embedded": {"underenheter": [{"organisasjonsnummer": "973000001", "navn": "Avdeling Bergen", "beliggenhetsadresse": {"adresse": ["Bryggen 2"], "postnummer": "5003", "poststed": "BERGEN"}}]}})
        if "regnskapsregisteret" in url:
            return json_result(url, 200, ACCOUNTS)
        if "/enheter/" in url:
            return json_result(url, 200, self.entities[org])
        return json_result(url, 404)


def offline_site(url, **kwargs):
    return ByteFetch(url, 404, 0, b"", "text/html", {}, None, NOW, 1, "HTTP 404")


def no_website(url):
    from norway_company_agent.evidence import evidence

    return evidence("website", "not_found", "registry_linked_company_website", "https://data.brreg.no/enhetsregisteret/api/enheter", note="No valid registry website URL", retrieved_at=NOW), {"requests": 0, "bytes": 0, "latencies_ms": []}


def injected(brreg: FakeBrreg) -> dict:
    return {"fetcher": brreg, "website_fetcher": no_website, "site_fetcher": offline_site, "resolver": lambda host: False}
