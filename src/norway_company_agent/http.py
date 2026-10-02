from __future__ import annotations

import json
import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class FetchResult:
    url: str
    status: int
    elapsed_ms: int
    bytes_received: int
    body: Any = None
    error: str | None = None
    content_sha256: str | None = None
    retrieved_at: str | None = None
    effective_at: str | None = None
    attempts: int = 1
    raw: bytes | None = field(default=None, repr=False, compare=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_json(url: str, *, timeout: float = 20.0, attempts: int = 3) -> FetchResult:
    last_error = "request failed"
    for attempt in range(attempts):
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                elapsed = int((time.monotonic() - started) * 1000)
                return FetchResult(url, response.status, elapsed, len(raw), json.loads(raw), content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now(), attempts=attempt + 1, raw=raw)
        except urllib.error.HTTPError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            raw = exc.read()
            if exc.code in {404, 410}:
                return FetchResult(url, exc.code, elapsed, len(raw), error=f"HTTP {exc.code}", content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now(), attempts=attempt + 1, raw=raw)
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            time.sleep(0.4 * (2**attempt))
    return FetchResult(url, 0, 0, 0, error=last_error, retrieved_at=_utc_now(), attempts=attempts)


@dataclass
class ByteFetch:
    url: str
    status: int
    elapsed_ms: int
    raw: bytes | None
    content_type: str
    headers: dict[str, str]
    content_sha256: str | None
    retrieved_at: str
    attempts: int
    error: str | None = None

    def json(self) -> Any:
        return json.loads(self.raw) if self.raw else None


def fetch_bytes(url: str, *, headers: dict[str, str] | None = None, timeout: float = 30.0, attempts: int = 3, max_bytes: int = 30_000_000) -> ByteFetch:
    """Raw GET with retries on transport errors and 5xx/429; 4xx is returned as-is (it is an answer)."""
    last_error = "request failed"
    for attempt in range(attempts):
        started = time.monotonic()
        request = urllib.request.Request(url, headers={"User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    return ByteFetch(url, response.status, int((time.monotonic() - started) * 1000), None, "", {}, None, _utc_now(), attempt + 1, error="response exceeds byte limit")
                return ByteFetch(url, response.status, int((time.monotonic() - started) * 1000), raw, response.headers.get("content-type", ""), dict(response.headers.items()), hashlib.sha256(raw).hexdigest(), _utc_now(), attempt + 1)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            if exc.code < 500 and exc.code != 429:
                return ByteFetch(url, exc.code, int((time.monotonic() - started) * 1000), raw, exc.headers.get("content-type", "") if exc.headers else "", dict(exc.headers.items()) if exc.headers else {}, hashlib.sha256(raw).hexdigest(), _utc_now(), attempt + 1, error=f"HTTP {exc.code}")
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            time.sleep(0.5 * (2**attempt))
    return ByteFetch(url, 0, 0, None, "", {}, None, _utc_now(), attempts, error=last_error)
