"""Which code produced an output (V3 §B8): stamped into every envelope's run block, the run report and run history.

`source_sha256` is authoritative and always present: a SHA-256 over the sorted relative paths and bytes of the runtime
sources (src/**/*.py, the batch entry script, pyproject.toml, uv.lock). It identifies the code even in a clean-room
copy without git. The git fields are best-effort context: they come from `git` run with a fixed argument list (no
shell, no request-derived input, 5 s timeout) and are null when `.git` is absent or git fails.
"""
from __future__ import annotations

import hashlib
import subprocess
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_VERSION = "0.3.0"
RUNTIME_FILES = ("scripts/run_competition_batch.py", "pyproject.toml", "uv.lock")
_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _runtime_paths(root: Path) -> list[Path]:
    paths = sorted(path for path in (root / "src").rglob("*.py") if "__pycache__" not in path.parts)
    paths += [root / name for name in RUNTIME_FILES if (root / name).is_file()]
    return paths


def source_sha256(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in _runtime_paths(root):
        relative = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big") + relative + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def code_version(root: Path = ROOT) -> dict[str, Any]:
    """{source_sha256, package_version, git_commit, git_dirty}; computed once per process and root."""
    key = str(root)
    with _lock:
        if key in _cache:
            return dict(_cache[key])
        commit = (_git(root, "rev-parse", "HEAD") or "").strip() or None
        status = _git(root, "status", "--porcelain", "--", "src", *RUNTIME_FILES)
        value = {
            "source_sha256": source_sha256(root),
            "package_version": PACKAGE_VERSION,
            "git_commit": commit if commit and len(commit) == 40 else None,
            "git_dirty": None if status is None else bool(status.strip()),
        }
        _cache[key] = value
        return dict(value)


def valid_code_version(value: Any) -> bool:
    """Shape check used by the contract validator (the field is optional; when present it must be well formed)."""
    if not isinstance(value, dict):
        return False
    sha = value.get("source_sha256")
    commit = value.get("git_commit")
    return (isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)
            and (commit is None or (isinstance(commit, str) and len(commit) == 40))
            and value.get("git_dirty") in (True, False, None))
