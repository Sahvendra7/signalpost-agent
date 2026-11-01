"""Input validation and request checks for the local search application (V3 design §B12).

Every value that comes from a request is validated here before it reaches the store, the registry or the research
pipeline. Inputs are company names and organisation numbers only: anything that looks like a web address is
rejected, so the app can never be used to fetch an arbitrary URL.
"""
from __future__ import annotations

import hmac
import re
import threading
import time
from typing import Mapping

from ..inputs import mod11_valid

ORG = re.compile(r"^\d{9}$")
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEME = re.compile(r"\b(?:https?|ftp|file|data|javascript|mailto|www)[:.]", re.I)
TLDS = "no|com|net|org|io|se|dk|fi|is|eu|info|biz|co|uk|de|nl|fr|app|dev|xyz|online|site|shop|cloud|ai|me|tv"
DOMAIN_LIKE = re.compile(rf"[a-z0-9\-]{{2,}}\.(?:{TLDS})(?![a-z0-9])", re.I)
MAX_QUERY = 100
MAX_BODY = 4096
URL_MESSAGE = "Search by company name or organisation number"


class HttpError(Exception):
    """An expected refusal: an HTTP status, a stable code and a short message (never a traceback)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def valid_org(value: str | None) -> str:
    value = str(value or "")
    if not ORG.fullmatch(value):
        raise HttpError(400, "invalid_organisation_number", "An organisation number has 9 digits")
    if not mod11_valid(value):
        raise HttpError(400, "invalid_organisation_number", "Not a valid Norwegian organisation number (check digit)")
    return value


def valid_job_id(value: str | None) -> str:
    if not JOB_ID.fullmatch(str(value or "")):
        raise HttpError(400, "invalid_job_id", "Unknown research job")
    return str(value)


def valid_sha(value: str | None) -> str:
    if not SHA256.fullmatch(str(value or "")):
        raise HttpError(400, "invalid_hash", "Not a content hash")
    return str(value)


def classify_query(raw: str | None) -> tuple[str, str]:
    """('number', org) or ('name', text). Raises HttpError(400) for empty, too long or URL-like input."""
    query = " ".join(str(raw or "").split())
    if not query:
        raise HttpError(400, "empty_query", "Type a company name or organisation number")
    if len(query) > MAX_QUERY:
        raise HttpError(400, "query_too_long", f"Use at most {MAX_QUERY} characters")
    compact = query.replace(" ", "")
    if compact.isdigit():
        return "number", valid_org(compact)
    probe = re.sub(r"\ba/s\b", "", query, flags=re.I)  # "A/S" is a legal-form spelling, not a path
    if "/" in probe or "\\" in probe or "@" in probe or SCHEME.search(probe) or "://" in probe or DOMAIN_LIKE.search(probe):
        raise HttpError(400, "url_not_allowed", URL_MESSAGE)
    if any(ord(ch) < 32 for ch in query):
        raise HttpError(400, "invalid_query", URL_MESSAGE)
    return "name", query


def check_host(host: str | None, port: int, extra: tuple[str, ...] = ()) -> None:
    """DNS-rebinding defence: only the loopback names this server was started on (and an explicit --host) are accepted."""
    if str(host or "").lower() not in {f"127.0.0.1:{port}", f"localhost:{port}", *(f"{name.lower()}:{port}" for name in extra)}:
        raise HttpError(421, "wrong_host", "This server only answers on 127.0.0.1 or localhost")


def check_post(headers: Mapping[str, str], token: str, origins: set[str]) -> None:
    """CSRF defence for state-changing requests: per-process token, same Origin, same-site fetch metadata, JSON."""
    supplied = headers.get("X-Signalpost-Token") or ""
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HttpError(403, "bad_token", "Reload the search page and try again")
    if (headers.get("Origin") or "") not in origins:
        raise HttpError(403, "cross_origin", "Requests must come from the search page")
    if (headers.get("Sec-Fetch-Site") or "same-origin") != "same-origin":
        raise HttpError(403, "cross_site", "Requests must come from the search page")
    if not (headers.get("Content-Type") or "").lower().startswith("application/json"):
        raise HttpError(415, "json_required", "Send JSON")


class RateLimiter:
    """A token bucket: `rate` requests per `per` seconds, refilled continuously. One bucket per key."""

    def __init__(self, rate: int, per: float = 60.0, clock=time.monotonic):
        self.rate, self.per, self.clock = float(rate), float(per), clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str = "local") -> bool:
        with self._lock:
            now = self.clock()
            tokens, last = self._buckets.get(key, (self.rate, now))
            tokens = min(self.rate, tokens + (now - last) * self.rate / self.per)
            allowed = tokens >= 1
            self._buckets[key] = (tokens - 1 if allowed else tokens, now)
            return allowed

    def check(self, key: str = "local") -> None:
        if not self.allow(key):
            raise HttpError(429, "rate_limited", "Too many requests; wait a minute and try again")
