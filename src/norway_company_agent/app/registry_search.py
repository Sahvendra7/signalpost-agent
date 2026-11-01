"""Find companies that are not yet in the dataset (V3 design §B11).

Either the optional bulk registry file (`--bulk`, read once into a compact in-memory list) or one fixed public
endpoint of the Brønnøysund Register Centre — never a URL taken from the request. At most 20 results; answers are
cached for ten minutes.
"""
from __future__ import annotations

import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from ..http import FetchResult, fetch_json
from ..sampling import iter_bulk
from .store import MAX_RESULTS, _words

ENDPOINT = "https://data.brreg.no/enhetsregisteret/api/enheter"
CACHE_SECONDS = 600
CACHE_ENTRIES = 256


def _from_api(item: dict[str, Any]) -> dict[str, Any]:
    address = item.get("forretningsadresse") or item.get("postadresse") or {}
    return {
        "org": str(item.get("organisasjonsnummer") or ""), "name": item.get("navn") or "",
        "form": (item.get("organisasjonsform") or {}).get("kode"), "municipality": address.get("kommune"),
        "deleted": bool(item.get("slettedato")), "bankrupt": bool(item.get("konkurs")), "liquidating": bool(item.get("underAvvikling")),
    }


class RegistrySearch:
    def __init__(self, fetcher: Callable[[str], FetchResult] = fetch_json, bulk: str | Path | None = None, clock=time.monotonic):
        self.fetcher, self.bulk, self.clock = fetcher, bulk, clock
        self._cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        self._rows: list[tuple[str, str, str, str]] | None = None  # (org, name, folded words, form)
        self._lock = threading.Lock()

    def _bulk_rows(self) -> list[tuple[str, str, str, str]]:
        with self._lock:
            if self._rows is None:
                self._rows = [(row["organisation_number"], row["name"], " ".join(_words(row["name"])), row["legal_form"]) for row in iter_bulk(self.bulk)]
            return self._rows

    def search(self, kind: str, query: str) -> dict[str, Any]:
        key = (kind, query.casefold())
        cached = self._cache.get(key)
        if cached and self.clock() - cached[0] < CACHE_SECONDS:
            return cached[1]
        answer = self._bulk(kind, query) if self.bulk else self._api(kind, query)
        if answer.get("error") is None:
            if len(self._cache) >= CACHE_ENTRIES:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (self.clock(), answer)
        return answer

    def _bulk(self, kind: str, query: str) -> dict[str, Any]:
        rows = self._bulk_rows()
        if kind == "number":
            found = [row for row in rows if row[0] == query]
        else:
            wanted = _words(query)
            found = [row for row in rows if all(any(word.startswith(term) for word in row[2].split()) for term in wanted)]
            found.sort(key=lambda row: (row[2] != " ".join(wanted), len(row[2]), row[1]))
        return {"source": "bulk_file", "error": None,
                "results": [{"org": org, "name": name, "form": form, "municipality": None, "deleted": False} for org, name, _, form in found[:MAX_RESULTS]]}

    def _api(self, kind: str, query: str) -> dict[str, Any]:
        parameter = {"organisasjonsnummer": query} if kind == "number" else {"navn": query}
        url = ENDPOINT + "?" + urllib.parse.urlencode({**parameter, "size": MAX_RESULTS})
        try:
            result = self.fetcher(url)
        except Exception:  # noqa: BLE001 — the registry being down is an answer, not a crash
            return {"source": "registry_api", "error": "registry_unreachable", "results": []}
        if result.status != 200 or not isinstance(result.body, dict):
            return {"source": "registry_api", "error": "registry_unreachable", "results": []}
        items = ((result.body.get("_embedded") or {}).get("enheter")) or []
        return {"source": "registry_api", "error": None, "retrieved_at": result.retrieved_at,
                "results": [_from_api(item) for item in items[:MAX_RESULTS] if isinstance(item, dict)]}
