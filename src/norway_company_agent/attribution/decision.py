from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Decision:
    """One attribution decision: accepted or held, why (stable `code`), and a sentence a person can read (`basis`)."""

    accepted: bool
    code: str
    basis: str
    signals: tuple[Any, ...] = field(default=())

    def note(self) -> dict[str, str]:
        return {"code": self.code, "basis": self.basis}
