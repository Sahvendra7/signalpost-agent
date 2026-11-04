"""Datasets for the V3.2 experiments: labelled candidate items and the evidence packets built from them.

Labels (verdict, note) are kept in the item rows and are NEVER placed in a packet: `news_contract.build_packet` takes
only identity, relationships, website evidence, the item metadata and captured text.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
from pathlib import Path
from typing import Any

from .capture import CaptureStore, article_text, feed_or_card_text, norm_url
from .news_contract import build_packet


def read_envelopes(path: Path) -> dict[str, dict[str, Any]]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return {row["organisation_number"]: row for row in (json.loads(line) for line in handle if line.strip())}


def claim(envelope: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((c for c in envelope.get("claims", []) if c["field"] == name), None)


def org_context(envelope: dict[str, Any]) -> dict[str, Any]:
    identity = envelope.get("identity") or {}
    org = envelope["organisation_number"]
    industry = (claim(envelope, "industry") or {}).get("value") or {}
    site = claim(envelope, "official_website") or {}
    evidence = {e["id"]: e for e in envelope.get("evidence", [])}
    operator = None
    if site.get("availability") == "available":
        spans = [evidence[i].get("claim_span") for i in site.get("evidence_ids", []) if i in evidence]
        operator = "; ".join(s for s in spans if s)[:600] or site.get("method")
    relationships: list[dict[str, Any]] = []
    group = (claim(envelope, "group_structure") or {}).get("value") or {}
    if isinstance(group, dict) and group.get("organisasjonsnummer"):
        root_org = group.get("organisasjonsnummer")
        if root_org != org:
            relationships.append({"relation": "parent_company", "name": group.get("navn"), "organisation_number": root_org})
        for child in group.get("children") or []:
            if child.get("organisasjonsnummer") == org:
                if child.get("parentOrganisasjonsnummer") and child.get("parentOrganisasjonsnummer") != root_org:
                    relationships.append({"relation": "parent_company", "name": child.get("parentNavn"), "organisation_number": child.get("parentOrganisasjonsnummer")})
                continue
            parent = child.get("parentOrganisasjonsnummer")
            relation = "subsidiary" if parent == org else ("sister_company" if parent and any(
                c.get("organisasjonsnummer") == org and c.get("parentOrganisasjonsnummer") == parent for c in group.get("children") or []) else "other_group_entity")
            relationships.append({"relation": relation, "name": child.get("navn"), "organisation_number": child.get("organisasjonsnummer")})
    manager = claim(envelope, "business_manager") or {}
    if manager.get("availability") == "available" and isinstance(manager.get("value"), dict):
        value = manager["value"]
        relationships.append({"relation": "business_manager", "name": (value.get("name") or [None])[0], "organisation_number": value.get("organisation_number")})
    return {"org": org, "legal_name": identity.get("legal_name") or (claim(envelope, "legal_name") or {}).get("value") or "",
            "legal_form": identity.get("legal_form"), "industry": industry.get("description") if isinstance(industry, dict) else None,
            "site_url": site.get("value") if site.get("availability") == "available" else None, "operator_assessment": operator,
            "relationships": relationships[:25]}


def news_claims(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in envelope.get("claims", []) if c["field"] == "news_item" and c.get("availability") == "available" and isinstance(c.get("value"), dict)]


def item_key(org: str, value: dict[str, Any]) -> str:
    return f"{org}|{norm_url(value.get('url'))}|{str(value.get('publication_date') or '')[:10]}|{(value.get('title') or '').strip().casefold()[:80]}"


def parse_value(value: str) -> dict[str, Any]:
    bits = [b.strip() for b in value.split(" | ")]
    url = bits[-1] if bits and bits[-1].startswith("http") else None
    return {"title": " | ".join(bits[:-2]) if len(bits) >= 3 else (bits[0] if bits else ""), "date": bits[-2][:10] if len(bits) >= 2 else None, "url": url}


def aid_texts(path: Path) -> dict[tuple[str, str], str]:
    """Excerpts from a label aid, keyed by (org, value prefix) taken from each entry's own header.

    The aid numbers only the units it lists (it skips official_website rows), so its numbers are NOT row positions in
    items.labelled.csv: an excerpt is attached by what its header says, never by position (regression, 2026-11-04)."""
    out: dict[tuple[str, str], str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^\d+\. \[news\] .*? \((\d+)\) \| (.*) \| src ", line)
        if match and i + 1 < len(lines) and lines[i + 1].startswith("   "):
            key = (match.group(1), match.group(2)[:200])
            if key in out:
                raise ValueError(f"ambiguous aid header for {key}")
            out[key] = lines[i + 1].strip()
    return out


def section_of(url: str | None) -> str | None:
    path = re.sub(r"^https?://[^/]+", "", url or "").strip("/")
    return path.split("/")[0] if "/" in path else (None if not path else "(root)")


def labelled_news_items(audit_dir: Path, base_envelopes: dict[str, dict[str, Any]], dataset: str) -> list[dict[str, Any]]:
    """Every labelled news unit of an audit (census of all arms), with its base-arm claim metadata and label."""
    rows = list(csv.DictReader(open(audit_dir / "items.labelled.csv", encoding="utf-8")))
    arms = json.loads((audit_dir / "arms.json").read_text(encoding="utf-8")) if (audit_dir / "arms.json").exists() else {}
    aids = aid_texts(audit_dir / "aid.md") if (audit_dir / "aid.md").exists() else {}
    items = []
    for row in rows:
        if row["category"] != "news_item":
            continue
        parsed = parse_value(row["value"])
        env = base_envelopes.get(row["org"]) or {}
        match = None
        for c in news_claims(env):
            v = c["value"]
            if norm_url(v.get("url")) == norm_url(parsed["url"]) and str(v.get("publication_date") or "")[:10] == parsed["date"] and \
                    (v.get("title") or "").strip()[:60] == parsed["title"].strip()[:60]:
                match = c
                break
        v = (match or {}).get("value") or {}
        aid = aids.get((row["org"], row["value"][:230][:200])) if aids else None
        if aids and aid is None:
            raise ValueError(f"no aid excerpt for {row['uid']}")
        kind = None
        if aid:
            kind = "feed_entry" if aid.startswith("feed entry") else "listing_card" if aid.startswith("listing card") else "article_page_excerpt" if aid.startswith("article page") else "other"
            aid = re.sub(r"^(feed entry|listing card|article page \(source\)|article page)( \(categories [^)]*\))?:\s*", lambda m: (f"[feed categories: {m.group(2)[13:-1]}] " if m.group(2) else ""), aid)
        items.append({"dataset": dataset, "item_id": row["uid"], "org": row["org"], "company": row["company"], "title": parsed["title"],
                      "url": parsed["url"], "date": parsed["date"], "source_url": row["source_url"], "method": (match or {}).get("method"),
                      "date_text": v.get("date_text"), "summary": v.get("summary"), "arms": arms.get(row["uid"], []),
                      "source_text_aid": aid, "source_text_kind": kind, "label": row["verdict"] or None, "label_note": row["note"]})
    return items


def packet_for(item: dict[str, Any], ctx: dict[str, Any], store: CaptureStore, source_raw: bytes | None = None, article_cap: int = 6000) -> dict[str, Any]:
    source_text, kind = item.get("source_text_aid"), item.get("source_text_kind")
    if source_raw is not None:
        source_text, kind = feed_or_card_text(source_raw, item["source_url"], item["url"] or "", item["title"])
    if not source_text and item.get("summary"):
        source_text, kind = item["summary"], "pipeline_summary"
    art, prov = (None, {"captured": False, "reason": "item_url_is_source_page"})
    if item.get("url") and norm_url(item["url"]) != norm_url(item["source_url"]) and ctx.get("site_url"):
        art, prov = article_text(store, item["url"], ctx["site_url"], cap=article_cap)
    if kind == "article_page_excerpt" and art:
        source_text, kind = None, None  # the excerpt is a prefix of the article text now supplied in full
    return build_packet(item_id=item["item_id"], org=item["org"], legal_name=ctx["legal_name"], legal_form=ctx.get("legal_form"),
                        industry=ctx.get("industry"), site_url=ctx.get("site_url"), operator_assessment=ctx.get("operator_assessment"),
                        relationships=ctx.get("relationships") or [], title=item["title"], item_url=item.get("url"),
                        source_url=item.get("source_url"), section=section_of(item.get("url")), extraction_method=item.get("method"),
                        date_candidate=item.get("date"), date_text=item.get("date_text"), source_text=source_text,
                        source_text_kind=kind, article_text=art, article_provenance=prov)
