"""Manual audit kit (V3 design §B9): turn published claims into auditable units, sample them blind to the code version
that produced them, and score human (or clearly labelled assistant) verdicts into per-category precision with Wilson
95% intervals, plus retention of correct baseline items.

Nothing here decides whether a claim is correct. It only organises the evidence for a person and does arithmetic on
their verdicts. Rows without a verdict are never counted.
"""
from __future__ import annotations

import csv
import gzip
import html as html_lib
import io
import json
import math
import random
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

CATEGORIES = ("official_website", "social_profile", "news_item", "job_posting", "careers_page")
VERDICTS = ("correct", "incorrect", "unsure")
CSV_FIELDS = ("uid", "org", "company", "category", "value", "source_url", "claim_span", "retrieved_at", "snapshot_path", "registry_url",
              "verdict", "note", "draft_verdict", "draft_by")


def _fold(text: Any) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"\s+", " ", folded).strip()


def _url_key(url: Any) -> str:
    text = str(url or "").strip().split("#")[0]
    text = re.sub(r"^https?://(www\.)?", "", text, flags=re.I).rstrip("/")
    return text.casefold()


def unit_key(claim: dict[str, Any]) -> str | None:
    """The identity of one published fact, stable across code versions (used to align arms)."""
    field, value = claim.get("field"), claim.get("value")
    if field == "official_website" or field == "careers_page":
        return _url_key(value)
    if field == "social_profile":
        return _url_key(claim.get("canonical_url") or value)
    if field == "news_item" and isinstance(value, dict):
        return _url_key(value.get("url")) + "|" + str(value.get("publication_date") or "")[:10] if value.get("url") else f"{str(value.get('publication_date') or '')[:10]}|{_fold(value.get('title'))}"
    if field == "job_posting" and isinstance(value, dict):
        return f"{_fold(value.get('title'))}|{_url_key(value.get('url'))}"
    return None


def _company(envelope: dict[str, Any]) -> str:
    identity = envelope.get("identity") or {}
    return str(identity.get("legal_name") or identity.get("name") or "")


def _value_text(claim: dict[str, Any]) -> str:
    value = claim.get("value")
    if isinstance(value, dict):
        parts = [value.get("title"), value.get("publication_date") or value.get("date_posted"), value.get("url")]
        if value.get("application_deadline") or value.get("valid_through"):
            parts.append("deadline " + str(value.get("application_deadline") or value.get("valid_through")))
        return " | ".join(str(part) for part in parts if part)
    return str(value or "")


def units(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """One auditable unit per available claim in the audited categories."""
    evidence = {item.get("id"): item for item in envelope.get("evidence") or []}
    org = str(envelope.get("organisation_number") or "")
    out = []
    for claim in envelope.get("claims") or []:
        if claim.get("availability") != "available" or claim.get("field") not in CATEGORIES:
            continue
        key = unit_key(claim)
        if key is None:
            continue
        cited = evidence.get((claim.get("evidence_ids") or [None])[0]) or {}
        out.append({
            "uid": f"{org}|{claim['field']}|{key}", "org": org, "company": _company(envelope), "category": claim["field"],
            "value": _value_text(claim), "source_url": cited.get("source_url") or "", "claim_span": str(cited.get("claim_span") or "")[:300],
            "retrieved_at": cited.get("retrieved_at") or "", "snapshot_path": cited.get("snapshot_path") or "",
            "registry_url": f"https://data.brreg.no/enhetsregisteret/oppslag/enheter/{org}",
            "basis": ((claim.get("attribution") or {}).get("basis") or claim.get("identity_basis") or claim.get("method") or ""),
        })
    return out


def read_envelopes(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def arm_units(envelopes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        for unit in units(envelope):
            found.setdefault(unit["uid"], unit)
    return found


def align(arms: dict[str, Iterable[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Union of units over named arms, and uid -> arms that published it."""
    by_arm = {name: arm_units(envelopes) for name, envelopes in arms.items()}
    union: dict[str, dict[str, Any]] = {}
    present: dict[str, list[str]] = {}
    for name, found in by_arm.items():
        for uid, unit in found.items():
            union.setdefault(uid, unit)
            present.setdefault(uid, []).append(name)
    return list(union.values()), present


def sample(units_list: list[dict[str, Any]], present: dict[str, list[str]], *, per_stratum: int | None, seed: int) -> list[dict[str, Any]]:
    """Every unit published by only some arms, plus up to `per_stratum` units published by all arms per category
    (all of them when `per_stratum` is None). Shuffled with `seed`; the arm is never part of the row."""
    arms = {name for names in present.values() for name in names}
    rng = random.Random(seed)
    changed = [unit for unit in units_list if set(present[unit["uid"]]) != arms]
    unchanged = [unit for unit in units_list if set(present[unit["uid"]]) == arms]
    chosen = list(changed)
    for category in CATEGORIES:
        pool = sorted((unit for unit in unchanged if unit["category"] == category), key=lambda unit: unit["uid"])
        rng.shuffle(pool)
        chosen.extend(pool if per_stratum is None else pool[:per_stratum])
    rng.shuffle(chosen)
    return [{field: unit.get(field, "") for field in CSV_FIELDS} for unit in chosen]


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def score(labels: list[dict[str, str]], present: dict[str, list[str]], *, baseline: str | None, candidate: str | None,
          labeller: str, labeller_kind: str) -> dict[str, Any]:
    """Precision per arm and category; retention of correct baseline units by the candidate; gained and lost units."""
    if labeller_kind not in ("owner", "assistant_blind", "other_person"):
        raise ValueError("labeller_kind must be owner, assistant_blind or other_person")
    labelled = [row for row in labels if row.get("verdict") in VERDICTS]
    skipped = len(labels) - len(labelled)
    arms = sorted({name for names in present.values() for name in names})
    result: dict[str, Any] = {"labeller": labeller, "labeller_kind": labeller_kind, "units_labelled": len(labelled), "units_without_verdict": skipped,
                              "draft_agreement": sum(1 for row in labelled if row.get("draft_verdict") and row["draft_verdict"] == row["verdict"]),
                              "arms": {}, "retention": {}, "note": "Local engineering measurement; not an official Builderr score."}
    for arm in arms:
        per = {}
        for category in CATEGORIES:
            rows = [row for row in labelled if row["category"] == category and arm in present.get(row["uid"], [])]
            correct = sum(row["verdict"] == "correct" for row in rows)
            incorrect = sum(row["verdict"] == "incorrect" for row in rows)
            unsure = sum(row["verdict"] == "unsure" for row in rows)
            decided = correct + incorrect
            interval = wilson(correct, decided)
            per[category] = {"published_labelled": len(rows), "correct": correct, "incorrect": incorrect, "unsure": unsure,
                             "precision": round(correct / decided, 4) if decided else None,
                             "ci95": [round(interval[0], 4), round(interval[1], 4)] if interval else None}
        result["arms"][arm] = per
    if baseline and candidate:
        for category in CATEGORIES:
            base_correct = [row for row in labelled if row["category"] == category and row["verdict"] == "correct" and baseline in present.get(row["uid"], [])]
            kept = [row for row in base_correct if candidate in present.get(row["uid"], [])]
            lost = [row for row in base_correct if candidate not in present.get(row["uid"], [])]
            gained = [row for row in labelled if row["category"] == category and row["verdict"] == "correct" and candidate in present.get(row["uid"], []) and baseline not in present.get(row["uid"], [])]
            removed_errors = [row for row in labelled if row["category"] == category and row["verdict"] == "incorrect" and baseline in present.get(row["uid"], []) and candidate not in present.get(row["uid"], [])]
            new_errors = [row for row in labelled if row["category"] == category and row["verdict"] == "incorrect" and candidate in present.get(row["uid"], []) and baseline not in present.get(row["uid"], [])]
            result["retention"][category] = {
                "baseline_correct": len(base_correct), "retained": len(kept), "retention": round(len(kept) / len(base_correct), 4) if base_correct else None,
                "lost_correct": [row["uid"] for row in lost], "gained_correct": [row["uid"] for row in gained],
                "errors_removed": len(removed_errors), "errors_introduced": [row["uid"] for row in new_errors],
            }
    return result


def render_checklist(rows: list[dict[str, Any]], *, title: str = "Signalpost audit checklist") -> str:
    """A self-contained page: one card per unit, verdict buttons, and a download of the labelled CSV. No network, no
    innerHTML: the data is embedded as JSON and rendered with textContent."""
    payload = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    fields = json.dumps(list(CSV_FIELDS))
    return CHECKLIST.replace("__TITLE__", html_lib.escape(title)).replace("__DATA__", payload).replace("__FIELDS__", fields)


def results_markdown(result: dict[str, Any]) -> str:
    out = io.StringIO()
    out.write(f"Labeller: {result['labeller']} ({result['labeller_kind']}); units labelled: {result['units_labelled']}; without verdict: {result['units_without_verdict']}.\n\n")
    out.write(result["note"] + "\n\n")
    for arm, per in result["arms"].items():
        out.write(f"### {arm}\n\n| Category | Labelled | Correct | Incorrect | Unsure | Precision | 95% CI |\n|---|---|---|---|---|---|---|\n")
        for category, row in per.items():
            precision = f"{row['precision']:.1%}" if row["precision"] is not None else "—"
            ci = f"{row['ci95'][0]:.1%}–{row['ci95'][1]:.1%}" if row["ci95"] else "—"
            out.write(f"| {category} | {row['published_labelled']} | {row['correct']} | {row['incorrect']} | {row['unsure']} | {precision} | {ci} |\n")
        out.write("\n")
    if result.get("retention"):
        out.write("### Retention of correct baseline units\n\n| Category | Baseline correct | Retained | Retention | Errors removed | Errors introduced |\n|---|---|---|---|---|---|\n")
        for category, row in result["retention"].items():
            retention = f"{row['retention']:.1%}" if row["retention"] is not None else "—"
            out.write(f"| {category} | {row['baseline_correct']} | {row['retained']} | {retention} | {row['errors_removed']} | {len(row['errors_introduced'])} |\n")
    return out.getvalue()


CHECKLIST = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<meta name="referrer" content="no-referrer"><title>__TITLE__</title>
<style>
body{font:15px/1.45 system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1b1f24}header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
main{max-width:900px;margin:0 auto;padding:12px 16px}.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0}.card.done{border-color:#7a7}
.k{color:#555;font-size:13px}.v{font-weight:600;word-break:break-word}.btns{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #888;background:#fff}
button[aria-pressed=true]{background:#1b5;color:#fff;border-color:#1b5}input{font:inherit;width:100%;box-sizing:border-box;margin-top:6px;padding:6px}a{color:#0645ad;word-break:break-all}
</style></head><body><header><strong>__TITLE__</strong><span id="count"></span><button id="dl" type="button">Download labelled CSV</button></header><main id="list"></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const rows = JSON.parse(document.getElementById("data").textContent); const FIELDS = __FIELDS__;
function el(tag, attrs, ...kids){const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs||{}))if(v!=null)n.setAttribute(k,v);for(const kid of kids)if(kid!=null)n.append(kid);return n;}
function link(url){return /^https?:\\/\\//.test(url)?el("a",{href:url,rel:"noopener noreferrer",target:"_blank"},url):document.createTextNode(url||"—");}
function count(){document.getElementById("count").textContent=rows.filter(r=>r.verdict).length+" of "+rows.length+" labelled";}
const list=document.getElementById("list");
rows.forEach((r,i)=>{const card=el("section",{class:"card"+(r.verdict?" done":"")});
 card.append(el("div",{class:"k"},(i+1)+". "+r.category+" · "+r.company+" ("+r.org+")"),el("div",{class:"v"},r.value),
  el("div",{class:"k"},"Source: "),link(r.source_url),el("div",{class:"k"},"Claim span: "+(r.claim_span||"—")),el("div",{class:"k"},"Retrieved: "+(r.retrieved_at||"—")+(r.snapshot_path?" · captured copy: "+r.snapshot_path:"")),
  el("div",{class:"k"},"Registry: "),link(r.registry_url));
 const btns=el("div",{class:"btns"});for(const v of ["correct","incorrect","unsure"]){const b=el("button",{type:"button","aria-pressed":String(r.verdict===v)},v);
  b.addEventListener("click",()=>{r.verdict=v;card.classList.add("done");btns.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));count();});btns.append(b);}
 const note=el("input",{type:"text",placeholder:"Note (why)","aria-label":"Note"});note.value=r.note||"";note.addEventListener("input",()=>{r.note=note.value;});
 card.append(btns,note);list.append(card);});
count();
function q(s){s=String(s==null?"":s);return /[",\\n\\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
document.getElementById("dl").addEventListener("click",()=>{const text=[FIELDS.join(",")].concat(rows.map(r=>FIELDS.map(f=>q(r[f])).join(","))).join("\\r\\n");
 const a=el("a",{href:URL.createObjectURL(new Blob([text],{type:"text/csv"})),download:"items.labelled.csv"});document.body.append(a);a.click();a.remove();});
</script></body></html>
"""
