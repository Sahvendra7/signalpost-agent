"""Run history (V3 design §B8): each documented run keeps its published envelopes, profiles and report, so the next run
can say what changed against what was actually *published*, and nothing earlier is lost.

Layout: <history_dir>/<run_id>/{envelopes.jsonl.gz, profiles.jsonl.gz, report.json, manifest.json}. A run is written
to a temporary directory, its manifest last, then renamed into place, so an interrupted write never looks like a run.
A run is `complete` only if the batch did not stop early; incomplete runs are kept for the record but never used as
a baseline. Pruning keeps the newest N runs and always the newest two complete runs, and only ever deletes directories
that carry this module's manifest marker.
"""
from __future__ import annotations

import gzip
import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any, Iterable

MARKER = "signalpost-run-history-v1"
DEFAULT_KEEP = 10


def _safe_name(run_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(run_id))[:80].strip("._")
    return cleaned or "run"


def _write_gz(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_is_complete(report: dict[str, Any], envelopes: list[dict[str, Any]]) -> bool:
    stop = ((report or {}).get("deadline") or {}).get("stop_reason")
    return stop in (None, "grace_window") and bool(((report or {}).get("validation") or {}).get("passed", True)) and len(envelopes) == (report or {}).get("emitted_envelopes", len(envelopes))


def write_run(history_dir: str | Path, run_id: str, envelopes: list[dict[str, Any]], profiles: list[dict[str, Any]], report: dict[str, Any]) -> Path:
    root = Path(history_dir)
    root.mkdir(parents=True, exist_ok=True)
    name = _safe_name(run_id)
    target = root / name
    if target.exists():
        name = f"{name}-{secrets.token_hex(3)}"
        target = root / name
    temporary = root / f".tmp-{name}-{secrets.token_hex(4)}"
    temporary.mkdir()
    try:
        _write_gz(temporary / "envelopes.jsonl.gz", envelopes)
        _write_gz(temporary / "profiles.jsonl.gz", profiles)
        (temporary / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        manifest = {
            "marker": MARKER, "run_id": run_id, "directory": name, "code_version": report.get("code_version"),
            "started_at": report.get("started_at"), "completed_at": report.get("completed_at"), "complete": run_is_complete(report, envelopes),
            "stop_reason": (report.get("deadline") or {}).get("stop_reason"), "envelopes": len(envelopes),
            "organisations": sorted({str(item.get("organisation_number")) for item in envelopes if item.get("organisation_number")}),
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def runs(history_dir: str | Path) -> list[dict[str, Any]]:
    """Manifests of finished runs, newest first. Temporary and foreign directories are ignored."""
    root = Path(history_dir)
    found = []
    if not root.is_dir():
        return found
    for path in root.iterdir():
        if path.name.startswith(".tmp-") or not path.is_dir():
            continue
        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("marker") == MARKER:
            found.append({**manifest, "path": str(path)})
    return sorted(found, key=lambda item: (str(item.get("completed_at") or ""), item["path"]), reverse=True)


def prune(history_dir: str | Path, keep: int = DEFAULT_KEEP) -> list[str]:
    """Delete runs beyond the newest `keep`, never one of the newest two complete runs; returns deleted paths."""
    listed = runs(history_dir)
    protected = {item["path"] for item in [run for run in listed if run.get("complete")][:2]}
    deleted = []
    for item in listed[max(0, keep):]:
        if item["path"] in protected:
            continue
        path = Path(item["path"])
        if (path / "manifest.json").is_file() and json.loads((path / "manifest.json").read_text(encoding="utf-8")).get("marker") == MARKER:
            shutil.rmtree(path)
            deleted.append(str(path))
    for stale in Path(history_dir).glob(".tmp-*"):  # an interrupted write: never a run
        shutil.rmtree(stale, ignore_errors=True)
    return deleted


def read_envelopes(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def baselines(history_dir: str | Path, organisations: Iterable[str], *, limit: int = DEFAULT_KEEP) -> dict[str, dict[str, Any]]:
    """For each organisation, its envelope in the newest complete run where its research completed."""
    return baseline_runs(history_dir, organisations, limit=limit)[0]


def baseline_runs(history_dir: str | Path, organisations: Iterable[str], *, limit: int = DEFAULT_KEEP) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """(envelopes, profiles): each organisation's envelope in the newest complete run where its research completed, and
    its profile from that same run. The profile is what outage carry-forward needs: without it, a source that fails in
    this run would look like a company change."""
    wanted = {str(org) for org in organisations if org}
    found: dict[str, dict[str, Any]] = {}
    source: dict[str, Path] = {}
    for item in [run for run in runs(history_dir) if run.get("complete")][:limit]:
        missing = wanted - set(found)
        if not missing:
            break
        if not missing & set(item.get("organisations") or []):
            continue
        for envelope in read_envelopes(Path(item["path"]) / "envelopes.jsonl.gz"):
            org = str(envelope.get("organisation_number") or "")
            if org in missing and (envelope.get("run") or {}).get("terminal_status") == "completed":
                found[org] = envelope
                source[org] = Path(item["path"])
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(set(source.values())):
        try:
            rows = read_envelopes(path / "profiles.jsonl.gz")
        except (OSError, ValueError):
            continue  # an unreadable profile file: no carry-forward for these companies, never a crash
        for profile in rows:
            org = str(profile.get("organisation_number") or "")
            if source.get(org) == path:
                profiles[org] = profile
    return found, profiles


def latest_by_org(envelopes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """An explicit --previous-envelopes file: the last completed envelope per organisation."""
    out: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        org = str(envelope.get("organisation_number") or "")
        if org and (envelope.get("run") or {}).get("terminal_status") == "completed":
            out[org] = envelope
    return out
