"""Experiment 4: deterministic (no search engine) website discovery for companies with no registry URL.

Candidate pointers, in order of evidence strength:
  subunit_website   - `hjemmeside` on a registered subunit of this organisation number (official)
  registry_email    - domain of a contact e-mail in the open entity record, if the field exists (official)
  nav_employer_site - employer homepage on a NAV ad whose employer.orgnr was verified (official, NAV)
  name_domain_guess - <legal-name>.no / <legal-name-hyphenated>.no (no endorsement at all)
Every candidate is crawled with the normal robots-respecting fetcher and must pass the strict
discovered-site gate (`assess_discovered_website_identity`). Candidates are evidence-free until then.
"""
from __future__ import annotations

import re
import socket
from typing import Any, Callable

from .common import Timer
from ..identity import _tokens, assess_discovered_website_identity
from ..website import fetch_website, normalize_homepage, _registered_domain

FREE_MAIL = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.no", "outlook.com", "outlook.no", "live.com", "live.no",
    "msn.com", "yahoo.com", "yahoo.no", "icloud.com", "me.com", "mac.com", "online.no", "frisurf.no", "start.no",
    "getmail.no", "broadpark.no", "lyse.net", "altibox.no", "epost.no", "mail.com", "c2i.net", "chello.no",
    "tele2.no", "telia.no", "sensewave.com", "proton.me", "protonmail.com",
}
EMAIL_KEYS = ("epostadresse", "epost", "email")


def registry_contact_fields(raw_entity: dict[str, Any]) -> dict[str, Any]:
    found = {}
    for key in ("epostadresse", "epost", "email", "telefon", "mobil", "mobiltelefon", "telefonnummer"):
        if key in raw_entity:
            found[key] = raw_entity[key]
    return found


def email_domain(value: Any) -> str | None:
    text = value.get("adresse") if isinstance(value, dict) else value
    match = re.search(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(text or ""))
    if not match:
        return None
    domain = match.group(1).lower().rstrip(".")
    return None if domain in FREE_MAIL or _registered_domain("https://" + domain) in FREE_MAIL else domain


def name_domain_guesses(name: Any) -> list[str]:
    core = _tokens(name)
    joined = "".join(core)
    if len(joined) < 5:
        return []
    guesses = [f"{joined}.no"]
    if len(core) > 1:
        guesses.append(f"{'-'.join(core)}.no")
    return guesses


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


def candidates_for(profile: dict[str, Any], raw_entity: dict[str, Any] | None, nav_homepages: list[str], *, include_guesses: bool = True) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for item in ((profile.get("evidence", {}).get("locations") or {}).get("value") or {}).get("locations", []):
        if item.get("website"):
            found.append({"source": "subunit_website", "url": item["website"]})
    for key in EMAIL_KEYS:
        domain = email_domain((raw_entity or {}).get(key))
        if domain:
            found.append({"source": "registry_email", "url": domain})
    for homepage in nav_homepages:
        found.append({"source": "nav_employer_site", "url": homepage})
    if include_guesses:
        for guess in name_domain_guesses(profile.get("name")):
            found.append({"source": "name_domain_guess", "url": guess})
    seen: set[str] = set()
    unique = []
    for item in found:
        normalized = normalize_homepage(item["url"])
        domain = _registered_domain(normalized) if normalized else None
        if not normalized or not domain or domain in seen or domain in FREE_MAIL:
            continue
        seen.add(domain)
        unique.append({**item, "url": normalized, "domain": domain})
    return unique


def run_company(
    profile: dict[str, Any],
    raw_entity: dict[str, Any] | None,
    nav_homepages: list[str],
    *,
    website_fetcher: Callable[..., tuple[dict[str, Any], dict[str, Any]]] = fetch_website,
    resolver: Callable[[str], bool] = resolves,
    include_guesses: bool = True,
) -> dict[str, Any]:
    profile = {**profile, "business_address": ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}).get("business_address") or {}}
    results = []
    requests = 0
    with Timer() as timer:
        for candidate in candidates_for(profile, raw_entity, nav_homepages, include_guesses=include_guesses):
            host = re.sub(r"^https?://", "", candidate["url"]).split("/")[0]
            if candidate["source"] == "name_domain_guess" and not resolver(host):
                results.append({**candidate, "outcome": "no_dns"})
                continue
            record, metrics = website_fetcher(candidate["url"])
            requests += int(metrics.get("requests", 0))
            assessment = assess_discovered_website_identity(profile, record)
            outcome = {"exact": "verified", "rejected": "rejected", "ambiguous": "ambiguous"}.get(assessment["status"], "unavailable")
            results.append({**candidate, "outcome": outcome, "score": assessment["score"], "reason": assessment["reasons"][0], "final_url": (record.get("value") or {}).get("final_url"), "content_sha256": record.get("content_sha256")})
    verified = [item for item in results if item["outcome"] == "verified"]
    return {
        "organisation_number": profile["organisation_number"],
        "requests": requests,
        "runtime_ms": timer.ms,
        "candidates": len(results),
        "by_source": {source: [item["outcome"] for item in results if item["source"] == source] for source in sorted({item["source"] for item in results})},
        "verified_sources": sorted({item["source"] for item in verified}),
        "covered": bool(verified),
        "verified_url": verified[0]["final_url"] if verified else None,
        "ambiguous": sum(1 for item in results if item["outcome"] == "ambiguous"),
        "identity_rejections": sum(1 for item in results if item["outcome"] in {"ambiguous", "rejected"}),
        "published_identity_mismatches": 0,
        "evidence_items": len(verified),
        "evidence_complete": sum(1 for item in verified if item.get("content_sha256") and item.get("final_url")),
        "results": results,
    }
