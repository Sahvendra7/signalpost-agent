"""Personal-data minimisation for official source responses.

Brreg's roles endpoint (`/enheter/{org}/roller`) returns each person's birth date (`fodselsdato`) and a
deceased flag (`erDoed`). Neither is needed for any claim, so both are removed from the response before it
is hashed, snapshotted, parsed or persisted anywhere. The evidence hash then covers the redacted canonical
JSON (sorted keys, compact UTF-8) that the snapshot store holds, so every hash stays verifiable offline; the
original bytes are not reproducible from the snapshot (re-query the registry for them). Trade-off: privacy
over byte-exact capture of the original response.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any, Callable

REDACTED_PERSON_KEYS = frozenset({"fodselsdato", "erDoed"})
ROLES_PATH_FRAGMENT = "/roller"


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip(item) for key, item in value.items() if key not in REDACTED_PERSON_KEYS}
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def redact_roles_body(body: Any) -> Any:
    return _strip(body)


def redacting_fetcher(fetcher: Callable[[str], Any]) -> Callable[[str], Any]:
    """Wrap a JSON fetcher (FetchResult) so roles responses never carry birth dates past this point."""

    def fetch(url: str) -> Any:
        result = fetcher(url)
        if ROLES_PATH_FRAGMENT not in url or result.body is None:
            return result
        body = redact_roles_body(result.body)
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return dataclasses.replace(result, body=body, raw=raw, content_sha256=hashlib.sha256(raw).hexdigest())  # bytes_received stays the transfer size

    fetch.live = getattr(fetcher, "live", _is_live(fetcher))  # type: ignore[attr-defined]
    return fetch


def _is_live(fetcher: Callable[[str], Any]) -> bool:
    from .http import fetch_json

    return fetcher is fetch_json
