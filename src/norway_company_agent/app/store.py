"""The app's company index (V3 design §B11).

Two kinds of envelopes are indexed:
- imported envelope files (`--envelopes`), read once and never modified;
- envelopes researched in the app, stored under `<data_dir>/research/<org>/<run_id>/` (directories 0700, files 0600,
  written to a temporary file and renamed).

Captured source bytes are served only for content hashes that appear in indexed evidence, and only from the
configured snapshot directories.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..attribution.names import fold
from ..contract import snapshot_relative_path
from ..history import read_envelopes
from ..viewer import _identity
from .security import ORG, SHA256

STALE_DAYS = 30
MAX_RESULTS = 20
_RUN_DIR = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _write_private(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class Store:
    def __init__(self, data_dir: str | Path, imports: Iterable[str | Path] = (), snapshot_dirs: Iterable[str | Path] = ()):
        self.data_dir = Path(data_dir).resolve()
        self.research_dir = self.data_dir / "research"
        self.snapshot_root = self.data_dir / "snapshots"
        for directory in (self.data_dir, self.research_dir, self.snapshot_root):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        self.snapshot_dirs = [self.snapshot_root] + [Path(item).resolve() for item in snapshot_dirs]
        self._lock = threading.Lock()
        self._runs: dict[str, list[dict[str, Any]]] = {}  # org -> envelopes, oldest first
        self._hashes: set[str] = set()
        self.imported = 0
        for path in imports:
            for envelope in read_envelopes(path):
                self._index(envelope, "imported")
                self.imported += 1
        for org_dir in sorted(self.research_dir.iterdir()):
            if not ORG.fullmatch(org_dir.name):
                continue
            for run_dir in sorted(org_dir.iterdir()):
                try:
                    envelope = json.loads((run_dir / "envelope.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue  # an interrupted write leaves no envelope.json: not a run
                self._index(envelope, "researched", run_dir)

    def _index(self, envelope: dict[str, Any], source: str, path: Path | None = None) -> None:
        org = str(envelope.get("organisation_number") or "")
        if not ORG.fullmatch(org):
            return  # an input row that never resolved to a company is not searchable
        envelope = {**envelope, "_source": source, "_path": str(path) if path else None}
        with self._lock:
            runs = self._runs.setdefault(org, [])
            runs.append(envelope)
            runs.sort(key=lambda item: str((item.get("run") or {}).get("started_at") or ""))
            for item in envelope.get("evidence") or []:
                if SHA256.fullmatch(str(item.get("content_sha256") or "")):
                    self._hashes.add(item["content_sha256"])

    # ---- queries -------------------------------------------------------------------------------------------
    def __contains__(self, org: str) -> bool:
        return org in self._runs

    def latest(self, org: str) -> dict[str, Any] | None:
        with self._lock:
            runs = self._runs.get(org) or []
            return runs[-1] if runs else None

    def baseline(self, org: str) -> dict[str, Any] | None:
        """The newest envelope whose research completed: what a re-check is compared with."""
        with self._lock:
            for envelope in reversed(self._runs.get(org) or []):
                if (envelope.get("run") or {}).get("terminal_status") == "completed":
                    return envelope
        return None

    def baseline_profile(self, envelope: dict[str, Any] | None) -> dict[str, Any] | None:
        """The profile stored with a researched run: outage carry-forward needs it (imported runs have none)."""
        path = (envelope or {}).get("_path")
        if not path:
            return None
        try:
            return json.loads((Path(path) / "profile.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def all_latest(self) -> list[dict[str, Any]]:
        with self._lock:
            orgs = sorted(self._runs)
        return [self.latest(org) for org in orgs]

    def summary(self, org: str, now: datetime | None = None) -> dict[str, Any]:
        envelope = self.latest(org) or {}
        run = envelope.get("run") or {}
        researched = run.get("completed_at") or run.get("started_at")
        when = _parse_time(researched) if researched else None
        age = ((now or datetime.now(timezone.utc)) - when).days if when else None
        return {
            "org": org, "name": _identity(envelope).get("legal_name") or "", "researched_at": researched, "terminal_status": run.get("terminal_status"),
            "company_status": (envelope.get("company_status") or {}).get("state"), "stale": age is not None and age > STALE_DAYS, "age_days": age,
            "source": envelope.get("_source"),
        }

    def search(self, kind: str, query: str) -> list[dict[str, Any]]:
        if kind == "number":
            return [self.summary(query)] if query in self._runs else []
        wanted = _words(query)
        if not wanted:
            return []
        scored = []
        with self._lock:
            orgs = list(self._runs)
        for org in orgs:
            name = _identity(self.latest(org) or {}).get("legal_name") or ""
            words = _words(name)
            if all(any(word.startswith(term) for word in words) for term in wanted):
                exact = " ".join(words) == " ".join(wanted)
                scored.append((0 if exact else 1, len(words), name, org))
        return [self.summary(org) for *_, org in sorted(scored)[:MAX_RESULTS]]

    # ---- writes --------------------------------------------------------------------------------------------
    def add_research(self, org: str, run_id: str, envelope: dict[str, Any], profile: dict[str, Any] | None) -> Path:
        if not ORG.fullmatch(org) or not _RUN_DIR.fullmatch(run_id):
            raise ValueError("invalid organisation number or run id")
        target = self.research_dir / org / run_id
        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target.parent, 0o700)
        os.chmod(target, 0o700)
        if profile is not None:
            _write_private(target / "profile.json", json.dumps(profile, ensure_ascii=False, default=str))
        _write_private(target / "envelope.json", json.dumps(envelope, ensure_ascii=False, default=str))  # last: marks the run complete
        self._index(envelope, "researched", target)
        return target

    # ---- captured bytes ------------------------------------------------------------------------------------
    def snapshot_path(self, sha: str) -> Path | None:
        if not SHA256.fullmatch(sha) or sha not in self._hashes:
            return None
        for root in self.snapshot_dirs:
            candidate = (root / snapshot_relative_path(sha)).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
        return None
