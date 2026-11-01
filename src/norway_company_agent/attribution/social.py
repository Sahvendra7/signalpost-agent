"""Is a profile linked from the verified website the company's own (design §B4)?

Being linked from the site is necessary, never sufficient. The handle must name this company; a brand or an extended
name is accepted only with corroboration that the site itself is the company's and named after it. A sister company,
parent, group, platform or unrelated account is held as "not attributed", with the reason.
"""
from __future__ import annotations

from .decision import Decision
from .names import Relation

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
