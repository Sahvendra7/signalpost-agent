"""The local HTTP server (V3 design §B11–§B12): standard library only, loopback by default.

Every request is checked for its Host header (DNS rebinding), bounded in time (socket timeout) and in number (a
semaphore; 503 when full). State-changing requests also need the page's token, the server's own Origin and
same-origin fetch metadata. Responses never contain a traceback.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..viewer import _identity, render_viewer
from .pages import SEARCH_CSP, search_page
from .registry_search import RegistrySearch
from .research import ResearchManager
from .security import MAX_BODY, HttpError, RateLimiter, check_host, check_post, classify_query, valid_job_id, valid_org, valid_sha
from .store import Store

LOG = logging.getLogger("signalpost.app")
VIEWER_CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
SNAPSHOT_CSP = "sandbox; default-src 'none'"
SOCKET_TIMEOUT = 10
MAX_CONCURRENT_REQUESTS = 32
APP_LINKS = {"search": "/", "snapshots": "/snapshot/"}


class App:
    """Everything a request handler needs; one per server."""

    def __init__(self, store: Store, registry: RegistrySearch, research: ResearchManager, *, token: str, manual_audit: dict[str, Any] | None = None):
        self.store, self.registry, self.research, self.token = store, registry, research, token
        self.manual_audit = manual_audit or {"state": "not_audited", "note": "no manual audit supplied (--audit-results)"}
        self.search_limit = RateLimiter(30)
        self.research_limit = RateLimiter(10)
        self.requests = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

    def viewer(self, envelopes: list[dict[str, Any]], title: str, open_view: str) -> str:
        return render_viewer(envelopes, {"manual_audit": self.manual_audit}, title=title, app={**APP_LINKS, "open": open_view})


class Handler(BaseHTTPRequestHandler):
    server_version = "Signalpost"
    sys_version = ""
    timeout = SOCKET_TIMEOUT  # slow or idle clients cannot hold a thread
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    # ---- plumbing ------------------------------------------------------------------------------------------
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — the base-class signature
        return  # replaced by log_request below: method, short path, status

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        path, _, query = (self.path or "").partition("?")
        LOG.info("%s %s%s %s", self.command, path[:80], ("?" + query[:20]) if query else "", code)

    def _send(self, status: int, body: bytes, content_type: str, csp: str | None = None, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", "default-src 'none'; frame-ancestors 'none'")

    def _html(self, text: str, csp: str) -> None:
        self._send(200, text.encode("utf-8"), "text/html; charset=utf-8", csp)

    def _error(self, error: HttpError) -> None:
        if self.path.startswith("/api/"):
            self._json(error.status, {"code": error.code, "message": error.message})
        else:
            self._send(error.status, f"{error.message}\n".encode("utf-8"), "text/plain; charset=utf-8", "default-src 'none'; frame-ancestors 'none'")

    def _dispatch(self, routes: list[tuple[re.Pattern[str], Any]]) -> None:
        if not self.app.requests.acquire(blocking=False):
            self.close_connection = True
            self._error(HttpError(503, "busy", "The server is busy; try again"))
            return
        try:
            check_host(self.headers.get("Host"), self.server.server_address[1], self.server.extra_hosts)  # type: ignore[attr-defined]
            path, _, query = self.path.partition("?")
            for pattern, handler in routes:
                match = pattern.fullmatch(path)
                if match:
                    try:
                        params = urllib.parse.parse_qs(query, max_num_fields=5)
                    except ValueError:
                        raise HttpError(400, "invalid_query_string", "Too many parameters") from None
                    handler(match, params)
                    return
            raise HttpError(404, "not_found", "Not found")
        except HttpError as error:
            if error.status in (400, 411, 413, 415, 421):
                self.close_connection = True
            self._error(error)
        except Exception:  # noqa: BLE001 — logged with its traceback here, never sent to the client
            LOG.exception("request failed: %s %s", self.command, self.path[:80])
            self.close_connection = True
            self._error(HttpError(500, "internal_error", "Something went wrong; nothing was changed"))
        finally:
            self.app.requests.release()

    def do_GET(self) -> None:  # noqa: N802 — http.server naming
        self._dispatch([
            (re.compile(r"/"), self.search_page),
            (re.compile(r"/api/search"), self.api_search),
            (re.compile(r"/company/([^/]*)"), self.company),
            (re.compile(r"/compare"), self.compare),
            (re.compile(r"/whats-new"), self.whats_new),
            (re.compile(r"/api/jobs/([^/]*)"), self.job),
            (re.compile(r"/snapshot/([^/]*)"), self.snapshot),
        ])

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch([
            (re.compile(r"/api/research"), self.api_research),
            (re.compile(r"/api/jobs/([^/]*)/cancel"), self.cancel),
        ])

    def _not_allowed(self) -> None:
        self._dispatch([])

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed  # noqa: N815 — 404 for every other method and path

    def _body(self) -> dict[str, Any]:
        """A small JSON object, after the CSRF checks."""
        port = self.server.server_address[1]
        origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}", *(f"http://{name}:{port}" for name in self.server.extra_hosts)}  # type: ignore[attr-defined]
        check_post(self.headers, self.app.token, origins)
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            raise HttpError(411, "length_required", "Content-Length is required")
        if int(length) > MAX_BODY:
            raise HttpError(413, "body_too_large", "Request too large")
        raw = self.rfile.read(int(length))
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            raise HttpError(400, "invalid_json", "Send a JSON object") from None
        if not isinstance(body, dict):
            raise HttpError(400, "invalid_json", "Send a JSON object")
        return body

    # ---- routes --------------------------------------------------------------------------------------------
    def search_page(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        self._html(search_page(self.app.token, len(self.app.store.all_latest())), SEARCH_CSP)

    def api_search(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        kind, text = classify_query((query.get("q") or [""])[0])
        self.app.search_limit.check()
        local = self.app.store.search(kind, text)
        registry = self.app.registry.search(kind, text)
        self._json(200, {"query_kind": kind, "query": text, "local": local, "registry": registry})

    def _indexed(self, org: str) -> dict[str, Any]:
        envelope = self.app.store.latest(valid_org(org))
        if envelope is None:
            raise HttpError(404, "not_researched", "This company has not been researched yet. Search for it to research it.")
        return envelope

    def company(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        envelope = self._indexed(match.group(1))
        name = _identity(envelope).get("legal_name") or envelope.get("organisation_number")
        self._html(self.app.viewer([envelope], f"{name} — Signalpost", "org=" + str(envelope["organisation_number"])), VIEWER_CSP)

    def compare(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        orgs = list(dict.fromkeys(item for item in ",".join(query.get("orgs") or []).split(",") if item))
        if not 2 <= len(orgs) <= 4:
            raise HttpError(400, "compare_count", "Choose 2 to 4 companies to compare")
        envelopes = [self._indexed(org) for org in orgs]
        self._html(self.app.viewer(envelopes, "Comparison — Signalpost", "compare=" + ",".join(orgs)), VIEWER_CSP)

    def whats_new(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        self._html(self.app.viewer(self.app.store.all_latest(), "What's new — Signalpost", "new"), VIEWER_CSP)

    def snapshot(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        sha = valid_sha(match.group(1))
        path = self.app.store.snapshot_path(sha)
        if path is None:
            raise HttpError(404, "snapshot_not_found", "No captured copy with this hash")
        self._send(200, path.read_bytes(), "text/plain; charset=utf-8", SNAPSHOT_CSP, {"Content-Disposition": f'attachment; filename="{sha}.txt"'})

    def api_research(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        body = self._body()
        if set(body) != {"org"}:
            raise HttpError(400, "invalid_request", "Send only an organisation number")
        org = valid_org(body["org"] if isinstance(body["org"], str) else "")
        self.app.research_limit.check()
        job, created = self.app.research.submit(org)
        self._json(202 if created else 200, job.public())

    def job(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        self._json(200, self.app.research.get(valid_job_id(match.group(1))).public())

    def cancel(self, match: re.Match[str], query: dict[str, list[str]]) -> None:
        self._body()
        self._json(200, self.app.research.cancel(valid_job_id(match.group(1))).public())


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, app: App, host: str = "127.0.0.1", port: int = 8765, *, allow_remote: bool = False):
        if host not in ("127.0.0.1", "localhost") and not allow_remote:
            raise ValueError("binding to a non-loopback address needs --allow-remote")
        self.app = app
        self.extra_hosts: tuple[str, ...] = () if host in ("127.0.0.1", "localhost") else (host,)
        super().__init__((host, port), Handler)
