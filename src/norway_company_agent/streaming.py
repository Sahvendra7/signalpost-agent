"""Durable append-only JSONL output: one line per terminal result, flushed and fsynced on write."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class JsonlStream:
    """Truncates `path` on open; every `append` is one complete line, flushed to the OS and fsynced.

    A process killed between appends leaves only complete lines. A kill during a write can at most
    leave one truncated last line, which `read_jsonl_tolerant` skips."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle = path.open("w", encoding="utf-8")
        self.lines = 0

    def append(self, row: dict[str, Any]) -> None:
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
        with self._lock:
            self._handle.write(line)
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self.lines += 1

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.close()


def read_jsonl_tolerant(path: Path) -> list[dict[str, Any]]:
    """Read a possibly interrupted stream: complete JSON lines only."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
