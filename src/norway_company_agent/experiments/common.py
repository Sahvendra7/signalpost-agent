from __future__ import annotations

import time
from collections import Counter
from typing import Any, Callable

from ..http import ByteFetch, fetch_bytes
from ..operations import latency_summary

ByteFetcher = Callable[..., ByteFetch]


def evidence_complete(item: dict[str, Any]) -> bool:
    """Same minimum the contract validator requires of a cited evidence entry, plus a claim span."""
    sha = str(item.get("content_sha256") or "")
    return bool(
        str(item.get("source_url") or "").startswith(("http://", "https://"))
        and len(sha) == 64
        and item.get("retrieved_at")
        and item.get("claim_span")
    )


class Meter:
    """Per-company request/latency accounting for one experiment."""

    def __init__(self, fetcher: ByteFetcher = fetch_bytes):
        self.fetcher = fetcher
        self.requests = 0
        self.statuses: Counter[str] = Counter()
        self.latencies: list[int] = []

    def get(self, url: str, **kwargs: Any) -> ByteFetch:
        result = self.fetcher(url, **kwargs)
        self.requests += result.attempts
        self.latencies.append(result.elapsed_ms)
        self.statuses[str(result.status)] += 1
        return result


def summarize(rows: list[dict[str, Any]], *, covered_key: str, count_key: str | None = None) -> dict[str, Any]:
    n = len(rows) or 1
    covered = sum(1 for row in rows if row.get(covered_key))
    measured = [row for row in rows if not row.get("unmeasured")]
    summary = {
        "companies": len(rows),
        "companies_measured": len(measured),
        "companies_covered": covered,
        "coverage_rate": round(covered / n, 4),
        "requests_total": sum(row.get("requests", 0) for row in rows),
        "requests_per_company": round(sum(row.get("requests", 0) for row in rows) / n, 3),
        "runtime_per_company": latency_summary([row.get("runtime_ms", 0) for row in rows]),
        "evidence_items": sum(row.get("evidence_items", 0) for row in rows),
        "evidence_complete_rate": _rate(sum(row.get("evidence_complete", 0) for row in rows), sum(row.get("evidence_items", 0) for row in rows)),
        "identity_rejections": sum(row.get("identity_rejections", 0) for row in rows),
        "published_identity_mismatches": sum(row.get("published_identity_mismatches", 0) for row in rows),
        "transport_failures": sum(1 for row in rows if row.get("transport_failure")),
    }
    if count_key:
        counts = [row.get(count_key, 0) for row in rows]
        summary[f"{count_key}_total"] = sum(counts)
        summary[f"{count_key}_per_company_mean"] = round(sum(counts) / n, 3)
        summary[f"{count_key}_per_covered_company_mean"] = round(sum(counts) / covered, 3) if covered else 0.0
    return summary


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


class Timer:
    def __enter__(self) -> "Timer":
        self.started = time.monotonic()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.ms = int((time.monotonic() - self.started) * 1000)
