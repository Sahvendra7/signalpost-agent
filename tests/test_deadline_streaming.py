"""Phase 1: streaming output, batch deadline, degradation, interruption and kill safety."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, no_website, valid_orgs  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.pipeline import InputRow, run_batch  # noqa: E402
from norway_company_agent.streaming import read_jsonl_tolerant  # noqa: E402

HELPER = ROOT / "tests" / "helpers" / "cli_with_fakes.py"


def rows_for(orgs):
    return [InputRow(position=index, raw=org, organisation_number=org) for index, org in enumerate(orgs)]


def codes(envelope):
    return {error["code"] for error in envelope["errors"]}


def available(envelope, field):
    return any(claim["field"] == field and claim["availability"] == "available" for claim in envelope["claims"])


class InProcessDeadlineTests(unittest.TestCase):
    def test_results_are_emitted_as_each_company_finishes(self):
        orgs = valid_orgs(6)
        brreg = FakeBrreg({org: entity(org) for org in orgs}, slow_orgs={orgs[0]: 0.4})
        seen = []
        started = time.monotonic()
        output = run_batch(rows_for(orgs), run_id="t", workers=3, on_result=lambda envelopes, profile: seen.append((time.monotonic() - started, [e["organisation_number"] for e in envelopes])), **injected(brreg))
        self.assertEqual(len(output["envelopes"]), 6)
        self.assertEqual([item[1][0] for item in seen][-1], orgs[0], "the slow company is emitted last")
        self.assertLess(seen[0][0], 1.0, "fast companies are emitted long before the slow one finishes")
        self.assertEqual([e["organisation_number"] for e in output["envelopes"]], orgs, "returned envelopes keep input order")

    def test_deadline_leaves_every_row_terminal_and_valid(self):
        orgs = valid_orgs(30)
        brreg = FakeBrreg({org: entity(org) for org in orgs}, delay=0.1)
        started = time.monotonic()
        output = run_batch(rows_for(orgs), run_id="t", workers=2, deadline_seconds=3.0, grace_seconds=1.0, **injected(brreg))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 4.5)
        self.assertEqual(len(output["envelopes"]), 30)
        self.assertTrue(output["report"]["validation"]["passed"], output["report"]["validation"])
        skipped = [e for e in output["envelopes"] if "deadline_exceeded" in codes(e)]
        self.assertTrue(skipped, "some companies must be cut by the deadline in this setup")
        self.assertTrue(all(e["run"]["terminal_status"] in {"completed", "failed"} for e in output["envelopes"]))
        self.assertTrue(all(validate_envelope(e) == [] for e in output["envelopes"]))
        self.assertGreater(output["report"]["deadline"]["companies_not_started"] + output["report"]["deadline"]["companies_salvaged_at_hard_stop"], 0)
        self.assertIn(output["report"]["deadline"]["stop_reason"], {"deadline", "grace_window"})
        unanchored = [e for e in output["envelopes"] if not e["identity"]["anchored"]]
        self.assertTrue(all(e["company_status"]["state"] == "not_researched" for e in unanchored), "a deadline cut is not an unresolved identity")

    def test_hard_stop_salvages_official_facts_already_fetched(self):
        orgs = valid_orgs(2)
        brreg = FakeBrreg({org: entity(org) for org in orgs})
        release = threading.Event()

        def hanging_website(url):
            release.wait(10)
            return no_website(url)

        try:
            started = time.monotonic()
            output = run_batch(rows_for(orgs), run_id="t", workers=2, deadline_seconds=1.5, grace_seconds=0.2, **{**injected(brreg), "website_fetcher": hanging_website})
            self.assertLess(time.monotonic() - started, 3.0, "the batch does not wait for a hung company")
        finally:
            release.set()
        for envelope in output["envelopes"]:
            self.assertIn("deadline_exceeded", codes(envelope))
            self.assertTrue(available(envelope, "legal_name"), "registry facts fetched before the stop are kept")
            self.assertTrue(available(envelope, "ceo"))
            self.assertEqual(envelope["run"]["terminal_status"], "completed")
            self.assertEqual(validate_envelope(envelope), [])
        self.assertEqual(output["report"]["deadline"]["companies_salvaged_at_hard_stop"], 2)

    def test_projected_overrun_degrades_new_companies_to_official_only(self):
        orgs = valid_orgs(4)
        brreg = FakeBrreg({org: entity(org) for org in orgs})

        def slow_website(url):
            time.sleep(1.0)
            return no_website(url)

        output = run_batch(rows_for(orgs), run_id="t", workers=1, deadline_seconds=3.5, grace_seconds=0.5, **{**injected(brreg), "website_fetcher": slow_website})
        degraded = [e for e in output["envelopes"] if "deadline_degraded" in codes(e)]
        self.assertTrue(degraded)
        for envelope in degraded:
            self.assertTrue(available(envelope, "legal_name"))
            self.assertIn("deadline", envelope["modules"]["site_research"]["note"])
        self.assertEqual(len(output["envelopes"]), 4)
        self.assertTrue(output["report"]["validation"]["passed"])

    def test_stop_event_emits_every_remaining_row(self):
        orgs = valid_orgs(12)
        brreg = FakeBrreg({org: entity(org) for org in orgs}, delay=0.05)
        stop = threading.Event()
        output = run_batch(rows_for(orgs), run_id="t", workers=1, stop_event=stop, on_result=lambda envelopes, profile: stop.set(), **injected(brreg))
        self.assertEqual([e["input_organisation_number"] for e in output["envelopes"]], orgs)
        self.assertTrue(any(codes(e) & {"interrupted", "deadline_exceeded"} for e in output["envelopes"]))
        self.assertTrue(output["report"]["validation"]["passed"])


class ProcessKillTests(unittest.TestCase):
    COUNT = 60

    def start(self, directory: Path, *extra: str, delay: float = 0.04):
        args = [sys.executable, str(HELPER), "--count", str(self.COUNT), "--delay", str(delay), "--write-input", str(directory / "in.jsonl"), "--",
                "--organisations", str(directory / "in.jsonl"), "--output", str(directory / "env.jsonl"), "--profiles-output", str(directory / "prof.jsonl"),
                "--report", str(directory / "report.json"), "--run-id", "kill", "--workers", "2", *extra]
        # The helper writes the input before the CLI reads it, so create it first by a dry write.
        from helpers.fakeweb import valid_orgs as orgs_for

        (directory / "in.jsonl").write_text("".join(json.dumps({"organisation_number": org}) + "\n" for org in orgs_for(self.COUNT)))
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def wait_lines(self, path: Path, minimum: int, timeout: float = 30.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and len(read_jsonl_tolerant(path)) >= minimum:
                return len(read_jsonl_tolerant(path))
            time.sleep(0.02)
        self.fail(f"stream never reached {minimum} lines")

    def check_persisted(self, path: Path, at_least: int):
        rows = read_jsonl_tolerant(path)
        self.assertGreaterEqual(len(rows), at_least)
        self.assertEqual(len({row["organisation_number"] for row in rows}), len(rows), "no duplicate envelopes")
        for row in rows:
            self.assertEqual(validate_envelope(row), [])
            self.assertEqual(row["run"]["terminal_status"], "completed")

    def test_sigkill_early_middle_and_late_keeps_completed_results(self):
        for label, threshold in (("first 10", 3), ("middle", 30), ("near end", 55)):
            with self.subTest(label), tempfile.TemporaryDirectory() as raw:
                directory = Path(raw)
                process = self.start(directory)
                seen = self.wait_lines(directory / "env.jsonl", threshold)
                process.send_signal(signal.SIGKILL)
                process.wait(10)
                self.check_persisted(directory / "env.jsonl", seen)
                self.check_persisted_profiles(directory / "prof.jsonl", seen)

    def check_persisted_profiles(self, path: Path, at_least: int):
        rows = read_jsonl_tolerant(path)
        self.assertGreaterEqual(len(rows), at_least)

    def test_sigterm_writes_every_row_in_input_order(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            process = self.start(directory)
            self.wait_lines(directory / "env.jsonl", 10)
            process.send_signal(signal.SIGTERM)
            process.wait(20)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode()[-2000:])
            rows = [json.loads(line) for line in (directory / "env.jsonl").read_text().splitlines()]
            expected = [json.loads(line)["organisation_number"] for line in (directory / "in.jsonl").read_text().splitlines()]
            self.assertEqual([row["input_organisation_number"] for row in rows], expected)
            self.assertTrue(any("interrupted" in codes(row) or "deadline_exceeded" in codes(row) for row in rows))
            report = json.loads((directory / "report.json").read_text())
            self.assertEqual(report["deadline"]["stop_reason"], "interrupted")
            self.assertTrue(report["validation"]["passed"])

    def test_cli_deadline_flag_and_env_default(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            env = {**os.environ, "SIGNALPOST_DEADLINE_SECONDS": "2", "SIGNALPOST_GRACE_SECONDS": "0.5"}
            args = [sys.executable, str(HELPER), "--count", str(self.COUNT), "--delay", "0.04", "--write-input", str(directory / "in.jsonl"), "--",
                    "--organisations", str(directory / "in.jsonl"), "--output", str(directory / "env.jsonl"), "--profiles-output", str(directory / "prof.jsonl"),
                    "--report", str(directory / "report.json"), "--run-id", "deadline", "--workers", "2"]
            started = time.monotonic()
            completed = subprocess.run(args, env=env, capture_output=True, timeout=60)
            self.assertLess(time.monotonic() - started, 15)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode()[-2000:])
            rows = [json.loads(line) for line in (directory / "env.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), self.COUNT)
            report = json.loads((directory / "report.json").read_text())
            self.assertEqual(report["deadline"]["deadline_seconds"], 2.0)
            self.assertIn(report["deadline"]["stop_reason"], {"deadline", "grace_window", None})
            self.assertTrue(report["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
