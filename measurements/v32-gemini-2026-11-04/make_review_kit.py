"""Second-person review kit: a stratified random fraction of a labelled set, blind (no label, no arm, no model output).

    uv run python measurements/v32-gemini-2026-11-04/make_review_kit.py SET [FRACTION=0.25] [SEED=20261106]
Writes audits/SET/review_kit/{sheet.md, form.csv, adjudication.csv, README.md, sample_ids.txt}. Stratified by
company: each company contributes round(FRACTION x its units) units, at least 1.
"""
import csv, gzip, json, random, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
name = sys.argv[1]
fraction = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20261106
packets = [json.loads(l) for l in gzip.open(HERE / f"datasets/{name}.packets.jsonl.gz", "rt", encoding="utf-8")]
by_org = defaultdict(list)
for n, p in enumerate(packets, 1):
    by_org[p["target_company"]["organisation_number"]].append((n, p))
rng = random.Random(seed)
chosen = []
for org in sorted(by_org):
    units = by_org[org]
    k = max(1, round(fraction * len(units)))
    chosen += rng.sample(units, min(k, len(units)))
chosen.sort(key=lambda x: x[0])
out = HERE / f"audits/{name}/review_kit"
out.mkdir(parents=True, exist_ok=True)
with (out / "sheet.md").open("w", encoding="utf-8") as fh:
    for n, p in chosen:
        tc = p["target_company"]
        rel = "; ".join(f"{r['relation']}: {r['name']}" for r in tc["known_relationships"][:4])
        fh.write(f"## {n}. {tc['legal_name']} ({tc['organisation_number']}) — site {p['website']['url']}{' | ' + rel if rel else ''}\n"
                 f"title: {p['item']['title']}\ndate: {p['item']['pipeline_date_candidate']} ({p['item']['extraction_method']}; "
                 f"'{p['item']['pipeline_date_text']}')  url: {p['item']['url']}\n"
                 f"source[{p['source_text_kind']}]: {(p['source_text'] or '-')[:900]}\n\narticle: {(p['article_text'] or '-')[:2200]}\n\n")
with (out / "form.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["n", "item_id", "label (correct|incorrect|unsure)", "category (rubric v2)", "rubric clause", "note", "reviewer"])
    for n, p in chosen:
        w.writerow([n, p["item_id"], "", "", "", "", ""])
with (out / "adjudication.csv").open("w", newline="", encoding="utf-8") as fh:
    csv.writer(fh).writerow(["n", "item_id", "first_label", "second_label", "first_category", "second_category", "clause", "adjudicated_label", "adjudicator", "reason"])
(out / "sample_ids.txt").write_text("".join(p["item_id"] + "\n" for _, p in chosen), encoding="utf-8")
(out / "README.md").write_text(f"""# Second-person review kit — {name}

{len(chosen)} of {len(packets)} units ({100 * len(chosen) / len(packets):.0f}%), stratified by company, seed {seed}.

1. Read `docs/v32-news-labelling-rubric.md` (rubric v2) first.
2. Label every unit in `sheet.md` **without** looking at any other label file, model output or arm, and fill in
   `form.csv` (label, category, rubric clause, a short note, your name).
3. Do not discuss units with the first labeller until the form is complete.
4. Adjudication: for each disagreement, add a row to `adjudication.csv`, decide by the rubric clause, and record the
   reason. The adjudicated label is used for scoring; first-pass agreement (Cohen's kappa) is reported.
""", encoding="utf-8")
print(name, "kit:", len(chosen), "units from", len(by_org), "companies ->", out)
