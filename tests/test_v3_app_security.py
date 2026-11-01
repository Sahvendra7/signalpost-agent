"""V3 §B12: the local search application's security controls."""
from __future__ import annotations

import http.client
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.app_harness import FakeRegistry, Harness  # noqa: E402
from helpers.fakeweb import valid_orgs  # noqa: E402
from norway_company_agent.app import security  # noqa: E402
from norway_company_agent.app.research import ResearchManager  # noqa: E402
from norway_company_agent.app.server import App, Server  # noqa: E402
from norway_company_agent.app.store import Store  # noqa: E402
from norway_company_agent.app.registry_search import RegistrySearch  # noqa: E402

ORGS = valid_orgs(30, start=950000000)


def stub_envelope(org: str, run_id: str) -> dict:
    return {"organisation_number": org, "run": {"run_id": run_id, "terminal_status": "completed", "started_at": "2026-11-01T00:00:00Z"},
            "claims": [], "evidence": [], "changes": [], "errors": [], "modules": {}}


class GatedRun:
    """A research stand-in that blocks until released, and records how many run at once."""

    def __init__(self, stop_reason: str | None = None):
        self.release = threading.Event()
        self.live = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.stop_reason = stop_reason

    def __call__(self, rows, *, run_id, progress, stop_event, **kwargs):
        org = rows[0].organisation_number
        progress[org] = {"evidence": {}}
        with self.lock:
            self.live += 1
            self.peak = max(self.peak, self.live)
        try:
            while not self.release.wait(0.02):
                if stop_event.is_set():
                    return {"envelopes": [stub_envelope(org, run_id)], "profiles": [None], "report": {"deadline": {"stop_reason": "interrupted"}}}
        finally:
            with self.lock:
                self.live -= 1
        return {"envelopes": [stub_envelope(org, run_id)], "profiles": [None], "report": {"deadline": {"stop_reason": self.stop_reason}}}


class QueryValidation(unittest.TestCase):
    def test_names_and_numbers_are_accepted(self):
        self.assertEqual(security.classify_query(" 983 181 732 "), ("number", "983181732"))
        for name in ("Tyin Alpint", "Alf I. Larsen A/S", "St.Olav Eiendom AS", "Hansen & Søn", "Ø"):
            self.assertEqual(security.classify_query(name)[0], "name", name)

    def test_urls_paths_and_bad_numbers_are_refused(self):
        for query in ("https://evil.example/", "http:x", "evil.com", "www.firma.no", "firma.no/kontakt", "user@firma.no", "../../etc/passwd",
                      "C:\\Windows", "file:/etc/passwd", "javascript:alert(1)", "x" * 101, "", "   ", "123", "983181733"):
            with self.subTest(query=query), self.assertRaises(security.HttpError) as caught:
                security.classify_query(query)
            self.assertEqual(caught.exception.status, 400)

    def test_rate_limiter_refills(self):
        now = [0.0]
        limiter = security.RateLimiter(2, per=60, clock=lambda: now[0])
        self.assertEqual([limiter.allow(), limiter.allow(), limiter.allow()], [True, True, False])
        now[0] = 30.0
        self.assertTrue(limiter.allow())


class ServerControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = FakeRegistry({ORGS[0]: "TEST AS"})
        self.gate = GatedRun()
        self.h = Harness(self.tmp.name, run=self.gate, registry=self.registry)

    def tearDown(self):
        self.gate.release.set()
        self.h.close()
        self.tmp.cleanup()

    def test_dns_rebinding_host_is_refused_with_421(self):
        for host in ("evil.example", f"evil.example:{self.h.port}", "127.0.0.1:1", ""):
            status, _, _ = self.h.request("GET", "/", headers={"Host": host})
            self.assertEqual(status, 421, host)
        self.assertEqual(self.h.request("GET", "/", headers={"Host": f"localhost:{self.h.port}"})[0], 200)

    def test_state_changes_need_token_origin_fetch_metadata_and_json(self):
        cases = {
            "no token": ({"X_Signalpost_Token": ""}, 403),
            "wrong token": ({"X_Signalpost_Token": "x" * 43}, 403),
            "no origin": ({"Origin": ""}, 403),
            "cross origin": ({"Origin": "http://evil.example"}, 403),
            "other port": ({"Origin": f"http://127.0.0.1:{self.h.port + 1}"}, 403),
            "cross site": ({"Sec_Fetch_Site": "cross-site"}, 403),
            "form post": ({"Content_Type": "application/x-www-form-urlencoded"}, 415),
        }
        for label, (override, expected) in cases.items():
            with self.subTest(label):
                status, answer = self.h.post("/api/research", {"org": ORGS[1]}, **override)
                self.assertEqual(status, expected, answer)
        self.assertEqual(self.h.research.jobs, {}, "no refused request started research")

    def test_research_body_is_small_and_only_an_organisation_number(self):
        status, _ = self.h.post("/api/research", {"org": ORGS[1], "url": "http://evil.example"})
        self.assertEqual(status, 400)
        status, _ = self.h.post("/api/research", {"org": "123456789"})
        self.assertEqual(status, 400)
        status, _ = self.h.post("/api/research", {"org": ["983181732"]})
        self.assertEqual(status, 400)
        headers = {"Content-Type": "application/json", "Origin": self.h.origin, "X-Signalpost-Token": "t" * 43}
        status, _, _ = self.h.request("POST", "/api/research", raw=b'{"org": "' + b"9" * 5000 + b'"}', headers=headers)
        self.assertEqual(status, 413)
        self.assertEqual(self.h.research.jobs, {})

    def test_url_like_searches_never_reach_the_registry(self):
        for query in ("https%3A%2F%2Fevil.example", "evil.com", "a%40b.no", "..%2F..%2Fetc"):
            status, answer = self.h.get_json(f"/api/search?q={query}")
            self.assertEqual((status, answer["code"]), (400, "url_not_allowed"), query)
        self.assertEqual(self.registry.calls, [])
        status, answer = self.h.get_json("/api/search?q=test")
        self.assertEqual(status, 200)
        self.assertEqual(len(self.registry.calls), 1)
        self.assertTrue(self.registry.calls[0].startswith("https://data.brreg.no/enhetsregisteret/api/enheter?navn=test&size=20"))

    def test_traversal_and_malformed_parameters(self):
        for path, expected in (("/company/..%2F..%2Fetc%2Fpasswd", 400), ("/company/../../etc/passwd", 404), ("/company/983181733", 400),
                               ("/snapshot/..%2F..%2Fsecret", 400), ("/snapshot/" + "0" * 64, 404), ("/api/jobs/../../x", 404),
                               ("/api/jobs/" + "g" * 32, 400), ("/api/jobs/" + "0" * 32, 404), ("/compare?orgs=1,2,3,4,5", 400),
                               ("/compare?" + "&".join(f"a{i}=1" for i in range(10)), 400), ("/nothing", 404)):
            with self.subTest(path):
                self.assertEqual(self.h.request("GET", path)[0], expected)
        self.assertEqual(self.h.request("PUT", "/api/research")[0], 404)

    def test_research_slots_are_bounded_and_queue_overflow_is_refused(self):
        jobs = [self.h.post("/api/research", {"org": org})[1] for org in ORGS[:4]]
        time.sleep(0.2)
        states = [self.h.get_json(f"/api/jobs/{job['id']}")[1]["state"] for job in jobs]
        self.assertEqual(states.count("running"), 2, states)
        self.assertEqual(self.gate.peak, 2)
        self.h.research.max_queue = 2
        status, answer = self.h.post("/api/research", {"org": ORGS[5]})
        self.assertEqual((status, answer["code"]), (429, "queue_full"))
        self.gate.release.set()
        for job in jobs:
            self.assertEqual(self.h.wait(job["id"])["state"], "completed")
        self.assertLessEqual(self.gate.peak, 2)

    def test_research_rate_limit(self):
        self.gate.release.set()
        statuses = [self.h.post("/api/research", {"org": org})[0] for org in ORGS[10:21]]
        self.assertEqual(statuses[:10], [202] * 10)
        self.assertEqual(statuses[10], 429)

    def test_search_rate_limit(self):
        statuses = [self.h.request("GET", "/api/search?q=test")[0] for _ in range(31)]
        self.assertEqual(statuses.count(429), 1)

    def test_request_concurrency_is_bounded(self):
        for _ in range(32):
            self.h.app.requests.acquire()
        try:
            self.assertEqual(self.h.request("GET", "/")[0], 503)
        finally:
            for _ in range(32):
                self.h.app.requests.release()
        self.assertEqual(self.h.request("GET", "/")[0], 200)

    def test_slow_clients_are_timed_out(self):
        sock = socket.create_connection(("127.0.0.1", self.h.port))
        sock.settimeout(15)
        sock.sendall(b"GET / HTTP/1.1\r\n")  # never finishes the request
        started = time.monotonic()
        self.assertEqual(sock.recv(100), b"", "the server closes the idle connection")
        self.assertLess(time.monotonic() - started, 12.5)
        sock.close()

    def test_errors_never_leak_a_traceback(self):
        def boom(*args, **kwargs):
            raise RuntimeError("secret /home/user/path")
        self.h.store.search = boom
        status, headers, body = self.h.request("GET", "/api/search?q=test")
        self.assertEqual(status, 500)
        self.assertNotIn(b"Traceback", body)
        self.assertNotIn(b"secret", body)

    def test_snapshot_for_an_indexed_hash_outside_the_roots_is_not_served(self):
        sha = "ab" * 32
        self.h.store._hashes.add(sha)
        outside = Path(self.tmp.name).parent / "ab"
        self.assertIsNone(self.h.store.snapshot_path(sha))
        self.assertEqual(self.h.request("GET", f"/snapshot/{sha}")[0], 404)
        self.assertFalse(outside.exists())


class Orphans(unittest.TestCase):
    def test_a_research_thread_left_running_after_a_deadline_keeps_its_slot(self):
        with tempfile.TemporaryDirectory() as raw:
            gate = GatedRun(stop_reason="deadline")
            gate.release.set()
            manager = ResearchManager(Store(raw), run=gate, max_live=1)
            job, _ = manager.submit(ORGS[0])
            for _ in range(100):
                if job.state not in ("queued", "running"):
                    break
                time.sleep(0.02)
            self.assertEqual(job.state, "partial")
            self.assertEqual(manager.live(), 1, "the orphan still holds the slot")
            second, _ = manager.submit(ORGS[1])
            time.sleep(0.1)
            self.assertEqual(second.state, "queued")
            job.progress[ORGS[0]]["run_metrics"] = {}  # the orphan's research ended
            manager.get(second.id)
            for _ in range(100):
                if second.state == "partial":
                    break
                time.sleep(0.02)
            self.assertEqual(second.state, "partial")


class Binding(unittest.TestCase):
    def test_non_loopback_needs_allow_remote(self):
        with tempfile.TemporaryDirectory() as raw:
            store = Store(raw)
            app = App(store, RegistrySearch(fetcher=FakeRegistry()), ResearchManager(store), token="t" * 43)
            with self.assertRaises(ValueError):
                Server(app, "0.0.0.0", 0)

    def test_the_app_runs_no_subprocess(self):
        for path in (ROOT / "src" / "norway_company_agent" / "app").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("subprocess", "os.system", "os.popen", "shell=True", "eval(", "exec("):
                self.assertNotIn(forbidden, text, f"{path.name}: {forbidden}")


if __name__ == "__main__":
    unittest.main()
