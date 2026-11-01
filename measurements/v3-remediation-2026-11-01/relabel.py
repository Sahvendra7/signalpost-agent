#!/usr/bin/env python3
"""Carry existing labels (by unit id) onto a new blind sample of the same set, failing on any unlabelled unit.

    uv run python measurements/v3-remediation-2026-11-01/relabel.py NEW_ITEMS.csv OUT.labelled.csv LABELLED.csv [LABELLED.csv ...]
"""
import csv
import sys

new, out, *sources = sys.argv[1:]
labels = {}
for path in sources:
    for row in csv.DictReader(open(path, encoding="utf-8")):
        if row.get("verdict"):
            labels[row["uid"]] = (row["verdict"], row.get("note", ""))
rows = list(csv.DictReader(open(new, encoding="utf-8")))
missing = [row["uid"] for row in rows if row["category"] != "official_website" and row["uid"] not in labels]
if missing:
    raise SystemExit(f"{len(missing)} unlabelled units, e.g. {missing[:5]}")
for row in rows:
    if row["uid"] in labels:
        row["verdict"], row["note"] = labels[row["uid"]]
writer = csv.DictWriter(open(out, "w", encoding="utf-8", newline=""), fieldnames=list(rows[0].keys()))
writer.writeheader()
writer.writerows(rows)
print(f"{len(rows)} units, labels carried")
