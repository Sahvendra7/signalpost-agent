"""Is a profile linked from the verified website the company's own (design §B4)?

Being linked from the site is necessary, never sufficient. The handle must name this company; a brand or an extended
name is accepted only with corroboration that the site itself is the company's and named after it. A sister company,
parent, group, platform or unrelated account is held as "not attributed", with the reason.
"""
from __future__ import annotations

from .decision import Decision
from .names import Relation
from typing import Any

SCORES = {"EXACT": 0.98, "EXACT_NEUTRAL": 0.95, "BRAND": 0.9, "EXTENDS": 0.9}
STRICT_KINDS = {"group_or_brand", "section", "platform"}
HOLD_KINDS = {"manager", "other_entity"}


SHARED_SAME_NAME_KINDS = {"group_or_brand", "section"}


def decide_profile(relation: Relation, operator_kind: str, *, domain_named: bool, handle_starts_with_domain: bool, org_sameas: bool,
                   operator_basis: str = "", handle_is_domain: bool = False, names_site_entity: str | None = None,
                   bare_exact_on_same_name_domain: bool = False) -> tuple[Decision, float | None]:
    """(decision, score). `domain_named`: the verified site's domain label is the legal name or a brand of it (and the
    site is self-operated); `org_sameas`: the profile is in sameAs of an Organization node that names this company.
    `names_site_entity`: another company the site itself names with a legal form whose name the handle spells exactly.
    `bare_exact_on_same_name_domain`: the handle is the legal name with no legal-form or Norway marker, and the site's
    domain is named like the company (a larger organisation of the same name runs it)."""
    kind = relation.kind
    if operator_kind in HOLD_KINDS:
        return Decision(False, f"site_operated_by_{operator_kind}", operator_basis or "The website is run by another company; its profiles are not this company's."), None
    if names_site_entity and kind in ("BRAND", "EXTENDS"):
        return Decision(False, "handle_names_other_company_on_site",
                        f"The handle spells the name of another company that the website itself names ({names_site_entity}); it is that company's profile."), None
    if kind == "EXACT" and operator_kind in SHARED_SAME_NAME_KINDS and bare_exact_on_same_name_domain:
        return Decision(False, f"group_name_handle_on_{operator_kind}_site",
                        "The website belongs to a larger organisation with the same name, and the handle has no Norwegian or legal-form marker: "
                        "it is that organisation's profile, not necessarily this company's."), None
    if kind == "EXACT":
        return Decision(True, "handle_exact", "The profile handle is the company's legal name."), SCORES[kind]
    if kind == "EXACT_NEUTRAL":
        return Decision(True, "handle_exact_neutral", f"The profile handle is the company's legal name with a neutral addition ({relation.rest})."), SCORES[kind]
    if handle_is_domain and operator_kind == "self" and kind != "OTHER_ENTITY":
        # The profile carries the name of the company's own registry-linked website ("ringblad" on ringblad.no), and
        # nothing on the site says another company runs it: the profile links back to the company's website by name.
        return Decision(True, "handle_is_own_domain_name", "The profile handle is the name of the company's own website, which no other company runs."), 0.9
    if kind == "OTHER_ENTITY":
        return Decision(False, "handle_names_other_entity", f"The profile handle names another entity (\"{relation.rest}\"), such as a group, parent or sister company."), None
    if kind == "UNRELATED":
        return Decision(False, "handle_unrelated", "The profile handle does not carry the company's name."), None
    if operator_kind in STRICT_KINDS:
        return Decision(False, f"brand_handle_on_{operator_kind}_site", "The handle is a brand or extended name, and the website is shared with other companies; only exact legal-name handles are attributed there."), None
    if kind == "BRAND":
        if domain_named:
            return Decision(True, "brand_handle_on_own_named_site", "The handle is the company's short name, and the company's own website is named after it."), SCORES[kind]
        return Decision(False, "brand_handle_uncorroborated", "The handle is only part of the company's name, and nothing else ties it to this company."), None
    if kind == "EXTENDS":
        if domain_named and handle_starts_with_domain:
            return Decision(True, "extended_handle_on_own_named_site", "The handle starts with the company's own website name."), SCORES[kind]
        if org_sameas:
            return Decision(True, "extended_handle_in_own_structured_data", "The company's own structured data, which names the company, lists this profile."), SCORES[kind]
        return Decision(False, "extended_handle_uncorroborated", f"The handle adds \"{relation.rest}\" to the company's name, and nothing ties it to this company."), None
    return Decision(False, "handle_unrelated", "The profile handle does not carry the company's name."), None


# ---------- V3.1.1: owner checks applied before the handle decision (docs/v311-rescore-revision.md §3) ----------
# Builderr's audit of ff3b515 found profiles that belong to other organisations: a website builder's own accounts
# (squarespace on a Squarespace-built site), and group or parent accounts on a subsidiary's site. Each check below
# looks only at the URL itself, the company's legal name, its registry group record and its website's domain. None
# names a company, and none can be overridden by sameAs structured data or an anchor label: they run first.

import re as _re
import urllib.parse as _urlparse

from .names import LegalName as _LegalName, fold as _fold, handle_of as _handle_of

# Accounts of website builders, hosting and CMS providers, and of the social platforms themselves. A site built on one
# carries the provider's links in its template (Squarespace's default sameAs, a "Powered by Wix" footer); a profile
# with such a handle is the provider's, never the tenant's, unless the tenant's own legal name is that handle.
PLATFORM_PROVIDERS = frozenset({
    "squarespace", "wix", "wixcom", "wixstudio", "wordpress", "wordpresscom", "wpengine", "weebly", "shopify", "jimdo", "godaddy",
    "webflow", "hubspot", "mailchimp", "onecom", "webnode", "strikingly", "site123", "blogger", "tumblr", "yola", "duda", "zyro",
    "hostinger", "bluehost", "elementor", "elegantthemes", "themeforest", "envato", "yoast", "cloudflare", "framer", "carrd",
    "smugmug", "zenfolio", "pixieset", "showit", "domeneshop", "proisp", "uniweb", "mystore", "visma", "facebook", "meta", "instagram",
    "linkedin", "youtube", "google", "twitter", "tiktok", "pinterest", "snapchat", "vimeo",
})
# Path segments that make a platform URL something other than the public profile: an administrator's console, a page
# verification flow or a login. "linkedin.com/company/squarespace/mycompany/verification/" is Squarespace's admin link.
NON_PROFILE_SEGMENTS = frozenset({"mycompany", "admin", "verification", "verify", "edit", "analytics", "setup", "login", "inbox", "settings", "manage"})
# Country words in a legal name that mark a national unit of a larger organisation ("GRUNDFOS NORGE AS",
# "BECTON DICKINSON U.K. LIMITED"). A handle without the word is the wider organisation's account.
NORWAY_MARKERS = ("norge", "norway", "noreg", "norwegian", "norsk")
NATIONAL_MARKERS = frozenset({"norge", "norway", "noreg", "uk", "sverige", "sweden", "danmark", "denmark", "finland", "suomi", "deutschland", "germany", "usa"})
NORWEGIAN_FORMS = frozenset({"AS", "ASA", "ANS", "DA", "ENK", "SA", "BA", "IKS", "KS", "STI", "FLI", "SAM", "NUF", "AAFY", "BRL", "ORGL"})
FOREIGN_FORM_WORDS = frozenset({"oy", "oyj", "ab", "gmbh", "ltd", "limited", "inc", "plc", "bv", "nv", "aps", "ag", "llc", "sa", "sas", "spa", "srl", "corp", "corporation"})
_LOCALE_HOST = _re.compile(r"^([a-z]{2})\.(?:linkedin|facebook)\.com$")


def _tld(url: str) -> str:
    host = (_urlparse.urlsplit(url).hostname or "").casefold().rstrip(".")
    return host.rsplit(".", 1)[-1] if "." in host else ""


def _words(text: str) -> list[str]:
    return _re.findall(r"[a-z0-9]+", _fold(text))


def national_markers(legal_name: str) -> set[str]:
    words = _words(legal_name)
    found = {word for word in words if word in NATIONAL_MARKERS}
    if any(a == "u" and b == "k" for a, b in zip(words, words[1:])):
        found.add("uk")
    return found


def _carries(handle: str, words: list[str], marker: str) -> bool:
    if marker in ("norge", "norway", "noreg"):
        return any(m in handle for m in NORWAY_MARKERS) or any(word in ("no", "nor") for word in words) or handle.endswith(("no", "nor"))
    if marker == "uk":
        return "uk" in words or handle.endswith("uk") or "unitedkingdom" in handle
    return marker in handle


def foreign_parent(profile: dict[str, Any]) -> str | None:
    """The top parent named in this company's registry group structure (konsernstruktur), when it is a foreign entity:
    registered as UTLA, or named with another country's legal form ("NELES CONTROLS OY" above VALMET AS)."""
    org = _re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    record = (profile.get("evidence") or {}).get("group") or {}
    value = record.get("value") if record.get("status") == "available" else None
    if not isinstance(value, dict):
        return None
    top_number = str(value.get("organisasjonsnummer") or "")
    if not top_number or top_number == org:
        return None
    form = str((value.get("organisasjonsform") or {}).get("kode") or "").upper()
    name = str(value.get("navn") or "")
    words = _words(name)
    if form == "UTLA" or (words and words[-1] in FOREIGN_FORM_WORDS):
        return name
    return None


def shared_group_brand(profile: dict[str, Any], legal: _LegalName, handle: str, words: list[str]) -> str | None:
    """Another registry group company whose name also begins with the handle's brand (MOELVEN WOOD AS's `moelven` next to
    Moelven Industrier ASA and Moelven Bioenergi AS). Only a brand handle (shorter than the legal name, possibly with a
    neutral or domain affix) is affected: a handle that spells this company's full legal name stays this company's."""
    from .operator import registry_group_names
    from .names import NEUTRAL, compact as _compact_name

    if not handle or handle in (legal.compact, legal.compact_full) or not legal.compact.startswith(handle[:4]):
        return None
    stem = next((brand for brand in sorted(legal.brands, key=len, reverse=True) if handle.startswith(brand)), None)
    if not stem or any(marker in handle[len(stem):] for marker in ("norge", "norway")) or legal.compact.startswith(handle) and handle != stem and len(handle) > len(stem) + 3:
        return None
    others = [name for number, name in registry_group_names(profile) if _compact_name(name).startswith(stem) and _compact_name(name) != legal.compact]
    return ", ".join(sorted(others)[:3]) or None


def owner_check(profile: dict[str, Any], legal: _LegalName, platform: str, url: str, site_url: str) -> Decision | None:
    """A Decision to withhold when the URL itself shows the profile is not this company's; None otherwise."""
    parsed = _urlparse.urlsplit(url)
    segments = [segment.casefold() for segment in parsed.path.split("/") if segment]
    tail = segments[2:] if platform == "linkedin" else segments[1:]
    hit = next((segment for segment in tail if segment in NON_PROFILE_SEGMENTS), None)
    if hit:
        return Decision(False, "not_a_public_profile_url",
                        f"The link is a platform administration or verification page (/{hit}/), not a public company profile.")
    handle, words = _handle_of(platform, url)
    exact = bool(handle) and handle in (legal.compact, legal.compact_full)
    if handle in PLATFORM_PROVIDERS and not exact:
        return Decision(False, "platform_provider_account",
                        f"\"{handle}\" is the account of a website or social-media platform provider; a link to it in a site's template or "
                        "structured data is not this company's profile.")
    legal_form = str(profile.get("legal_form") or "").upper()
    name = str(profile.get("name") or legal.name or "")
    site_tld = _tld(site_url)
    shared = shared_group_brand(profile, legal, handle, words)
    if shared:
        return Decision(False, "group_shared_brand_handle",
                        f"The handle is the brand \"{handle}\", which other companies in this company's registry group also carry ({shared}); it is "
                        "the group's account, not necessarily this company's.")
    locale = _LOCALE_HOST.match((parsed.hostname or "").casefold())
    foreign_locale = bool(locale) and locale.group(1) not in ("no", "www") and site_tld != locale.group(1)
    markers = national_markers(name)
    missing = sorted(marker for marker in markers if not _carries(handle, words, marker))
    if missing and (site_tld != "no" or foreign_locale):
        return Decision(False, "group_account_without_national_unit",
                        f"The company is a national unit (\"{missing[0]}\" in its legal name), the handle leaves that out, and the website is a wider "
                        "organisation's: it is the group's account, not this company's.")
    norwegian = legal_form in NORWEGIAN_FORMS and not (markers - {"norge", "norway", "noreg"})
    parent = foreign_parent(profile)
    carries_norway = any(m in handle for m in NORWAY_MARKERS) or any(word in ("no", "nor") for word in words)
    if parent and site_tld != "no" and not carries_norway:
        return Decision(False, "foreign_parent_group_account",
                        f"The registry lists a foreign parent ({parent}), the website is the group's international site, and the handle has no Norwegian "
                        "marker: the account is the group's, not this Norwegian company's.")
    if norwegian and foreign_locale and site_tld != "no" and not carries_norway:
        return Decision(False, "account_localised_abroad_on_group_site",
                        f"A Norwegian company's international website links the profile in another country's locale ({locale.group(1)}.), and the handle "
                        "has no Norwegian marker: the account is run abroad by the wider organisation.")
    return None
