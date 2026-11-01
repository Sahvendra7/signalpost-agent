"""How a name, domain label or social-media handle relates to the target's legal name (design §B3). Pure string logic."""
from __future__ import annotations

import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from ..identity import _tokens

LEGAL_FORMS = {"as", "asa", "sa", "da", "ans", "enk", "nuf", "iks", "ba", "bbl", "brl", "sti", "ks", "fli", "ab", "gmbh", "ltd", "inc", "aps", "oy", "ag", "llc", "plc"}
# Words a handle may add to the legal name without naming another entity.
NEUTRAL = {"norge", "norway", "no", "nor", "norwegian", "official", "offisiell", "hq", "hovedkontor", "the", "www", "page", "side", "info"}
# Words that turn the legal name into another entity's name: a group, holding, other country or business line.
DISTINGUISHING = {"group", "gruppen", "gruppe", "konsern", "konsernet", "holding", "holdings", "global", "international", "intl", "invest",
                  "investment", "eiendom", "capital", "ventures", "company", "worldwide", "europe", "nordic", "nordics", "scandinavia",
                  "sverige", "sweden", "danmark", "denmark", "finland", "usa", "uk", "germany", "deutschland", "corporate", "corp"}
# Leading-name prefixes a handle may omit or keep ("stiftelsen-crux" for STIFTELSEN CRUX; tokens drop "stiftelsen").
PREFIXES = ("stiftelsen", "sameiet", "borettslaget", "the")
# Brand candidates that are too generic to identify a company on their own.
GENERIC_BRANDS = {"bygg", "eiendom", "service", "services", "holding", "invest", "drift", "norge", "norsk", "norske", "entreprenor", "transport",
                  "consulting", "group", "media", "design", "data", "regnskap", "handel", "utvikling", "prosjekt", "energi", "bil", "elektro",
                  "ror", "vvs", "maler", "tak", "anlegg", "betong", "tre", "hus", "hotell", "restaurant", "kafe", "butikk", "klinikk", "tannlege",
                  "advokat", "advokatfirma", "advokatfirmaet", "revisjon", "auto", "marine", "fisk", "sjomat", "landbruk", "gard", "skog", "bolig",
                  "eiendomsutvikling", "invest", "partner", "partners", "solutions", "system", "systems", "tech", "teknikk", "it", "net", "web"}
COUNTIES = {"agder", "innlandet", "moreogromsdal", "nordland", "oslo", "rogaland", "troms", "finnmark", "trondelag", "vestfold", "telemark",
            "vestland", "ostfold", "akershus", "buskerud", "viken", "hordaland", "sognogfjordane", "hedmark", "oppland", "vestagder", "austagder"}
REGIONS = {"nord", "sor", "ost", "vest", "midt", "sorvest", "nordvest", "sorost", "nordost", "nordnorge", "midtnorge", "sorlandet", "vestlandet", "ostlandet"}


def fold(text: Any) -> str:
    value = str(text or "").translate(str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE"}))
    return unicodedata.normalize("NFKD", urllib.parse.unquote(value)).encode("ascii", "ignore").decode().casefold()


def compact(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(text))


@dataclass
class LegalName:
    """The target's legal name in the forms attribution rules compare against."""

    name: str
    municipality: str | None = None
    post_town: str | None = None
    tokens: list[str] = field(init=False)
    compact: str = field(init=False)
    brands: list[str] = field(init=False)
    qualifiers: list[str] = field(init=False)
    places: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = _tokens(self.name)
        self.compact = "".join(self.tokens)
        self.places = {compact(place) for place in (self.municipality, self.post_town) if place}
        self.brands = []
        for k in range(1, len(self.tokens)):
            brand = "".join(self.tokens[:k])
            if len(brand) >= 4 and brand not in GENERIC_BRANDS:
                self.brands.append(brand)
        self.qualifiers = [token for token in self.tokens[1:] if token in self.places or token in COUNTIES or token in REGIONS]
        self.initials = "".join(token[0] for token in self.tokens) if len(self.tokens) >= 2 else ""
        first = fold(self.name).split()[:1]
        # "AS JACO", "AS SOLREGN": a leading legal form is part of how the company writes its name ("asjaco", "as-solregn")
        self.leading_form = first[0] if first and first[0] in LEGAL_FORMS else ""

    @classmethod
    def from_profile(cls, profile: dict[str, Any]) -> LegalName:
        live = ((profile.get("evidence") or {}).get("registry_live") or {}).get("value") or {}
        address = profile.get("business_address") or live.get("business_address") or {}
        return cls(str(profile.get("name") or live.get("name") or ""), address.get("kommune"), address.get("poststed"))

    @property
    def phrase_re(self) -> re.Pattern[str]:
        """The distinctive tokens in order and adjacent (separators and "og/and/&" allowed), on folded text."""
        if not self.tokens:
            return re.compile(r"(?!x)x")
        parts = [re.escape(token) for token in self.tokens]
        joiner = r"(?:[\s\-_.&/,]|og|and)*"
        return re.compile(r"(?<![a-z0-9])" + joiner.join(parts) + r"(?![a-z0-9])")

    def phrase_in(self, text: Any) -> bool:
        return bool(self.tokens) and bool(self.phrase_re.search(fold(text)))

    def strip_neutral(self, rest: str) -> str:
        """Remove leading neutral affixes, legal forms, the company's own places, short digit runs and an acronym of
        the name ("-ipr" for INSTITUTT FOR PSYKOLOGISK RÅDGIVNING) from `rest`."""
        words = sorted(NEUTRAL | LEGAL_FORMS | self.places, key=len, reverse=True)
        changed = True
        while rest and changed:
            changed = False
            if 2 <= len(rest) <= 5 and self.initials and _subsequence(rest, self.initials):
                return ""
            digits = re.match(r"\d{1,4}", rest)
            if digits:
                rest, changed = rest[digits.end():], True
                continue
            for word in words:
                if word and rest.startswith(word):
                    rest, changed = rest[len(word):], True
                    break
        return rest

    def domain_named(self, label: str) -> bool:
        """The domain label is the legal name, a brand of it, its initials, or one of these with neutral affixes."""
        label = compact(label)
        for base in [self.compact, *self.brands, self.initials]:
            if base and label.startswith(base) and not self.strip_neutral(label[len(base):]):
                return True
        return False

    def domain_related(self, label: str) -> bool:
        """The domain label shares at least one distinctive legal-name token (weaker than `domain_named`)."""
        label = compact(label)
        return any(len(token) >= 4 and token not in GENERIC_BRANDS and token in label for token in self.tokens) or self.domain_named(label)


def _subsequence(short: str, long: str) -> bool:
    letters = iter(long)
    return all(letter in letters for letter in short)


@dataclass(frozen=True)
class Relation:
    kind: str  # EXACT | EXACT_NEUTRAL | BRAND | EXTENDS | OTHER_ENTITY | UNRELATED
    handle: str
    rest: str = ""


def handle_of(platform: str, url: str) -> tuple[str, list[str]]:
    """(compact handle, separator-split words) from a profile URL."""
    path = urllib.parse.urlsplit(url).path
    segments = [segment for segment in path.split("/") if segment]
    raw = ""
    if platform == "linkedin":
        for marker in ("company", "school", "showcase"):
            if marker in segments and segments.index(marker) + 1 < len(segments):
                raw = segments[segments.index(marker) + 1]
                break
        else:
            raw = segments[-1] if segments else ""
    elif platform == "youtube":
        handle = next((segment for segment in segments if segment.startswith("@")), None)
        if handle:
            raw = handle[1:]
        elif len(segments) >= 2 and segments[0] in ("c", "user"):
            raw = segments[1]
        else:
            raw = ""  # channel ids carry no name
    elif platform == "facebook":
        if segments[:1] == ["pages"] and len(segments) >= 2:
            raw = segments[1]
        elif segments[:1] == ["pg"] and len(segments) >= 2:
            raw = segments[1]
        else:
            raw = segments[0] if segments else ""
        raw = re.sub(r"-\d{8,}$", "", raw)  # facebook.com/Name-As-359873177420058: the page id is not part of the name
    else:
        raw = segments[0] if segments else ""
    folded = fold(raw)
    words = [word for word in re.split(r"[^a-z0-9]+", folded) if word]
    if len(words) > 2:
        words = [word for word in words if word not in ("og", "and")]  # "hansen-og-sonn-as": connectors are not in legal tokens
    return "".join(words), words


def handle_relation(legal: LegalName, platform: str, url: str) -> Relation:
    handle, words = handle_of(platform, url)
    if not handle or not legal.compact:
        return Relation("UNRELATED", handle)
    # A handle spelling a legal name ("tyin-filefjell-as", "bdt-viken-revisjon-as"): the name before the legal form must
    # be this company's (optionally with neutral affixes); any other name is another registered or registrable entity.
    if len(words) >= 2 and words[-1] in LEGAL_FORMS:
        named = "".join(word for word in words[:-1] if word not in ("og", "and"))
        if legal.leading_form and words[0] == legal.leading_form and len(words) >= 3:
            named = "".join(word for word in words[1:-1] if word not in ("og", "and"))
        for prefix in PREFIXES:
            if named.startswith(prefix) and named != prefix and not legal.compact.startswith(prefix):
                named = named[len(prefix):]
        if not (named.startswith(legal.compact) and not legal.strip_neutral(named[len(legal.compact):])):
            return Relation("OTHER_ENTITY", handle, named)
    prefixes = PREFIXES + ((legal.leading_form,) if legal.leading_form else ())
    candidates = [handle] + [handle[len(prefix):] for prefix in prefixes if handle.startswith(prefix) and len(handle) > len(prefix)]
    best: Relation | None = None
    for candidate in candidates:
        relation = _relation(legal, candidate)
        if best is None or _RANK[relation.kind] < _RANK[best.kind]:
            best = relation
    return best or Relation("UNRELATED", handle)


_RANK = {"EXACT": 0, "EXACT_NEUTRAL": 1, "BRAND": 2, "OTHER_ENTITY": 3, "EXTENDS": 4, "UNRELATED": 5}


def _relation(legal: LegalName, handle: str) -> Relation:
    for base, exact_kind in [(legal.compact, "EXACT")] + [(brand, "BRAND") for brand in sorted(legal.brands, key=len, reverse=True)]:
        if not handle.startswith(base):
            continue
        rest = handle[len(base):]
        if not rest or (exact_kind == "EXACT" and rest in LEGAL_FORMS):
            return Relation(exact_kind, handle, rest)
        remaining = legal.strip_neutral(rest)
        if not remaining:
            return Relation("EXACT_NEUTRAL" if exact_kind == "EXACT" else "BRAND", handle, rest)
        if any(remaining.startswith(word) for word in DISTINGUISHING) or any(word in remaining for word in DISTINGUISHING if len(word) >= 5):
            return Relation("OTHER_ENTITY", handle, remaining)
        return Relation("EXTENDS", handle, remaining)
    return Relation("UNRELATED", handle)
