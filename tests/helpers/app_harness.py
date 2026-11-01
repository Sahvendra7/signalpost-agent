"""Start the local search app on a free loopback port for tests, with injected (offline) research and registry."""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from typing import Any

from norway_company_agent.app.registry_search import RegistrySearch
from norway_company_agent.app.research import ResearchManager
from norway_company_agent.app.server import App, Server
from norway_company_agent.app.store import Store
from norway_company_agent.http import FetchResult

TOKEN = "t" * 43


class FakeRegistry:
    """The registry search endpoint: returns `entities` (org -> name) whose name contains the query."""

    def __init__(self, entities: dict[str, str] | None = None):
        self.entities, self.calls = entities or {}, []

    def __call__(self, url: str) -> FetchResult:
        self.calls.append(url)
        import urllib.parse
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "organisasjonsnummer" in query:
            hits = {org: name for org, name in self.entities.items() if org == query["organisasjonsnummer"][0]}
        else:
            hits = {org: name for org, name in self.entities.items() if query.get("navn", [""])[0].casefold() in name.casefold()}
        body = {"_embedded": {"enheter": [{"organisasjonsnummer": org, "navn": name, "organisasjonsform": {"kode": "AS"}} for org, name in hits.items()]}} if hits else {}
        return FetchResult(url, 200, 1, 10, body, retrieved_at="2026-11-01T00:00:00Z")


class Harness:
    def __init__(self, data_dir: str | Path, *, run=None, run_kwargs: dict[str, Any] | None = None, imports=(), snapshot_dirs=(), registry=None, **manager):
        self.store = Store(data_dir, imports=imports, snapshot_dirs=snapshot_dirs)
        self.registry_fetcher = registry or FakeRegistry()
        self.research = ResearchManager(self.store, run_kwargs=run_kwargs or {}, **({"run": run} if run else {}), **manager)
        self.app = App(self.store, RegistrySearch(fetcher=self.registry_fetcher), self.research, token=TOKEN)
        self.server = Server(self.app, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def request(self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None, raw: bytes | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        base = {"Host": f"127.0.0.1:{self.port}"}
        connection.request(method, path, body=payload, headers={**base, **(headers or {})})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, {key.lower(): value for key, value in response.getheaders()}, data

    def get_json(self, path: str) -> tuple[int, Any]:
        status, _, data = self.request("GET", path)
        return status, json.loads(data or b"null")

    def post(self, path: str, body: Any, **override: str) -> tuple[int, Any]:
        headers = {"Content-Type": "application/json", "Origin": self.origin, "Sec-Fetch-Site": "same-origin", "X-Signalpost-Token": TOKEN}
        headers.update({key.replace("_", "-"): value for key, value in override.items()})
        headers = {key: value for key, value in headers.items() if value is not None and value != ""}
        status, _, data = self.request("POST", path, body, headers)
        return status, json.loads(data or b"null")

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
        import time
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            status, job = self.get_json(f"/api/jobs/{job_id}")
            if job["state"] in ("completed", "partial", "failed", "cancelled"):
                return job
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} did not finish: {job}")
