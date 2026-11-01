"""On-demand research of one company (V3 design §B11).

The manager runs the same `run_batch` as the command line, for a single input row, with a 120-second deadline. At
most two research threads are live at once, counting *orphans*: when a job is cancelled or hits its deadline,
`run_batch` returns at once with what it has, but the worker thread that was researching the company may still be
finishing its current request. Such a thread keeps a slot until its research ends (its profile gains `run_metrics`)
or ORPHAN_SECONDS pass. Up to 20 jobs wait in a queue; a second request for a company that is already queued or
running returns the existing job.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ..inputs import InputRow
from ..pipeline import run_batch
from .security import HttpError
from .store import Store

LOG = logging.getLogger("signalpost.app")
ACTIVE = ("queued", "running", "cancelling")
TERMINAL = ("completed", "partial", "failed", "cancelled")
ORPHAN_SECONDS = 300.0
SOURCE_FAILED = ("source_error", "submission_error", "blocked_robots", "blocked_policy", "carried_forward")  # batch.evidence_terminal_state

ERROR_MESSAGES = {
    "not_in_registry": "This organisation number is not in the Central Coordinating Register for Legal Entities.",
    "registry_unreachable": "The registry could not be reached. Nothing was changed; try again later.",
    "deadline_exceeded": "Research did not finish within its time limit. The facts found so far are shown.",
    "cancelled": "Research was cancelled.",
    "internal_error": "Research failed unexpectedly. Nothing was saved.",
}


def stage_of(profile: dict[str, Any] | None) -> str:
    """A plain stage name from what the research has fetched so far."""
    records = (profile or {}).get("evidence") or {}
    if "site_research" in records:
        return "Preparing the profile"
    if "website" in records:
        return "Reading the company's website"
    if "registry_live" in records:
        return "Reading official sources (roles, accounts, subunits)"
    return "Looking up the registry"


@dataclass
class Job:
    id: str
    org: str
    state: str = "queued"
    stage: str = "Waiting for a free research slot"
    created: float = field(default_factory=time.monotonic)
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    run_id: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    progress: dict[str, dict[str, Any]] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        now = time.monotonic()
        profile = self.progress.get(self.org)
        stage = stage_of(profile) if self.state == "running" else self.stage
        elapsed = (self.finished or now) - (self.started or now)
        return {"id": self.id, "org": self.org, "state": self.state, "stage": stage, "elapsed_s": round(max(0.0, elapsed), 1),
                "result": self.result, "error": self.error, "message": ERROR_MESSAGES.get(self.error or "") if self.error else None}


class ResearchManager:
    def __init__(self, store: Store, *, run: Callable[..., dict[str, Any]] = run_batch, run_kwargs: dict[str, Any] | None = None,
                 max_live: int = 2, max_queue: int = 20, deadline: float = 120.0, clock=time.monotonic):
        self.store, self.run, self.run_kwargs = store, run, dict(run_kwargs or {})
        self.max_live, self.max_queue, self.deadline, self.clock = max_live, max_queue, deadline, clock
        self.jobs: dict[str, Job] = {}
        self._queue: deque[Job] = deque()
        self._threads: list[threading.Thread] = []
        self._orphans: list[tuple[float, dict[str, dict[str, Any]], str]] = []  # (since, progress, org)
        self._lock = threading.RLock()

    # ---- slots ---------------------------------------------------------------------------------------------
    def live(self) -> int:
        with self._lock:
            self._threads = [thread for thread in self._threads if thread.is_alive()]
            now = self.clock()
            self._orphans = [(since, progress, org) for since, progress, org in self._orphans
                             if now - since < ORPHAN_SECONDS and "run_metrics" not in (progress.get(org) or {"run_metrics": 1})]
            return len(self._threads) + len(self._orphans)

    def _pump(self) -> None:
        with self._lock:
            while self._queue and self.live() < self.max_live:
                job = self._queue.popleft()
                job.state, job.started = "running", self.clock()
                thread = threading.Thread(target=self._work, args=(job,), name=f"research-{job.org}", daemon=True)
                self._threads.append(thread)
                thread.start()

    # ---- API -----------------------------------------------------------------------------------------------
    def submit(self, org: str) -> tuple[Job, bool]:
        with self._lock:
            for job in self.jobs.values():
                if job.org == org and job.state in ACTIVE:
                    return job, False
            if len(self._queue) >= self.max_queue:
                raise HttpError(429, "queue_full", "Too many companies are waiting to be researched; try again shortly")
            job = Job(id=secrets.token_hex(16), org=org)
            self.jobs[job.id] = job
            self._queue.append(job)
            if len(self.jobs) > 500:  # forget the oldest finished jobs
                for old in [item for item in self.jobs.values() if item.state in TERMINAL][:100]:
                    self.jobs.pop(old.id, None)
        self._pump()
        return job, True

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise HttpError(404, "unknown_job", "Unknown research job")
        self._pump()  # a slot may have been freed by an orphan finishing
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        with self._lock:
            if job.state == "queued":
                self._queue.remove(job)
                job.state, job.error, job.finished, job.stage = "cancelled", "cancelled", self.clock(), "Finished"
            elif job.state == "running":
                job.state = "cancelling"
                job.stop_event.set()
        return job

    # ---- worker --------------------------------------------------------------------------------------------
    def _work(self, job: Job) -> None:
        run_id = "app-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + job.id[:6]
        job.run_id = run_id
        baseline = self.store.baseline(job.org)
        # One company: the batch "degrade when it will not fit" rule starts at 2 x grace before the deadline, so the
        # grace window must be well under half the deadline or every on-demand research would skip the website.
        try:
            outcome = self.run([InputRow(0, job.org, job.org)], run_id=run_id, workers=1, deadline_seconds=self.deadline,
                               grace_seconds=min(15.0, self.deadline / 4), stop_event=job.stop_event, progress=job.progress,
                               previous_envelopes={job.org: baseline} if baseline else None, snapshot_root=self.store.snapshot_root, **self.run_kwargs)
            envelope = outcome["envelopes"][0]
            stop_reason = ((outcome.get("report") or {}).get("deadline") or {}).get("stop_reason")
            if stop_reason in ("interrupted", "deadline"):
                with self._lock:
                    self._orphans.append((self.clock(), job.progress, job.org))
            self._finish(job, envelope, outcome, stop_reason)
        except Exception:  # noqa: BLE001 — logged here; the response carries only a code
            LOG.exception("research of %s failed", job.org)
            job.state, job.error = "failed", "internal_error"
        finally:
            job.finished, job.stage = self.clock(), "Finished"
            threading.Thread(target=self._pump, daemon=True).start()  # this thread is still alive: pump from another

    def _finish(self, job: Job, envelope: dict[str, Any], outcome: dict[str, Any], stop_reason: str | None) -> None:
        run = envelope.get("run") or {}
        modules = envelope.get("modules") or {}
        failed = sorted(name for name, state in modules.items() if (state or {}).get("state") in SOURCE_FAILED)
        job.result = {"terminal_status": run.get("terminal_status"), "partial_sources": failed, "run_id": job.run_id,
                      "company_status": (envelope.get("company_status") or {}).get("state")}
        if job.stop_event.is_set():
            job.state, job.error = "cancelled", "cancelled"  # nothing is saved: a cancelled run is not a profile
            return
        if run.get("terminal_status") != "completed":
            codes = {error.get("code") for error in envelope.get("errors") or []}
            registry = modules.get("registry_live") or {}
            if "registry_live" in modules and registry.get("state") == "not_found":
                job.error = "not_in_registry"
            elif registry.get("state") in SOURCE_FAILED or "registry_unreachable" in codes:
                job.error = "registry_unreachable"
            else:
                job.error = "internal_error"
            job.state = "failed"
            return
        profile = (outcome.get("profiles") or [None])[0]
        self.store.add_research(job.org, job.run_id or "run", envelope, profile)
        if stop_reason == "deadline":
            job.state, job.error = "partial", "deadline_exceeded"
        else:
            job.state = "partial" if failed else "completed"
