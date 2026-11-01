"""V3 §B8: run history, published-envelope baselines, retractions, removed vs not re-checked, first-seen."""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.c12_replay import Fixture  # noqa: E402
from norway_company_agent import history  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402

V3 = ROOT / "tests" / "fixtures" / "v3"
TYIN = "983181732"
KILIS = "875606662"


def envelope(org: str, status: str = "completed") -> dict:
    return {"organisation_number": org, "run": {"run_id": "r", "terminal_status": status, "started_at": "2026-10-01T00:00:00Z"}, "claims": [], "evidence": []}


def report(stop: str | None = None, n: int = 1) -> dict:
    return {"run_id": "r", "started_at": "2026-10-01T00:00:00Z", "completed_at": "2026-10-01T00:01:00Z", "emitted_envelopes": n,
            "deadline": {"stop_reason": stop}, "validation": {"passed": True}}


class History(unittest.TestCase):
    def test_runs_are_written_atomically_with_a_manifest_and_completeness(self):
        with tempfile.TemporaryDirectory() as raw:
            path = history.write_run(raw, "run 1/../x", [envelope("911771098")], [], report())
            self.assertTrue(path.is_relative_to(Path(raw)), "the run id cannot escape the history directory")
            manifest = json.loads((path / "manifest.json").read_text())
            self.assertEqual((manifest["marker"], manifest["complete"], manifest["organisations"]), (history.MARKER, True, ["911771098"]))
            interrupted = history.write_run(raw, "run2", [envelope("911771098")], [], report("interrupted"))
            self.assertFalse(json.loads((interrupted / "manifest.json").read_text())["complete"])
            Path(raw, ".tmp-run3-dead").mkdir()  # an interrupted write
            self.assertEqual(len(history.runs(raw)), 2, "temporary directories are never runs")

    def test_an_incomplete_run_or_a_failed_company_is_never_a_baseline(self):
        with tempfile.TemporaryDirectory() as raw:
            good = envelope("911771098")
            good["claims"] = [{"field": "x"}]
            history.write_run(raw, "a", [good], [], {**report(), "completed_at": "2026-10-01T00:01:00Z"})
            history.write_run(raw, "b", [envelope("911771098", "failed")], [], {**report(), "completed_at": "2026-10-02T00:01:00Z"})
            history.write_run(raw, "c", [envelope("911771098")], [], {**report("deadline"), "completed_at": "2026-10-03T00:01:00Z"})
            self.assertEqual(history.baselines(raw, ["911771098"])["911771098"]["claims"], [{"field": "x"}])

    def test_prune_keeps_the_newest_two_complete_runs_and_never_touches_foreign_directories(self):
        with tempfile.TemporaryDirectory() as raw:
            for day in range(1, 7):
                history.write_run(raw, f"r{day}", [envelope("911771098")], [], {**report(None if day <= 2 else "interrupted"), "completed_at": f"2026-10-0{day}T00:00:00Z"})
            foreign = Path(raw, "my-notes")
            foreign.mkdir()
            deleted = history.prune(raw, keep=2)
            names = sorted(Path(path).name for path in deleted)
            self.assertEqual(names, ["r3", "r4"], "r6, r5 are the newest; r1, r2 the only complete runs")
            self.assertTrue(foreign.exists())


class PublishedBaseline(unittest.TestCase):
    def run_v3(self, org: str, previous: dict | None = None) -> dict:
        fixture = Fixture(org, base=V3)
        return run_batch([InputRow(0, org, org)], run_id="v3-now", previous_envelopes={org: previous} if previous else None, **fixture.injected())["envelopes"][0]

    def test_a_withdrawn_attribution_is_a_retraction_with_its_rule(self):
        """TYIN ALPINT: the baseline published Tyin Filefjell's three profiles; V3 still extracts them and holds them."""
        current = self.run_v3(TYIN)
        baseline = copy.deepcopy(current)
        baseline["run"] = {**baseline["run"], "run_id": "ff3b515-run", "code_version": {"source_sha256": "0" * 64, "git_commit": None, "git_dirty": None}}
        home = next(item for item in baseline["evidence"] if item["source_url"] == "https://www.tyinfilefjell.no/")
        baseline["claims"] = [claim for claim in baseline["claims"] if claim["field"] != "social_profile"]
        for url, canonical in (("https://www.facebook.com/tyinfilefjell", "https://facebook.com/tyinfilefjell"), ("https://www.instagram.com/tyinfilefjell", "https://instagram.com/tyinfilefjell"),
                               ("https://no.linkedin.com/company/tyin-filefjell-as", "https://linkedin.com/company/tyin-filefjell-as")):
            baseline["claims"].append({"field": "social_profile", "category": "public_activity", "value": url, "availability": "available", "canonical_url": canonical,
                                       "evidence_ids": [home["id"]], "source_page": "https://www.tyinfilefjell.no/", "confidence": 0.95})
        refreshed = self.run_v3(TYIN, baseline)
        retracted = [change for change in refreshed["changes"] if change["change_type"] == "retracted"]
        self.assertEqual(len(retracted), 3, refreshed["changes"])
        self.assertEqual({change["rule"] for change in retracted}, {"site_operated_by_other_entity"})
        self.assertNotIn("verified", " ".join(change["basis"] for change in retracted).casefold())
        self.assertEqual(refreshed["refresh"]["baseline"]["kind"], "published_envelope")
        self.assertEqual(refreshed["refresh"]["counts"]["retracted"], 3)
        self.assertEqual(validate_envelope(refreshed), [])

    def test_same_data_again_gives_no_event_and_first_seen_is_carried(self):
        first = self.run_v3(KILIS)
        self.assertFalse(any("is_new" in claim for claim in first["claims"]), "no baseline: a first observation, never 'new'")
        again = self.run_v3(KILIS, first)
        self.assertEqual([change for change in again["changes"] if change["change_type"] != "unavailable"], [])
        news = [claim for claim in again["claims"] if claim["field"] == "news_item" and claim["availability"] == "available"]
        self.assertTrue(news and all(claim["first_seen_run_id"] == "v3-now" and not claim.get("is_new") for claim in news))

    def test_removed_when_the_page_was_read_and_not_rechecked_when_it_was_not(self):
        current = self.run_v3(KILIS)
        baseline = copy.deepcopy(current)
        feed = next(item for item in baseline["evidence"] if item["source_url"].endswith("/feed/"))
        baseline["claims"].append({"field": "news_item", "category": "public_activity", "availability": "available", "evidence_ids": [feed["id"]],
                                   "value": {"title": "Gammel sak fra feeden", "url": "https://kilishockey.no/gammel-sak/", "publication_date": "2026-01-01T10:00:00Z"},
                                   "source_page": feed["source_url"]})
        baseline["claims"].append({"field": "news_item", "category": "public_activity", "availability": "available", "evidence_ids": [feed["id"]],
                                   "value": {"title": "Sak fra en side som ikke ble lest", "url": "https://kilishockey.no/arkiv/sak/", "publication_date": "2025-01-01T10:00:00Z"},
                                   "source_page": "https://kilishockey.no/arkiv/"})
        refreshed = self.run_v3(KILIS, baseline)
        kinds = {change["old_value"]["title"]: change["change_type"] for change in refreshed["changes"] if change.get("field") == "news_item"}
        self.assertEqual(kinds, {"Gammel sak fra feeden": "removed", "Sak fra en side som ikke ble lest": "not_rechecked"})

    def test_new_items_are_marked_only_against_a_baseline(self):
        current = self.run_v3(KILIS)
        baseline = copy.deepcopy(current)
        dropped = next(claim for claim in baseline["claims"] if claim["field"] == "news_item" and claim["availability"] == "available")
        baseline["claims"].remove(dropped)
        refreshed = self.run_v3(KILIS, baseline)
        new = [claim["value"]["title"] for claim in refreshed["claims"] if claim.get("is_new")]
        self.assertEqual(new, [dropped["value"]["title"]])
        self.assertEqual(refreshed["refresh"]["new_items"]["news_item"], 1)


class FirstObservation(unittest.TestCase):
    """Live release run, 929336038: the baseline's website returned an HTTP error, the refresh read it. Its profile and
    careers page were reported "added" and the profile "new" — they were simply not observable before."""

    def test_items_on_a_site_the_baseline_could_not_read_are_first_observations(self):
        current = PublishedBaseline.run_v3(None, KILIS)
        baseline = copy.deepcopy(current)
        baseline["claims"] = [claim for claim in baseline["claims"] if claim["field"] not in ("news_item", "social_profile", "careers_page")]
        baseline["modules"]["site_research"] = {"state": "source_error", "note": "Registry-linked website could not be checked in this run (http_error)"}
        refreshed = PublishedBaseline.run_v3(None, KILIS, baseline)
        site_changes = [change for change in refreshed["changes"] if change.get("field") in ("news_item", "social_profile", "careers_page")]
        self.assertTrue(site_changes)
        self.assertEqual({change["change_type"] for change in site_changes}, {"first_observed"})
        self.assertFalse(any(claim.get("is_new") for claim in refreshed["claims"]))
        self.assertEqual(refreshed["refresh"]["counts"].get("added", 0), 0)
        self.assertEqual(validate_envelope(refreshed), [])

    def test_after_a_read_baseline_additions_stay_new(self):
        current = PublishedBaseline.run_v3(None, KILIS)
        baseline = copy.deepcopy(current)
        dropped = next(claim for claim in baseline["claims"] if claim["field"] == "news_item" and claim["availability"] == "available")
        baseline["claims"].remove(dropped)
        self.assertEqual(baseline["modules"]["site_research"]["state"], "complete")
        refreshed = PublishedBaseline.run_v3(None, KILIS, baseline)
        self.assertEqual([change["change_type"] for change in refreshed["changes"] if change.get("field") == "news_item"], ["added"])


class CommandLineHistory(unittest.TestCase):
    def test_the_documented_command_keeps_history_and_uses_it_as_the_baseline(self):
        from norway_company_agent.cli import main
        fixture = Fixture(KILIS, base=V3)
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            (out / "in.jsonl").write_text(json.dumps({"organisation_number": KILIS}) + "\n")
            for run in ("r1", "r2"):
                argv = ["--organisations", str(out / "in.jsonl"), "--output", str(out / f"{run}.jsonl"), "--profiles-output", str(out / f"{run}-p.jsonl"),
                        "--report", str(out / f"{run}-report.json"), "--run-id", run, "--no-viewer"]
                with open(os.devnull, "w") as sink:
                    stdout, sys.stdout = sys.stdout, sink
                    try:
                        main(argv, **fixture.injected())
                    except SystemExit as exit_code:
                        self.assertEqual(exit_code.code, 0)
                    finally:
                        sys.stdout = stdout
            second = json.loads((out / "r2.jsonl").read_text().splitlines()[0])
            self.assertEqual(second["refresh"]["baseline"]["run_id"], "r1")
            self.assertEqual([change for change in second["changes"] if change["change_type"] != "unavailable"], [])
            report = json.loads((out / "r2-report.json").read_text())
            self.assertTrue(report["history"]["written"])
            self.assertEqual(report["baseline"]["source"], "history")
            self.assertEqual(report["manual_audit"]["state"], "not_audited")
            self.assertEqual(len(history.runs(out / "signalpost-history")), 2)

    def test_an_outage_in_the_next_run_is_carried_forward_not_removed(self):
        """Live release refresh, 929336038: robots.txt unreachable in the second run. Without the history run's profiles
        the website, profile, careers page and description were reported "removed" — an outage taken for a change."""
        from norway_company_agent.cli import main
        from norway_company_agent.evidence import evidence
        from norway_company_agent.http import ByteFetch
        fixture = Fixture(KILIS, base=V3)
        down = {**fixture.injected(),
                "site_fetcher": lambda url, **kwargs: ByteFetch(url, 0, 0, b"", None, {}, None, "2026-11-01T00:00:00Z", 1, "URLError: network unreachable"),
                "website_fetcher": lambda url: (evidence("website", "blocked", "registry_linked_company_website", str(url or "https://kilishockey.no/"),
                                                         note="robots.txt unreachable (5xx/429/network; RFC 9309: assume disallow)"), {"requests": 1, "bytes": 0, "latencies_ms": []})}
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            (out / "in.jsonl").write_text(json.dumps({"organisation_number": KILIS}) + "\n")
            for run, injected in (("r1", fixture.injected()), ("r2", down)):
                argv = ["--organisations", str(out / "in.jsonl"), "--output", str(out / f"{run}.jsonl"), "--profiles-output", str(out / f"{run}-p.jsonl"),
                        "--report", str(out / f"{run}-report.json"), "--run-id", run, "--no-viewer"]
                with open(os.devnull, "w") as sink:
                    stdout, sys.stdout = sys.stdout, sink
                    try:
                        main(argv, **injected)
                    except SystemExit as exit_code:
                        self.assertEqual(exit_code.code, 0)
                    finally:
                        sys.stdout = stdout
            second = json.loads((out / "r2.jsonl").read_text().splitlines()[0])
            kinds = {change["change_type"] for change in second["changes"]}
            self.assertNotIn("removed", kinds, second["changes"])
            self.assertIn("unavailable", kinds)
            self.assertEqual(second["refresh"]["baseline"]["kind"], "published_envelope")
            website = next(claim for claim in second["claims"] if claim["field"] == "official_website")
            self.assertEqual((website["availability"], website.get("carried_forward")), ("available", True))


if __name__ == "__main__":
    unittest.main()
