"""Who operates the verified website (design §B5)? Decided from pages the crawl already captured; no request is made.

Kinds, first match wins:
  manager         the registered business manager's site (Revision 1, MANAGER_DESIGNATED)
  platform        a tenant subdomain of a hosting platform (C300)
  section         a section of a larger organisation's domain (C300)
  self            the company's own organisation number is stated on a captured page
  other_entity    another organisation number is stated in an imprint, ours nowhere
  group_or_brand  the site is a group's or a brand's: a redirect to another domain, a domain unrelated to the legal
                  name with the name absent, a "BRAND + own town" name in a corporate group with the full name absent
                  from the homepage, or sibling "BRAND + other place" names in the site's own taxonomy
  self            otherwise
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from ..inputs import mod11_valid
from .names import COUNTIES, REGIONS, LegalName, compact, fold

IMPRINT_CUE = re.compile(r"(?:org(?:anisasjons)?\.?\s*-?\s*(?:nr|nummer|no)\b\.?|organisasjonsnummer|foretaksregisteret|selskapsinformasjon)\s*[:.]?\s*", re.I)
VAT_NUMBER = re.compile(r"(?<![A-Za-z])NO\s?(\d{3})[\s.]?(\d{3})[\s.]?(\d{3})\s?MVA")
DIRECTORY_SEGMENTS = {"forhandlere", "forhandler", "partnere", "partner", "partners", "medlemmer", "members", "kunder", "referanser", "leverandorer",
                      "dealers", "resellers", "butikker", "avdelinger", "kontorer"}
NINE_DIGITS = re.compile(r"(?<!\d)(\d{3})[\s. ]?(\d{3})[\s. ]?(\d{3})(?!\d)")


@dataclass(frozen=True)
class SiteOperator:
    kind: str
    code: str
    basis: str
    signals: tuple[dict[str, Any], ...] = field(default=())
    operator_org: str | None = None

    def record(self) -> dict[str, Any]:
        return {"kind": self.kind, "code": self.code, "basis": self.basis, "signals": [dict(signal) for signal in self.signals], "operator_org": self.operator_org}


def stated_org_numbers(text: str) -> list[tuple[str, str]]:
    """(organisation number, span) for valid numbers written right after an imprint cue ("org.nr. 930 182 451")."""
    found: list[tuple[str, str]] = []
    for match in VAT_NUMBER.finditer(text):
        number = "".join(match.groups())
        if mod11_valid(number) and number not in {item[0] for item in found}:
            found.append((number, " ".join(match.group(0).split())))
    for cue in IMPRINT_CUE.finditer(text):
        window = text[cue.end():cue.end() + 40]
        match = NINE_DIGITS.search(window)
        if match and match.start() <= 12:
            number = "".join(match.groups())
            if mod11_valid(number) and number not in {item[0] for item in found}:
                start = cue.start()
                found.append((number, " ".join(text[start:cue.end() + match.end()].split())))
    return found


def _digits(text: str) -> str:
    return re.sub(r"(?<=\d)[\s. ](?=\d)", "", text)


def _label(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").casefold().removeprefix("www.")
    return host.split(".")[0] if host else ""


def _registered(url: str) -> str | None:
    from ..website import _registered_domain  # local import: website.py imports heavy modules

    return _registered_domain(url) if url else None


def sibling_names(legal: LegalName, labels: list[str]) -> set[str]:
    """Taxonomy labels naming a sibling unit of the same brand ("Betonmast Trøndelag" for BETONMAST OSLO AS). Only
    applies when the legal name itself is BRAND + place qualifier; other companies' categories are never read this way."""
    if not legal.qualifiers:
        return set()
    first = legal.tokens.index(legal.qualifiers[0])
    brand = "".join(legal.tokens[:first])
    own_rest = legal.compact[len(brand):]
    if len(brand) < 4:
        return set()
    siblings = set()
    for label in labels:
        value = compact(label)
        if value.startswith(brand) and value != legal.compact:
            rest = value[len(brand):]
            if len(rest) >= 3 and rest != own_rest:
                siblings.add(value)
    return siblings


def registry_group_names(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """(organisation number, name) of every other company in the registry group structure (parent, top parent, sisters)."""
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    record = (profile.get("evidence") or {}).get("group") or {}
    value = record.get("value") if record.get("status") == "available" else None
    found: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for number_key, name_key in (("organisasjonsnummer", "navn"), ("parentOrganisasjonsnummer", "parentNavn")):
                number, name = str(node.get(number_key) or ""), str(node.get(name_key) or "")
                if number and name and number != org:
                    found.setdefault(number, name)
            for child in node.get("children") or []:
                walk(child)
    walk(value)
    return sorted(found.items())


def registry_group_company_named_by(label: str, profile: dict[str, Any], legal: LegalName) -> tuple[str, str] | None:
    """The other group company the domain label is named after, if the label is not named after this company."""
    label = compact(label)
    if len(label) < 3 or legal.domain_named(label) or label in (legal.compact, legal.compact_full):
        return None
    for number, name in registry_group_names(profile):
        other = LegalName(name)
        if other.compact and (label == other.compact or label == other.compact_full or other.domain_named(label) and not legal.domain_related(label)):
            return number, name
    return None


def assess_operator(profile: dict[str, Any], site_url: str, *, page_texts: list[tuple[str, str]], homepage_text: str = "",
                    website_value: dict[str, Any] | None = None, identity_class: str | None = None, shared_kind: str | None = None,
                    taxonomy: list[str] | None = None, legal: LegalName | None = None) -> SiteOperator:
    """`page_texts`: (url, visible text with header/footer) of every captured page of the verified site."""
    legal = legal or LegalName.from_profile(profile)
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    live = ((profile.get("evidence") or {}).get("registry_live") or {}).get("value") or {}
    if identity_class == "MANAGER_DESIGNATED":
        return SiteOperator("manager", "manager_designated", "The website is operated by the registered business manager.")
    if shared_kind == "platform":
        return SiteOperator("platform", "hosting_platform_tenant", "The website is one tenant of a hosting platform's domain.")
    signals: list[dict[str, Any]] = []
    others: list[tuple[str, str, str]] = []
    own_stated = False
    for url, text in page_texts:
        if org and org in _digits(text):
            own_stated = True
            signals.append({"signal": "own_org_number_stated", "page_url": url})
        stated = [(number, span) for number, span in stated_org_numbers(text) if number != org]
        directory = len({number for number, _ in stated}) >= 3 or any(segment in DIRECTORY_SEGMENTS for segment in urllib.parse.urlsplit(url).path.casefold().split("/"))
        if not directory:  # a list of dealers, partners or members names other companies, not who runs the site
            others.extend((number, span, url) for number, span in stated)
    if shared_kind == "section":
        return SiteOperator("section", "section_of_shared_domain", "The website is a section of a larger organisation's domain.", tuple(signals))
    related = registry_group_company_named_by(_label(site_url), profile, legal)
    if related:
        # V3.1: the domain carries the name of another company in the registry group (BE KRAFTSALG AS's site
        # bodoenergi.no states its own org. number but trades as "Bodø Energi", the name of its parent BODØ ENERGI AS).
        # The site is still this company's website, but stories and profiles under the shared name may be either
        # company's: only items naming this company are attributed to it.
        return SiteOperator("group_or_brand", "site_named_after_registry_group_company",
                            f"The website's name is that of {related[1]} ({related[0]}), another company in this company's registry group; "
                            "stories and profiles under that name may be either company's, so only items naming this company are attributed to it.",
                            tuple(signals[:1]) + ({"signal": "site_named_after_registry_group_company", "organisation_number": related[0], "name": related[1]},))
    if own_stated:
        return SiteOperator("self", "own_org_number_on_site", "The company's own organisation number is stated on the website.", tuple(signals[:1]))
    if others:
        number, span, url = others[0]
        return SiteOperator("other_entity", "other_org_number_on_site",
                            f"The website states organisation number {number}, not this company's ({org}); it is run by another company.",
                            tuple({"signal": "other_org_number_stated", "organisation_number": n, "span": s, "page_url": u} for n, s, u in others[:5]), number)
    group: list[dict[str, Any]] = []
    value = website_value or {}
    requested, final = str(value.get("requested_url") or ""), str(value.get("final_url") or "")
    if requested and final and _registered(requested) and _registered(final) and _registered(final) == _registered(site_url) \
            and str(_registered(requested)).endswith(".no") and not str(_registered(final)).endswith(".no"):
        # the company's Norwegian domain now redirects to an international domain (bartec-technor.no -> bartec.com): the
        # group's site. A move to another .no domain (stalheim.com -> stalheimhotel.no, hadeland.net -> hadeland.no) is not.
        group.append({"signal": "registry_website_redirects_to_other_domain", "detail": f"{requested} -> {final}"})
    all_text = " ".join(text for _, text in page_texts)
    phrase_present = legal.phrase_in(all_text)
    label = _label(site_url)
    if label and not phrase_present and not legal.domain_related(label):
        group.append({"signal": "domain_and_site_do_not_name_the_company", "detail": f"domain label {label!r}; legal name phrase absent"})
    if legal.qualifiers and live.get("in_group") and any(compact(label) == brand for brand in legal.brands) and not legal.phrase_in(homepage_text):
        group.append({"signal": "brand_site_of_a_group_unit", "detail": f"legal name = brand + {', '.join(legal.qualifiers)}; full name absent from the homepage"})
    siblings = sibling_names(legal, taxonomy or [])
    if len(siblings) >= 2:
        group.append({"signal": "sibling_entities_in_site_taxonomy", "detail": "; ".join(sorted(siblings)[:5])})
    if group:
        return SiteOperator("group_or_brand", group[0]["signal"],
                            "The website belongs to a group or brand that this company is part of; only items naming this company are attributed to it.",
                            tuple(group))
    return SiteOperator("self", "no_contrary_signal", "No signal that another company runs the website.", tuple(signals))
