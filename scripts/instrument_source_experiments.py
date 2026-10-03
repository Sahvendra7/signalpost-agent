#!/usr/bin/env python3
"""Wire-level instrumentation wrapper for scripts/run_source_experiments.py (measurement only).

Runs the frozen experiment script unchanged, with urllib's OpenerDirector.open wrapped to log
every HTTP exchange: phase, host, status, bytes read, elapsed time, and whether it was a first
attempt, a retry of the same URL in the same thread, or a redirect hop. No research behaviour
changes; it only observes. Usage: same arguments as run_source_experiments.py, plus
--wire-log PATH (default <out>/wire-log.jsonl).

  logical request = first top-level open() of a URL in a thread (or after a success)
  attempt         = every top-level open()
  retry           = top-level open() of the same URL right after a failed attempt in that thread
  redirect hop    = nested open() issued by the redirect handler
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_lock = threading.Lock()
_local = threading.local()
_records: list[dict] = []
_phase = {"name": "setup", "started": time.monotonic()}
_phase_times: dict[str, float] = {}
_original_open = urllib.request.OpenerDirector.open


def set_phase(name: str) -> None:
    with _lock:
        now = time.monotonic()
        _phase_times[_phase["name"]] = _phase_times.get(_phase["name"], 0.0) + now - _phase["started"]
        _phase.update(name=name, started=now)


def _counting(obj, record):
    read = obj.read

    def wrapped(*args, **kwargs):
        data = read(*args, **kwargs)
        record["bytes"] += len(data or b"")
        return data

    try:
        obj.read = wrapped
    except AttributeError:
        pass
    return obj


def instrumented_open(self, fullurl, data=None, timeout=None, **kwargs):
    url = fullurl if isinstance(fullurl, str) else fullurl.full_url
    depth = getattr(_local, "depth", 0)
    if depth == 0:
        previous = getattr(_local, "last", None)
        kind = "retry" if previous and previous[0] == url and not previous[1] else "first"
    else:
        kind = "redirect"
    record = {"phase": _phase["name"], "host": urllib.parse.urlsplit(url).hostname, "url": url[:300], "kind": kind, "status": None, "bytes": 0, "error": None}
    started = time.monotonic()
    _local.depth = depth + 1
    try:
        response = _original_open(self, fullurl, data, timeout) if timeout is not None else _original_open(self, fullurl, data)
        record["status"] = getattr(response, "status", None) or response.getcode()
        ok = True
        return _counting(response, record)
    except urllib.error.HTTPError as exc:
        record["status"] = exc.code
        record["error"] = f"HTTP {exc.code}"
        ok = exc.code < 500 and exc.code != 429
        _counting(exc, record)
        raise
    except Exception as exc:
        record["error"] = type(exc).__name__
        ok = False
        raise
    finally:
        _local.depth = depth
        record["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        if depth == 0:
            _local.last = (url, ok)
        with _lock:
            _records.append(record)


def main() -> None:
    argv = sys.argv[1:]
    wire_log = None
    if "--wire-log" in argv:
        index = argv.index("--wire-log")
        wire_log = argv[index + 1]
        del argv[index:index + 2]
    out = argv[argv.index("--out") + 1] if "--out" in argv else "out/experiments"
    wire_path = Path(wire_log or Path(out) / "wire-log.jsonl")

    urllib.request.OpenerDirector.open = instrumented_open
    spec = importlib.util.spec_from_file_location("run_source_experiments", ROOT / "scripts" / "run_source_experiments.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original_run_batch = module.run_batch

    def run_batch(*args, **kwargs):
        set_phase("baseline")
        try:
            result = original_run_batch(*args, **kwargs)
        finally:
            set_phase("between")
        # The frozen script keeps envelopes/profiles in memory only; persist them for quality checks.
        out_dir = Path(out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for key in ("envelopes", "profiles"):
            with (out_dir / f"baseline-{key}.jsonl").open("w", encoding="utf-8") as handle:
                for item in result.get(key) or []:
                    handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        return result

    original_pmap = module.pmap

    def pmap(function, items, workers):
        names = set(getattr(function, "__code__", None).co_names if hasattr(function, "__code__") else ())
        if function.__name__ == "discover":
            phase = "site_discovery"
        elif "brreg_activity" in names:
            phase = "brreg_activity"
        elif "filings" in names:
            phase = "filings"
        elif "nav_jobs" in names:
            phase = "nav_jobs"
        else:
            phase = "other"
        set_phase(phase)
        try:
            return original_pmap(function, items, workers)
        finally:
            set_phase("between")

    module.run_batch = run_batch
    module.pmap = pmap
    sys.argv = [str(ROOT / "scripts" / "run_source_experiments.py"), *argv]
    started = time.monotonic()
    try:
        module.main()
    finally:
        set_phase("done")
        wire_path.parent.mkdir(parents=True, exist_ok=True)
        with wire_path.open("w", encoding="utf-8") as handle:
            for record in _records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        summary: dict = {"total_wall_s": round(time.monotonic() - started, 2), "phase_wall_s": {k: round(v, 2) for k, v in _phase_times.items()}, "phases": {}}
        for record in _records:
            phase = summary["phases"].setdefault(record["phase"], {"logical_requests": 0, "attempts": 0, "retries": 0, "redirect_hops": 0, "bytes": 0, "transport_errors": 0, "status": {}, "hosts": {}})
            if record["kind"] == "redirect":
                phase["redirect_hops"] += 1
            else:
                phase["attempts"] += 1
                phase["logical_requests"] += record["kind"] == "first"
                phase["retries"] += record["kind"] == "retry"
            phase["bytes"] += record["bytes"]
            phase["transport_errors"] += record["status"] is None
            phase["status"][str(record["status"])] = phase["status"].get(str(record["status"]), 0) + 1
            phase["hosts"][record["host"] or "?"] = phase["hosts"].get(record["host"] or "?", 0) + 1
        (wire_path.parent / "wire-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
