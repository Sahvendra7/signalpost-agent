"""Blind labelling aid for an audit_kit sample: for every unit print what the captured bytes say about it.

    python label_aid.py ITEMS.csv BASE_PROFILES.jsonl BASE_SNAPSHOTS OUT.md

Only the captured evidence is shown (registry name, source page, claim span, and for news items the matching feed
entry or listing card text plus the item's own page if it was captured). Nothing from any code version's claim
metadata (attribution codes, reasons) is shown, so the label cannot depend on which version published the unit.
"""
import csv, gzip, json, re, sys
from pathlib import Path
sys.path.insert(0, "/home/user/signalpost-agent/src")
from bs4 import BeautifulSoup
from norway_company_agent.replay import entries_from_profile

items, profiles_path, snaps, out = sys.argv[1:5]
profiles = {}
for line in open(profiles_path, encoding="utf-8").read().split("\n"):
    if line.strip():
        p = json.loads(line); profiles[p["organisation_number"]] = p
entries = {org: entries_from_profile(p, Path(snaps)) for org, p in profiles.items()}


def raw(org, url):
    e = entries.get(org, {}).get(url)
    if not e or not e.get("path"):
        return None
    return Path(e["path"]).read_bytes()


def norm(url):
    url = re.sub(r"[?&]utm_[^&]*", "", (url or "").split("#")[0])
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/?").rstrip("/").lower()


def text_of(b):
    soup = BeautifulSoup(b, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return " ".join(main.get_text(" ", strip=True).split())


def news_context(org, value, source):
    bits = [b.strip() for b in value.split(" | ")]
    url = bits[-1] if bits and bits[-1].startswith("http") else None
    title = " | ".join(bits[:-2]) if len(bits) >= 3 else (bits[0] if bits else "")
    v = {"url": url, "title": title, "date": bits[-2] if len(bits) >= 2 else None}
    parts = [f"title: {title}", f"date: {v.get('date')}  url: {url}"]
    b = raw(org, source)
    if b:
        if b.lstrip()[:200].lower().find(b"<rss") >= 0 or b.lstrip().startswith(b"<?xml"):
            soup = BeautifulSoup(b, "xml")
            for node in soup.find_all(["item", "entry"]):
                link = node.find("link")
                href = (link.get("href") or link.get_text(strip=True)) if link else ""
                if norm(href) == norm(url):
                    body = node.find(["encoded", "content"]) or node.find(["description", "summary"])
                    cats = [c.get_text(strip=True) for c in node.find_all("category")]
                    txt = " ".join(BeautifulSoup(body.get_text(" ", strip=True), "lxml").get_text(" ", strip=True).split()) if body else ""
                    parts.append(f"feed entry (categories {cats}): {txt[:1800]}")
                    break
        else:
            soup = BeautifulSoup(b, "lxml")
            card = None
            for a in soup.find_all("a", href=True):
                href = a["href"] if a["href"].startswith("http") else re.sub(r"^(https?://[^/]+).*", r"\1", source) + "/" + a["href"].lstrip("/")
                if norm(href) == norm(url):
                    card = a
                    for _ in range(4):
                        if card.parent is not None and len(card.parent.get_text(" ", strip=True)) < 900:
                            card = card.parent
                    break
            if card is None and title:
                h = soup.find(lambda t: t.name in ("h1", "h2", "h3", "h4") and title[:30] in t.get_text(" ", strip=True))
                card = h.parent if h is not None else None
            if card is not None:
                parts.append("listing card: " + " ".join(card.get_text(" ", strip=True).split())[:900])
    own = raw(org, url) if url and norm(url) != norm(source) else None
    if own:
        parts.append("article page: " + text_of(own)[:2200])
    elif norm(url) == norm(source) and b:
        parts.append("article page (source): " + text_of(b)[:2200])
    else:
        parts.append("article page: not captured")
    return parts


rows = list(csv.DictReader(open(items, encoding="utf-8")))
CAP = 600
with open(out, "w", encoding="utf-8") as f:
    for n, r in enumerate(rows, 1):
        org = r["org"]
        if r["category"] == "news_item":
            parts = news_context(org, r["value"], r["source_url"])
            texts = [p for p in parts[2:] if not p.endswith("not captured")]
            best = next((p for p in texts if p.startswith("feed entry")), None) or next((p for p in texts if p.startswith("article page")), None) or (texts[0] if texts else "NO TEXT")
            f.write(f"{n}. [news] {r['company']} ({org}) | {r['value'][:230]} | src {r['source_url'][:70]}\n   {best[:CAP]}\n")
        else:
            f.write(f"{n}. [{r['category']}] {r['company']} ({org}) | {r['value']} | src {r['source_url']} | {r['claim_span'][:160]}\n")
print(len(rows), "units ->", out)
