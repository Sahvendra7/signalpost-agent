"""Deterministic legal-entity identity gate (V3.2 research; reusable, not imported by the V3.1 run path).

Principle: the organisation number and the exact legal name *with its legal form* are identity evidence; a bare brand
is not. A website can be a company's declared web presence (the registry lists it) and still be *operated* by another
legal entity of its group; such a site cannot by itself make an item news about the target.

Site level (`assess_site`), from the captured homepage text and registry facts only:
  * target_operated  — the target's organisation number, its exact legal name with legal form, or its registered
                       street address with postal code appears on the site;
  * other_entity     — no target evidence, and the site names another legal entity under the target's brand
                       ("Brand Oyj" or "Brand AB" for BRAND AS), or states another organisation number;
  * group_site       — no target evidence, only the bare brand, and the registry places the target in a group whose
                       parent is foreign or the site's domain is not Norwegian (a global group site);
  * brand_only       — only the bare brand and no group signal: presumed the company's own (unchanged V3.1 behaviour);
  * unresolved       — not even the brand appears.

Item level (`assess_item`) is a hard gate (an LLM can never override it):
  * an item naming another legal entity under the target's brand without naming the exact target is withheld;
  * on group_site / other_entity sites an item must name the exact target (legal name with form, or org number);
  * on unresolved sites the item is withheld as ambiguous.
No company-specific exception exists anywhere in this module.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .attribution.names import FOREIGN_FORMS, LEGAL_FORMS, LegalName, fold

# legal forms that can follow a brand to name a distinct legal entity (lower-case, folded)
ENTITY_FORMS = sorted((FOREIGN_FORMS | LEGAL_FORMS | {"asa", "a/s", "corporation", "corp", "sa", "sas", "nv", "spa", "srl", "kg", "se", "oyj", "oy"})
                      - {"enk", "nuf", "iks", "ba", "bbl", "brl", "sti", "ks", "fli", "da", "ans"}, key=len, reverse=True)
_FORM_RE = "|".join(re.escape(f) for f in ENTITY_FORMS)
FOREIGN_PARENT_FORMS = {"ab", "oy", "oyj", "gmbh", "ag", "ltd", "limited", "inc", "llc", "plc", "bv", "nv", "sa", "sas", "spa", "aps", "a/s", "corporation", "corp", "kg", "se"}


AMBIGUOUS_FORMS = {"as", "sa", "se", "da", "ab", "ag", "nv", "bv", "kg", "asa", "sas", "spa", "a/s"}


def cfold(text: Any) -> str:
    """Case-preserving ASCII fold (same transliteration as names.fold, without lower-casing)."""
    import unicodedata
    value = urllib.parse.unquote(str(text or "")).translate(str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE",
                                                                          "\u2019": "'", "\u2018": "'", "\u02bc": "'"}))
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def written_form(word: str, allowed: set[str]) -> str | None:
    """The legal form `word` denotes, if it is written as a legal form: ambiguous short forms ("AS", "SA", "AB") only in
    capitals ("Brand as a partner" is English, not "Brand AS"); others with an initial capital ("Oy", "GmbH", "Inc")."""
    form = word.casefold()
    if form not in allowed:
        return None
    if form in AMBIGUOUS_FORMS:
        return form if word.isupper() or word == "A/S" else None
    return form if word[:1].isupper() else None


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def org_number_in(text: str, org: str) -> bool:
    """The 9-digit organisation number written plainly, spaced ("999 999 999") or as a VAT id ("NO999999999MVA")."""
    if not org or len(org) != 9:
        return False
    pattern = r"(?<!\d)" + r"[\s. ]?".join(org) + r"(?!\d)"
    return re.search(pattern, text or "") is not None


def other_org_numbers(text: str, org: str) -> list[str]:
    """Other organisation numbers stated with an org-number label (avoids phone numbers and prices)."""
    found = []
    for match in re.finditer(r"(?i)(?:org\.?\s*(?:nr|nummer|no)\.?|organisasjonsnummer|foretaksregisteret|mva)[\s:.\-]*((?:NO)?\s?\d{3}[\s. ]?\d{3}[\s. ]?\d{3})", text or ""):
        number = _digits(match.group(1))[-9:]
        if len(number) == 9 and number != org and number[0] in "89":
            found.append(number)
    return sorted(set(found))


@dataclass(frozen=True)
class TargetIdentity:
    org: str
    legal_name: str
    legal_form: str | None = None
    street: str | None = None
    postal_code: str | None = None
    municipality: str | None = None
    parents: tuple[dict[str, Any], ...] = ()
    group_members: tuple[dict[str, Any], ...] = ()
    registry_website: str | None = None

    @property
    def legal(self) -> LegalName:
        return LegalName(self.legal_name, self.municipality, None)

    @property
    def brand_tokens(self) -> list[str]:
        """Distinctive name tokens without the legal form: brand evidence only, never identity evidence."""
        return self.legal.tokens

    @property
    def own_forms(self) -> set[str]:
        return set(self.legal.own_forms) | ({fold(self.legal_form)} if self.legal_form else set())

    def _token_re(self, tokens: list[str]) -> str:
        joiner = r"(?:[\s\-_.&/,]|og|and|OG|AND)*"
        return joiner.join("(?i:" + re.escape(t) + ")" for t in tokens)

    def exact_name_matches(self, text: str) -> list[str]:
        """The legal name tokens in order followed by the target's own legal form, written as a legal form."""
        tokens = self.brand_tokens
        if not tokens:
            return []
        forms = (self.own_forms - {"nuf"}) or {"as"}
        out = []
        for match in re.finditer(r"(?<![A-Za-z0-9])" + self._token_re(tokens) + r"[\s,.]*([A-Za-z/]+)(?![A-Za-z0-9])", cfold(text)):
            if written_form(match.group(1), forms):
                out.append(match.group(0))
        return out

    def names_exactly(self, text: str) -> bool:
        return bool(self.exact_name_matches(text)) or org_number_in(text, self.org)

    def brand_in(self, text: str) -> bool:
        return self.brand_prefix_in(text)

    def other_entities_named(self, text: str) -> list[str]:
        """Legal entities written as the target's brand (+ up to two words) + a legal form the target does not carry
        ("Brand Oyj", "Brand AB", "Brand Technologies Oy")."""
        tokens = self.brand_tokens
        if not tokens:
            return []
        allowed = set(ENTITY_FORMS) - self.own_forms
        names = set()
        forms = "|".join(re.escape(f) for f in sorted(allowed, key=len, reverse=True))
        pattern = (r"(?<![A-Za-z0-9])" + self._token_re(tokens) + r"((?:[\s\-]+[A-Za-z0-9]+){0,2}?)[\s,]+((?i:" + forms + r"))(?![A-Za-z0-9/])")
        for match in re.finditer(pattern, cfold(text)):
            if written_form(match.group(2), allowed):
                names.add(" ".join(match.group(0).split()))
        return sorted(names)

    def brand_prefix_in(self, text: str) -> bool:
        """The full legal-name phrase, or a leading prefix of it of ≥4 letters ("Nordlys Gård" for STIFTELSEN NORDLYS GÅRD
        KURSSENTER), occurs: brand evidence only."""
        if self.legal.phrase_in(text):
            return True
        tokens = self.brand_tokens
        folded = fold(text)
        for k in range(len(tokens) - 1, 0, -1):
            prefix = tokens[:k]
            if len("".join(prefix)) >= 4 and "".join(prefix) in self.legal.brands:
                if re.search(r"(?<![a-z0-9])" + r"[\s\-_.&/]*".join(re.escape(t) for t in prefix) + r"(?![a-z0-9])", folded):
                    return True
        return False

    def group_members_share_brand(self) -> list[str]:
        """Other registry group members whose legal name begins with this company's first distinctive brand token."""
        first = self.brand_tokens[:1]
        if not first or len(first[0]) < 4:
            return []
        out = []
        for member in (*self.parents, *self.group_members):
            name = member.get("name") or ""
            if name and fold(name) != fold(self.legal_name) and LegalName(name).tokens[:1] == first:
                out.append(name)
        return out

    def group_names_in(self, text: str) -> list[str]:
        """Registry group members (parent, sister, subsidiary) whose full legal name occurs in `text`."""
        out = []
        folded = fold(text)
        for member in (*self.parents, *self.group_members):
            name = fold(member.get("name") or "")
            if name and name != fold(self.legal_name) and len(name) >= 5 and name in folded:
                out.append(member.get("name"))
        return out


def _form_of(name: str) -> str:
    words = re.findall(r"[a-z/]+", fold(name))
    return words[-1] if words else ""


def target_from_envelope(envelope: dict[str, Any]) -> TargetIdentity:
    """Registry facts only (Enhetsregisteret record and konsernstruktur), as captured in a V3.1 envelope."""
    claims = {c["field"]: c for c in envelope.get("claims", []) if c.get("availability") == "available"}
    identity = envelope.get("identity") or {}
    address = (claims.get("business_address") or {}).get("value") or {}
    org = envelope["organisation_number"]
    parents, members = [], []
    group = (claims.get("group_structure") or {}).get("value") or {}
    if isinstance(group, dict) and group.get("organisasjonsnummer"):
        root = {"name": group.get("navn"), "org": group.get("organisasjonsnummer"),
                "foreign": (group.get("organisasjonsform") or {}).get("kode") in ("UTLA", "NUF") or _form_of(group.get("navn") or "") in FOREIGN_PARENT_FORMS}
        if root["org"] != org:
            parents.append(root)
        for child in group.get("children") or []:
            if child.get("organisasjonsnummer") == org:
                if child.get("parentOrganisasjonsnummer") and child.get("parentOrganisasjonsnummer") != root["org"]:
                    parents.append({"name": child.get("parentNavn"), "org": child.get("parentOrganisasjonsnummer"),
                                    "foreign": _form_of(child.get("parentNavn") or "") in FOREIGN_PARENT_FORMS})
                continue
            members.append({"name": child.get("navn"), "org": child.get("organisasjonsnummer"),
                            "relation": "subsidiary" if child.get("parentOrganisasjonsnummer") == org else "group_member"})
    return TargetIdentity(org=org, legal_name=identity.get("legal_name") or (claims.get("legal_name") or {}).get("value") or "",
                          legal_form=identity.get("legal_form"), street=(address.get("lines") or [None])[0],
                          postal_code=address.get("postal_code"), municipality=address.get("municipality"),
                          parents=tuple(parents), group_members=tuple(members[:40]),
                          registry_website=(claims.get("registry_listed_website") or {}).get("value"))


@dataclass
class SiteIdentity:
    status: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    operator_note: str = ""

    @property
    def requires_exact_item_relevance(self) -> bool:
        return self.status in ("group_site", "other_entity")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "evidence": self.evidence, "operator_note": self.operator_note}


def _norwegian_domain(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host.endswith(".no")


def assess_site(target: TargetIdentity, site_url: str, homepage_text: str) -> SiteIdentity:
    text = homepage_text or ""
    evidence: list[dict[str, Any]] = []
    if org_number_in(text, target.org):
        evidence.append({"signal": "target_org_number_on_site"})
    exact = target.exact_name_matches(text)
    if exact:
        evidence.append({"signal": "exact_legal_name_with_form_on_site", "match": exact[0][:80]})
    if target.street and target.postal_code and fold(target.street) in fold(text) and target.postal_code in text:
        evidence.append({"signal": "registered_business_address_on_site"})
    label = (urllib.parse.urlsplit(site_url).hostname or "").removeprefix("www.").split(".")[0]
    legal = target.legal
    # A unit whose legal name is a brand plus a place/region qualifier ("BRAND ØST", "BRAND TROMSØ AS") on the
    # bare brand's domain: a network's site lists its units' addresses, so an address alone does not show who runs it.
    network_domain = bool(legal.qualifiers) and any(compact_label == brand for brand in legal.brands for compact_label in [re.sub(r"[^a-z0-9]", "", fold(label))])
    strong = [e for e in evidence if e["signal"] != "registered_business_address_on_site"] if network_domain else evidence
    if strong:
        return SiteIdentity("target_operated", evidence, "The site states the target's own legal identity.")
    if network_domain:
        return SiteIdentity("group_site", evidence + [{"signal": "unit_of_brand_network_on_brand_domain", "qualifiers": legal.qualifiers, "domain_label": label}],
                            "The target is a regional/local unit (brand + place) on the bare brand's domain, which does not state the "
                            "unit's organisation number or legal name: the site is the network's, so items must name the unit.")
    others = target.other_entities_named(text)
    numbers = other_org_numbers(text, target.org)
    if others or numbers:
        ev = [{"signal": "other_legal_entity_under_brand_on_site", "names": others}] if others else []
        ev += [{"signal": "other_org_number_on_site", "numbers": numbers}] if numbers else []
        return SiteIdentity("other_entity", ev, "The site states another legal entity's identity and not the target's.")
    brand = target.brand_prefix_in(text) or (bool(label) and target.legal.domain_named(label))
    foreign_parent = any(p.get("foreign") for p in target.parents)
    sharing = target.group_members_share_brand()
    if brand and target.parents and (foreign_parent or not _norwegian_domain(site_url) or sharing):
        return SiteIdentity("group_site", [{"signal": "brand_only_site_of_group_member",
                                            "parents": [p.get("name") for p in target.parents], "foreign_parent": foreign_parent,
                                            "norwegian_domain": _norwegian_domain(site_url), "group_members_sharing_brand": sharing[:5]}],
                            "Only the brand appears and the target belongs to a registry group (foreign parent, non-Norwegian domain, "
                            "or other group companies carrying the same brand): the site is presumed the group's, so brand mentions "
                            "refer to the group, not to the target.")
    if brand:
        return SiteIdentity("brand_only", [{"signal": "brand_only_no_group_signal"}], "Only the brand appears; no group signal (presumed own).")
    return SiteIdentity("unresolved", [{"signal": "no_identity_evidence_on_site"}], "Neither the legal identity nor the brand appears.")


@dataclass
class ItemIdentity:
    decision: str            # pass | withhold
    code: str
    names_target_exactly: bool
    other_entities: list[str]
    group_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def assess_item(target: TargetIdentity, site: SiteIdentity, text: str) -> ItemIdentity:
    """Hard identity gate for one item. `text` = title + captured source text + item page text."""
    exact = target.names_exactly(text)
    others = target.other_entities_named(text)
    groups = target.group_names_in(text)
    if others and not exact:
        return ItemIdentity("withhold", "item_names_other_legal_entity_under_brand", exact, others, groups)
    if site.status == "unresolved":
        return ItemIdentity("withhold", "site_identity_unresolved", exact, others, groups)
    if site.requires_exact_item_relevance and not exact:
        return ItemIdentity("withhold", f"{site.status}_item_does_not_name_exact_target", exact, others, groups)
    return ItemIdentity("pass", "exact_target_named" if exact else f"{site.status}_site", exact, others, groups)
