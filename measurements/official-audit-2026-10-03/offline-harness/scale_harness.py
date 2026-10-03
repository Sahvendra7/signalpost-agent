"""Offline batch-contract harness for the official audit (not part of the repo).

Feeds run_batch / the CLI reader with batches of companies the agent has never seen, with injected
source failures, and checks the official batch rules: one terminal envelope per input, input order,
isolation, no dependency on the public universe.
"""
from __future__ import annotations

import gzip
import json
import random
import resource
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

from test_contract import FakeBrreg, entity_body, offline_site, make_website_fetcher, result  # noqa: E402
from norway_company_agent.pipeline import mod11_valid, read_input_rows, run_batch  # noqa: E402
from norway_company_agent.pipeline import load_bulk_profiles  # noqa: E402

rng = random.Random(20261003)


def universe_orgs() -> set[str]:
    path = REPO / "signalpost-universe.jsonl.gz"
    if not path.exists():
        return set()
    with gzip.open(path, "rt") as handle:
        return {json.loads(line)["organisation_number"] for line in handle}


def synthetic_unseen(n: int, exclude: set[str]) -> list[str]:
    out: list[str] = []
    while len(out) < n:
        org = str(rng.randrange(800_000_000, 999_999_999))
        if mod11_valid(org) and org not in exclude and org not in out:
            out.append(org)
    return out


class ChaosBrreg(FakeBrreg):
    """FakeBrreg that answers for any org and injects failures by org-number hash."""

    def __call__(self, url: str):
        org = next((part for part in url.replace("=", "/").replace("&", "/").split("/") if len(part) == 9 and part.isdigit()), None)
        if org and org not in self.entities:
            self.entities[org] = entity_body(org, f"UNSEEN {org} AS")
        bucket = int(org or "0") % 100
        if bucket < 3 and "/roller" in url:
            raise RuntimeError("injected parser crash")
        if bucket in (3, 4) and "regnskap" in url:
            return result(url, 500)
        if bucket == 5 and "/enheter/" in url and "underenheter" not in url:
            return result(url, 200, entity_body("999999999", "SOMEONE ELSE AS"))  # wrong-org response
        if bucket == 6:
            return result(url, 0)  # network failure on every source
        return super().__call__(url)


def run_case(name: str, lines: list[str], suffix: str = ".jsonl", workers: int = 8) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / f"batch{suffix}"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        rows = read_input_rows(path)
        started = time.monotonic()
        out = run_batch(rows, run_id=name, fetcher=ChaosBrreg({}), website_fetcher=make_website_fetcher({}),
                        site_fetcher=offline_site, resolver=lambda host: False, workers=workers)
        elapsed = time.monotonic() - started
    env = out["envelopes"]
    expected_keys = [r.organisation_number or (str(r.raw) if r.raw is not None else None) for r in rows]
    statuses: dict[str, int] = {}
    for e in env:
        statuses[e["run"]["terminal_status"]] = statuses.get(e["run"]["terminal_status"], 0) + 1
    codes: dict[str, int] = {}
    for e in env:
        for err in e["errors"]:
            codes[err["code"]] = codes.get(err["code"], 0) + 1
    return {
        "case": name,
        "input_lines": len(lines),
        "rows_read": len(rows),
        "envelopes": len(env),
        "one_per_row": len(env) == len(rows),
        "order_preserved": [e.get("input_organisation_number") for e in env] == expected_keys,
        "validation_passed": out["report"]["validation"]["passed"],
        "terminal_status_counts": statuses,
        "error_codes": codes,
        "seconds": round(elapsed, 2),
    }


def main() -> None:
    universe = universe_orgs()
    results = []
    # 1) 1,200 numbers the agent has never researched (not even in the public universe).
    unseen = synthetic_unseen(1200, universe)
    results.append(run_case("unseen_1200_jsonl", [json.dumps({"organisation_number": o}) for o in unseen]))
    # 2) 1,100 real universe rows in the universe row format (what select_entry_batch emits), shuffled.
    real = rng.sample(sorted(universe), 1100) if universe else unseen[:1100]
    results.append(run_case("universe_rows_1100", [json.dumps({"organisation_number": o, "name": "x", "legal_form": "AS"}) for o in real]))
    # 3) Dirty batch: invalid, duplicate, checksum-fail, spaced, blank lines, organisasjonsnummer key.
    dirty = [json.dumps({"organisation_number": o}) for o in unseen[:150]]
    dirty += [json.dumps({"organisation_number": "12345"}), json.dumps({"organisation_number": unseen[0]}),
              json.dumps({"organisasjonsnummer": unseen[1]}), json.dumps({"organisation_number": "923 609 016"}),
              "", json.dumps({"organisation_number": "123456789"}), "not json at all"]
    results.append(run_case("dirty_157", dirty))
    # 4) Plain text, one number per line, 2,000 rows (no batch-size assumption).
    results.append(run_case("text_2000", synthetic_unseen(2000, universe | set(unseen)), suffix=".txt"))
    # 5) Input key variants the reader may not know (risk probe).
    for key in ("orgnr", "org", "organization_number", "organisationNumber"):
        results.append(run_case(f"key_{key}", [json.dumps({key: o}) for o in unseen[:5]]))
    # 6) CSV with a header row (risk probe).
    results.append(run_case("csv_header", ["organisation_number"] + unseen[:5], suffix=".csv"))
    # 7) --bulk robustness: a plain (non-gzip) CSV passed as the registry snapshot.
    with tempfile.TemporaryDirectory() as directory:
        plain = Path(directory) / "enheter.csv"
        plain.write_text("organisasjonsnummer;navn\n" + unseen[0] + ";UNSEEN AS\n", encoding="utf-8")
        try:
            load_bulk_profiles(plain, {unseen[0]})
            bulk = "loaded"
        except Exception as exc:  # noqa: BLE001
            bulk = f"raised {type(exc).__name__}: {str(exc)[:80]}"
    results.append({"case": "bulk_plain_csv", "outcome": bulk})
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(json.dumps({"universe_rows_known": len(universe), "peak_rss_mib": round(peak, 1), "results": results}, indent=1))


if __name__ == "__main__":
    main()
