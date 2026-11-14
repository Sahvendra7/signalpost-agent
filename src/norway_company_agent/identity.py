from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any


LEGAL_AND_GENERIC = {
    "as", "asa", "ans", "da", "enk", "iks", "sa", "sam", "sti", "stiftelsen",
    "nuf", "ab", "b", "v", "limited", "ltd", "inc", "plc", "the", "og", "and",
}


def _tokens(value: Any) -> list[str]:
    text = str(value or "").translate(str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [token for token in re.findall(r"[a-z0-9]+", text) if token not in LEGAL_AND_GENERIC and len(token) > 1]


def _structured_names(value: Any) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"name", "legalName", "alternateName"} and isinstance(child, str):
                names.append(child)
            else:
                names.extend(_structured_names(child))
    elif isinstance(value, list):
        for child in value:
            names.extend(_structured_names(child))
    return names


# ---- Registry-listed sites whose identity evidence is the domain itself or the owner's name (V3.1.2) ----
# Legal-form words a legal name ends with. A site writes "Impakt Geofysik AB" for the registered
# "IMPAKT GEOFYSIK AKTIEBOLAG": the form is not part of the name to be matched.
TRAILING_LEGAL_FORMS = {
    "aktiebolag", "aktieselskap", "aktieselskab", "aps", "ag", "gmbh", "oy", "oyj", "llc", "sarl", "srl", "spa",
    "nv", "kft", "ou", "uab", "sia", "ehf", "hf", "kg", "se", "nuf",
}
# Parked or placeholder pages not already named in PARKED_MARKERS; consulted by the V3.1.2 rules only.
PLACEHOLDER_MARKERS = (
    "is parked", "domain parking", "parked domain", "domenet er parkert", "this domain is registered",
    "buy this domain", "kjop dette domenet", "site maintenance", "under construction", "coming soon",
    "nettsiden er under utvikling", "siden er under konstruksjon",
    "no website is currently present", "this server is operated by", "could be suspended", "account suspended",
    "account has been suspended", "default web page", "welcome to nginx", "apache2 ubuntu default", "index of /",
    "webhotellet er", "denne siden er under", "domenet er registrert",
)
# A company name written with its legal form: "Blindheim Fysikalske Institutt AS". Case-sensitive on purpose
# ("Da" and "da" are words; "DA" after a capitalised name is a legal form).
STATED_ENTITY = re.compile(r"((?:[A-ZÆØÅ0-9][\w&'.\-]*[ \t]+){1,4})(AS|ASA|A/S|ANS|DA|SA|BA|AB|ApS|GmbH|Ltd\.?|Limited|Inc\.?|Oy|LLC)(?![\w])")


# A page a registrar, web host or broken installation serves in place of a site. Read on thin pages only (one page, a
# few lines of text), where these words are about the domain itself and not about the company's business.
HOST_PLACEHOLDER = re.compile(
    r"parked|parkert|parkering|expired|utl[oø]pt|site unavailable|currently unavailable|no website|not have an active website|"
    r"ingen nettside|hosted by|this server is operated|web ?hosting|webhotell|domeneregistrar|domain registrar|renew it|suspended|"
    r"find your own domain|this domain|dette domenet|domenet er|fatal error|default (?:web )?page|it works!|index of /|welcome to nginx|"
    r"buy this domain|domain (?:is )?for sale|domenet er til salgs",
    re.I,
)


def host_placeholder(value: dict[str, Any]) -> str | None:
    """The marker found when the captured homepage is a registrar's, web host's or broken installation's page."""
    if len(value.get("pages") or []) > 1 or len(str(value.get("main_text_excerpt") or "")) >= 600:
        return None
    match = HOST_PLACEHOLDER.search(" ".join(str(value.get(key) or "") for key in ("title", "description", "main_text_excerpt")))
    return match.group(0) if match else None


def _states_name(words: list[str], value: dict[str, Any], hostname: str) -> bool:
    """The page's own text (title, description, body, footer) writes these name words together, in order. The
    domain is not text: "example.no is parked" and a file path in an error message state nothing."""
    text = " ".join(str(value.get(key) or "") for key in ("title", "description", "main_text_excerpt", "identity_text_excerpt"))
    text = " ".join([text, *_structured_names(value.get("structured_organisations") or [])])
    return bool(words) and "".join(words) in "".join(_tokens(_without_domain_mentions(text, hostname)))


def _without_domain_mentions(text: str, hostname: str) -> str:
    """Text with the site's own domain name, URLs and file paths removed ("www.example.no is parked" -> " is parked")."""
    host = hostname.casefold().removeprefix("www.")
    if host:
        text = re.sub(r"[\w.\-]*" + re.escape(host.split(".")[0]) + r"\.[a-z]{2,}", " ", text, flags=re.I)
    return re.sub(r"\S*/\S*", " ", text)


def _name_without_trailing_form(core: list[str]) -> list[str]:
    trimmed = list(core)
    while len(trimmed) > 1 and trimmed[-1] in TRAILING_LEGAL_FORMS:
        trimmed.pop()
    return trimmed


def _domain_label(hostname: str) -> str:
    """The registrable label of a hostname, hyphens removed: www.alle-gode-ting.no -> allegodeting."""
    from .website import _registered_domain  # late import: website imports nothing from here, but keep the cycle impossible

    domain = _registered_domain("https://" + hostname) if hostname else ""
    label = (domain or hostname).split(".")[0]
    return "".join(_tokens(label.replace("-", " ")) or [re.sub(r"[^a-z0-9]", "", label.casefold())])


def _owner_tokens(profile: dict[str, Any]) -> list[str]:
    """Name tokens of the registered owner (innehaver) of a sole proprietorship, from the roles register."""
    roles = (((profile.get("evidence") or {}).get("roles") or {}).get("value") or {}).get("roles") or []
    for role in roles:
        if role.get("role_code") == "INNH" and not role.get("inactive") and not role.get("organisation_number"):
            name = role.get("name")
            return _tokens(" ".join(name) if isinstance(name, list) else name)
    return []


def _same_person_token(name_token: str, owner_token: str) -> bool:
    # "BENGTSSONS KUNSTNERSKAP": the legal name carries the owner's surname in the genitive.
    return name_token == owner_token or (len(owner_token) >= 4 and name_token == owner_token + "s")


def _registered_place_stated(profile: dict[str, Any], text: str) -> bool:
    """The entity's registered postcode or postal town (business or postal address) is written on the captured pages."""
    live = (((profile.get("evidence") or {}).get("registry_live") or {}).get("value") or {})
    tokens = set(_tokens(text))
    for address in (live.get("business_address"), live.get("postal_address"), profile.get("business_address")):
        if not isinstance(address, dict):
            continue
        postcode = str(address.get("postnummer") or address.get("postal_code") or "").strip()
        town = _tokens(address.get("poststed") or address.get("city"))
        if (len(postcode) == 4 and re.search(r"(?<!\d)" + re.escape(postcode) + r"(?!\d)", text)) or (town and len("".join(town)) >= 3 and set(town).issubset(tokens)):
            return True
    return False


def _registry_listed_site_rule(profile: dict[str, Any], core: list[str], hostname: str, homepage_token_sets: list[set[str]], *, substantive: bool, folded_text: str, raw_text: str, value: dict[str, Any]) -> str | None:
    """A reason when a registry-listed site's own domain or the registered owner's name identifies the entity, else None.

    Every rule needs the registry's own link (the caller applies this to the registry-listed website only) and no parked
    or placeholder marker; all but the last also need a homepage with real content (the last has the owner's name
    stated on it, which a portfolio site often has and little else). A site that names another company with a legal
    form and a word of this entity's name is that company's. None accepts name similarity alone:
      * the homepage states the legal name, the trailing legal-form word aside (AKTIEBOLAG ~ AB);
      * the domain label is exactly the legal name written together (at least two name words), the page's own text
        writes that name, and the domain is .no or the pages carry the entity's registered postcode or town;
      * a sole proprietorship (ENK) whose domain is exactly its trade name, the part of the legal name that is not the
        registered owner's name, written in the page's own text; or whose domain carries the owner's name and whose
        homepage states that name.
    """
    if not core or any(marker in folded_text for marker in PLACEHOLDER_MARKERS):
        return None
    label = _domain_label(hostname)
    trimmed = _name_without_trailing_form(core)
    # A name-shaped domain abroad is often the foreign parent's (a Norwegian AS named after its group): outside .no
    # the pages must place the entity at its registered postcode or town.
    norwegian_domain = hostname.casefold().endswith(".no")
    registered_place_stated = _registered_place_stated(profile, raw_text)
    owner = _owner_tokens(profile) if str(profile.get("legal_form") or "").upper() == "ENK" else []
    # The site names a company, with its legal form, whose name shares a word with this entity's but is not this
    # entity: a clinic's or firm's site (… Institutt AS) that a practitioner's sole proprietorship points at, the
    # limited company a proprietorship was converted into, a sister company. The site is theirs.
    own_words = set(core) | set(owner)
    for match in STATED_ENTITY.finditer(raw_text):
        stated = set(_tokens(match.group(1)))
        if stated & own_words and not set(trimmed).issubset(stated):
            return None
    if substantive and trimmed != core and len(trimmed) >= 2 and any(set(trimmed).issubset(tokens) for tokens in homepage_token_sets):
        return "the homepage states the legal name (its legal-form word aside) on the registry-listed website"
    if substantive and len(trimmed) >= 2 and len(label) >= 8 and label == "".join(trimmed) and (norwegian_domain or registered_place_stated) and _states_name(trimmed, value, hostname):
        return "the registry-listed domain is the legal name written together"
    if str(profile.get("legal_form") or "").upper() == "ENK":
        if owner:
            owner_in_name = [token for token in core if any(_same_person_token(token, part) for part in owner)]
            trade = [token for token in core if token not in owner_in_name]
            if substantive and trade and owner_in_name and len(label) >= 5 and label == "".join(trade) and _states_name(trade, value, hostname):
                return "sole proprietorship: the registry-listed domain is its trade name (the legal name without the registered owner's name)"
            stated = [part for part in owner if any(_same_person_token(token, part) for token in core)]
            if len(stated) >= 2 and any(len(part) >= 4 and part in label for part in stated) and any(set(stated).issubset(tokens) for tokens in homepage_token_sets):
                return "sole proprietorship: the registry-listed domain carries the registered owner's name and the homepage states it"
    return None


def assess_website_identity(profile: dict[str, Any]) -> dict[str, Any]:
    website = profile.get("evidence", {}).get("website", {})
    value = website.get("value") or {}
    core = _tokens(profile.get("name"))
    hostname = urllib.parse.urlparse(value.get("final_url") or website.get("source_url") or "").hostname or ""
    structured_names = _structured_names(value.get("structured_organisations") or [])
    rendered = value.get("js_fallback") or {}
    homepage_identity_parts = [
        value.get("title"), value.get("description"), value.get("identity_text_excerpt"), hostname, *structured_names,
        rendered.get("title"),
    ]
    candidate_parts = [
        *homepage_identity_parts, value.get("main_text_excerpt"),
        *[page.get("title") for page in value.get("pages", [])],
        *[page.get("main_text_excerpt") for page in value.get("pages", [])],
        *[page.get("identity_text_excerpt") for page in value.get("pages", [])],
    ]
    candidate_parts.append(rendered.get("main_text_excerpt"))
    candidate_text = " ".join(str(part or "") for part in candidate_parts)
    homepage_candidate_text = " ".join(str(part or "") for part in [*homepage_identity_parts, value.get("main_text_excerpt"), rendered.get("main_text_excerpt")])
    normalized_candidate_text = " ".join(_tokens(candidate_text))
    candidate_tokens = set(_tokens(candidate_text))
    org_digits = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    compact_candidate = re.sub(r"\D", "", candidate_text)
    compact_homepage_candidate = re.sub(r"\D", "", homepage_candidate_text)
    overlap = sorted(set(core) & candidate_tokens)
    ratio = len(overlap) / len(set(core)) if core else 0.0
    reasons = []
    parked_markers = (
        "domain is for sale", "domain for sale", "hugedomains", "parked at", "miss hosting",
        "her flytter snart en ny gjest", "has been informing visitors",
        "find the best information and most relevant links on all topics related to",
    )
    normalized_raw = unicodedata.normalize("NFKD", candidate_text).encode("ascii", "ignore").decode().casefold()
    homepage_token_sets = [set(_tokens(part)) for part in homepage_identity_parts if part]
    # A one-page capture with a few lines of text (a placeholder, an empty shell): the domain alone is not the page
    # stating a name. The hostname counts as identity text only next to real content or further pages.
    thin_capture = len(value.get("pages") or []) <= 1 and len(str(value.get("main_text_excerpt") or "")) < 600
    stated_token_sets = [set(_tokens(_without_domain_mentions(str(part), hostname))) for part in homepage_identity_parts if part and part != hostname] if thin_capture else homepage_token_sets
    exact_homepage_name = bool(core and any(set(core).issubset(tokens) for tokens in stated_token_sets))
    substantive_homepage = len(str(value.get("main_text_excerpt") or "").strip()) >= 100
    is_business_sports_club = bool(re.search(r"(?:^|\s)B\.?\s*I\.?\s*L\.?(?:\s|$)", str(profile.get("name") or ""), re.I))
    if any(marker in normalized_raw for marker in parked_markers):
        score = 0.1
        reasons.append("captured page is a parked, for-sale, or generic hosting placeholder")
    elif placeholder := host_placeholder(value):
        score = 0.1
        reasons.append(f"captured page is a registrar, web-host or error placeholder, not a website (“{placeholder}”)")
    elif is_business_sports_club and "bedriftsidrett" not in normalized_candidate_text and "b i l" not in normalized_candidate_text:
        score = 0.3
        reasons.append("business sports-club entity points to the operating company's site without club evidence")
    elif org_digits and org_digits in compact_homepage_candidate:
        score = 1.0
        reasons.append("exact organisation number appears in homepage identity evidence")
    elif len(core) >= 2 and exact_homepage_name:
        score = 0.95
        reasons.append("all normalized legal-name tokens appear together in homepage identity evidence")
    elif len(core) == 1 and exact_homepage_name and substantive_homepage:
        score = 0.95
        reasons.append("single distinctive legal-name token appears in homepage identity evidence with substantive content")
    elif listed_site_reason := _registry_listed_site_rule(profile, core, hostname, homepage_token_sets, substantive=substantive_homepage, folded_text=normalized_raw, raw_text=candidate_text, value=value):
        score = 0.92
        reasons.append(listed_site_reason)
    elif ratio >= 0.75 and len(overlap) >= 2:
        score = 0.85
        reasons.append("most legal-name tokens appear, but exact identity is incomplete")
    elif ratio >= 0.5 and len(overlap) >= 2:
        score = 0.65
        reasons.append("partial legal-name overlap only")
    else:
        score = 0.3
        reasons.append("registry-linked URL lacks strong exact-entity identity evidence")
    status = "exact" if score >= 0.9 else "review" if score >= 0.8 else "related_or_uncertain"
    return {
        "status": status,
        "score": score,
        "publishable": status == "exact",
        "legal_name_tokens": core,
        "matched_tokens": overlap,
        "reasons": reasons,
        "method": "deterministic_name_org_evidence_v2",
    }


def assess_social_identity(profile: dict[str, Any], link: dict[str, str]) -> dict[str, Any]:
    core = _tokens(profile.get("name"))
    parsed = urllib.parse.urlparse(link.get("url") or "")
    handle_text = urllib.parse.unquote(parsed.path)
    handle_compact = "".join(_tokens(handle_text))
    matched = [token for token in core if token in handle_compact]
    core_compact = "".join(core)
    ratio = len(set(matched)) / len(set(core)) if core else 0.0
    if core_compact and core_compact in handle_compact:
        score = 0.98
        reason = "normalized legal-name sequence appears in the social handle"
    elif len(core) == 1 and matched:
        score = 0.95
        reason = "single distinctive legal-name token appears in the social handle"
    elif ratio >= 0.75 and len(set(matched)) >= 2:
        score = 0.9
        reason = "most legal-name tokens appear in the social handle"
    else:
        score = 0.3
        reason = "social handle lacks strong exact-entity name evidence"
    return {
        **link,
        "identity_score": score,
        "publishable": score >= 0.9,
        "matched_tokens": matched,
        "reason": reason,
        "method": "deterministic_social_handle_identity_v1",
    }


def apply_website_identity_gate(profile: dict[str, Any], website: dict[str, Any]) -> dict[str, Any]:
    if website.get("status") != "available":
        return {"website": website, "assessment": None, "quarantined_social_links": 0}
    temporary_profile = {**profile, "evidence": {**profile.get("evidence", {}), "website": website}}
    value = website.get("value") or {}
    assessment = assess_website_identity(temporary_profile)
    value["identity_assessment"] = assessment
    original = list(value.get("discovered_social_links") or value.get("social_links") or [])
    value["discovered_social_links"] = original
    social_assessments = [assess_social_identity(profile, link) for link in original]
    value["social_link_assessments"] = social_assessments
    value["social_links"] = [
        {"platform": item["platform"], "url": item["url"]}
        for item in social_assessments
        if assessment["publishable"] and item["publishable"]
    ]
    website["value"] = value
    return {
        "website": website,
        "assessment": assessment,
        "quarantined_social_links": len(original) - len(value["social_links"]),
    }


PARKED_MARKERS = (
    "domain is for sale", "domain for sale", "hugedomains", "parked at", "miss hosting",
    "her flytter snart en ny gjest", "has been informing visitors",
    "find the best information and most relevant links on all topics related to",
)


def assess_discovered_website_identity(profile: dict[str, Any], website: dict[str, Any]) -> dict[str, Any]:
    """Stricter gate for a URL the registry did NOT list for this organisation number.

    Publishable only with (a) the organisation number on a captured page of the site, or (b) every
    legal-name token in homepage identity text AND the registered postcode plus a street token on the
    site. Name similarity alone never passes: a discovered domain carries no registry endorsement.
    """
    value = website.get("value") or {}
    pages = value.get("pages") or []
    homepage_parts = [value.get("title"), value.get("description"), value.get("identity_text_excerpt"), *_structured_names(value.get("structured_organisations") or [])]
    all_parts = [*homepage_parts, value.get("main_text_excerpt"), *[page.get(key) for page in pages for key in ("title", "main_text_excerpt", "identity_text_excerpt")]]
    all_text = " ".join(str(part or "") for part in all_parts)
    folded = unicodedata.normalize("NFKD", all_text).encode("ascii", "ignore").decode().casefold()
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    core = _tokens(profile.get("name"))
    address = profile.get("business_address") or {}
    postcode = str(address.get("postnummer") or address.get("postal_code") or "")
    street_tokens = [token for line in (address.get("adresse") or address.get("lines") or []) for token in _tokens(line) if not token.isdigit() and len(token) > 3]
    reasons: list[str] = []
    if website.get("status") != "available":
        status, score = "not_available", 0.0
        reasons.append("candidate site not available")
    elif any(marker in folded for marker in PARKED_MARKERS):
        status, score = "rejected", 0.1
        reasons.append("parked, for-sale or hosting placeholder")
    elif org and re.search(r"(?<!\d)" + r"\D{0,3}".join(org) + r"(?!\d)", all_text):
        status, score = "exact", 1.0
        reasons.append("organisation number appears on a captured page of the discovered site")
    elif core and any(set(core).issubset(set(_tokens(part))) for part in homepage_parts if part) and postcode and postcode in all_text and any(token in set(_tokens(all_text)) for token in street_tokens):
        status, score = "exact", 0.95
        reasons.append("full legal name on homepage plus registered postcode and street on the site")
    else:
        status, score = "ambiguous", 0.3
        reasons.append("no organisation number and no name-plus-registered-address corroboration")
    return {"status": status, "score": score, "publishable": status == "exact", "reasons": reasons, "method": "discovered_site_strict_v1"}
