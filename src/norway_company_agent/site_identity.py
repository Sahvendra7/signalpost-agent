"""Website/profile trust classifier, policy v2 (docs/website-identity-policy-v2.md).

Classes: FIRST_PARTY_CONFIRMED, OFFICIALLY_LINKED (a profile linked from a FIRST_PARTY_CONFIRMED or registry-verified site),
THIRD_PARTY, FAN_COMMUNITY, DIRECTORY, AMBIGUOUS. Only FIRST_PARTY_CONFIRMED and OFFICIALLY_LINKED are publishable.

FIRST_PARTY_CONFIRMED needs a *control* signal, not just aboutness:
  C1 organisation number in the site's own footer/contact/legal text, with at most one other distinct
     organisation-number-shaped value on the captured pages; or
  C2 exact legal name + registered postcode + a street token, PLUS a mailbox on the site's own registered
     domain, or the registry e-mail domain equal to the site's domain.
Disqualifiers win over control signals: fan/community markers, directory shape, delegated contact
(all published mailboxes on another non-free-mail domain), parked/for-sale placeholders.
Registry phone numbers corroborate only; third parties copy them (976744667 → arasenstadion.no).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup

from .identity import PARKED_MARKERS, _tokens
from .website import IDENTITY_SELECTOR, _registered_domain

FREE_MAIL = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.no", "outlook.com", "outlook.no", "live.com", "live.no",
    "msn.com", "yahoo.com", "yahoo.no", "icloud.com", "me.com", "mac.com", "online.no", "frisurf.no", "start.no",
    "getmail.no", "broadpark.no", "lyse.net", "altibox.no", "epost.no", "mail.com", "c2i.net", "chello.no",
    "tele2.no", "telia.no", "proton.me", "protonmail.com", "verizon.net", "gmx.de", "gmx.com", "gmx.net", "aol.com",
    "ymail.com", "yahoo.co.uk", "hotmail.co.uk", "live.co.uk", "hotmail.se", "outlook.dk", "hotmail.dk", "comcast.net",
    "web.de", "t-online.de", "bluewin.ch", "orange.fr", "free.fr", "kpnmail.nl", "telenor.no", "netcom.no", "ebnett.no",
}
FAN_MARKERS = ("fansite", "fan site", "fanside", "fan-side", "supporterklubb", "supporter club", "uoffisiell", "unofficial", "ikke offisiell", "not affiliated", "ikke tilknyttet")
DIRECTORY_MARKERS = ("bedriftsoversikt", "firmaoversikt", "bedriftskatalog", "firmakatalog", "company directory", "alle bedrifter i", "finn bedrifter")
COMMUNITY_MARKERS = ("wiki", "forum", "diskusjonsforum")
ORG_SHAPE = re.compile(r"(?<!\d)(\d{3})[ . ]?(\d{3})[ . ]?(\d{3})(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


def decode_cfemail(hex_value: str) -> str | None:
    """Cloudflare e-mail obfuscation: first byte is an XOR key for the rest (deterministic)."""
    try:
        key = int(hex_value[:2], 16)
        return "".join(chr(int(hex_value[i:i + 2], 16) ^ key) for i in range(2, len(hex_value), 2))
    except ValueError:
        return None


def page_signals(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    emails = set(EMAIL.findall(" ".join(a.get("href", "") for a in soup.select("a[href^='mailto:']"))))
    emails |= set(EMAIL.findall(soup.get_text(" ", strip=True)))
    for node in soup.select("[data-cfemail]"):
        decoded = decode_cfemail(node.get("data-cfemail", ""))
        if decoded:
            emails |= set(EMAIL.findall(decoded))
    for anchor in soup.select("a[href*='email-protection#']"):
        decoded = decode_cfemail(anchor["href"].split("#", 1)[1])
        if decoded:
            emails |= set(EMAIL.findall(decoded))
    heading = " ".join(filter(None, [
        soup.title.get_text(" ", strip=True) if soup.title else "",
        " ".join(node.get_text(" ", strip=True) for node in soup.select("h1")[:3]),
        " ".join(str(node.get("content") or "") for node in soup.select('meta[name="description"], meta[property="og:site_name"], meta[property="og:title"]')),
    ]))
    identity = " ".join(" ".join(node.get_text(" ", strip=True) for node in soup.select(IDENTITY_SELECTOR)).split())
    return {
        "heading": heading,
        "identity_text": identity,
        "text": " ".join(soup.get_text(" ", strip=True).split()),
        "email_domains": sorted({domain.lower().rstrip(".") for domain in emails}),
    }


def classify_site(profile: dict[str, Any], site_domain: str, pages_html: list[str], *, registry_email: str | None = None) -> dict[str, Any]:
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    signals = [page_signals(html) for html in pages_html if html]
    heading = " ".join(item["heading"] for item in signals)
    identity_text = " ".join(item["identity_text"] for item in signals)
    all_text = " ".join(item["text"] for item in signals)
    folded_heading, folded_all = _fold(heading), _fold(all_text)
    email_domains = sorted({domain for item in signals for domain in item["email_domains"]})
    own_mail = [domain for domain in email_domains if _registered_domain("https://" + domain) == site_domain]
    foreign_mail = [domain for domain in email_domains if _registered_domain("https://" + domain) not in {site_domain} and _registered_domain("https://" + domain) not in FREE_MAIL and domain not in FREE_MAIL]
    org_values = {"".join(match) for match in ORG_SHAPE.findall(all_text)}
    registry_mail_domain = _registered_domain("https://" + registry_email.split("@")[-1]) if registry_email and "@" in registry_email else None
    address = profile.get("business_address") or {}
    postcode = str(address.get("postnummer") or address.get("postal_code") or "")
    streets = [token for line in (address.get("adresse") or address.get("lines") or []) for token in _tokens(line) if not token.isdigit() and len(token) > 3]
    core = _tokens(profile.get("name"))
    text_tokens = set(_tokens(all_text))
    signals_out = {
        "org_in_identity_text": bool(org and org in {"".join(match) for match in ORG_SHAPE.findall(identity_text)}),
        "org_anywhere": org in org_values,
        "other_org_numbers": len(org_values - {org}),
        "own_domain_mailbox": own_mail,
        "foreign_mailbox": foreign_mail,
        "registry_email_domain_match": bool(registry_mail_domain and registry_mail_domain == site_domain),
        "legal_name_in_heading": bool(core) and set(core).issubset(set(_tokens(heading))),
        "registered_postcode": bool(postcode) and postcode in all_text,
        "registered_street": any(token in text_tokens for token in streets),
    }
    reasons: list[str] = []
    if not signals:
        return {"class": "AMBIGUOUS", "publishable": False, "reasons": ["no captured pages"], "signals": signals_out}
    if any(marker in folded_all[:20000] for marker in PARKED_MARKERS):
        return {"class": "THIRD_PARTY", "publishable": False, "reasons": ["parked, for-sale or hosting placeholder"], "signals": signals_out}
    if any(marker in folded_heading for marker in FAN_MARKERS):
        return {"class": "FAN_COMMUNITY", "publishable": False, "reasons": ["fan/unofficial marker in title, h1 or meta"], "signals": signals_out}
    if any(marker in folded_heading for marker in COMMUNITY_MARKERS):
        return {"class": "FAN_COMMUNITY", "publishable": False, "reasons": ["community/wiki/forum marker in title, h1 or meta"], "signals": signals_out}
    if signals_out["other_org_numbers"] >= 3 or any(marker in folded_heading for marker in DIRECTORY_MARKERS):
        return {"class": "DIRECTORY", "publishable": False, "reasons": [f"directory shape ({signals_out['other_org_numbers']} other organisation numbers)"], "signals": signals_out}
    if foreign_mail and not own_mail:
        return {"class": "THIRD_PARTY", "publishable": False, "reasons": [f"contact delegated to another domain ({foreign_mail[0]})"], "signals": signals_out}
    if signals_out["org_in_identity_text"] and signals_out["other_org_numbers"] <= 1:
        return {"class": "FIRST_PARTY_CONFIRMED", "publishable": True, "reasons": ["C1: organisation number in the site's own footer/contact/legal text"], "signals": signals_out}
    name_address = signals_out["legal_name_in_heading"] and signals_out["registered_postcode"] and signals_out["registered_street"]
    control = bool(own_mail) or signals_out["registry_email_domain_match"]
    if name_address and control:
        reasons.append("C2: exact legal name + registered postcode and street + " + ("own-domain mailbox" if own_mail else "registry e-mail domain"))
        return {"class": "FIRST_PARTY_CONFIRMED", "publishable": True, "reasons": reasons, "signals": signals_out}
    if signals_out["org_anywhere"] and signals_out["other_org_numbers"] <= 1 and control:
        return {"class": "FIRST_PARTY_CONFIRMED", "publishable": True, "reasons": ["C1': organisation number on the site plus an own-domain/registry mailbox"], "signals": signals_out}
    if name_address:
        reasons.append("legal name and registered address present but no control indicator (aboutness only)")
    else:
        reasons.append("no control signal")
    return {"class": "AMBIGUOUS", "publishable": False, "reasons": reasons, "signals": signals_out}
