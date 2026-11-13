"""V3.1.1: the test modules written for V3.1 and earlier pin V3.1's news classification on synthetic posts (a "Ny avtale
med kommunen" blog post must publish). They run with SIGNALPOST_NEWS_PUBLICATION=anchored, which reproduces V3.1's news
output exactly. Modules for V3.1.1 run the default announcement tier. `scripts/run_suite_default_tier.sh` runs the
whole suite on the default tier to list exactly which V3.1 expectations the tier changes."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

DEFAULT_TIER_MODULES = {"test_v311_rescore.py"}


@pytest.fixture(autouse=True)
def _news_publication_tier(request, monkeypatch):
    if os.environ.get("SIGNALPOST_TEST_DEFAULT_TIER") == "1":
        yield
        return
    if Path(str(request.node.fspath)).name not in DEFAULT_TIER_MODULES:
        monkeypatch.setenv("SIGNALPOST_NEWS_PUBLICATION", "anchored")
    else:
        monkeypatch.delenv("SIGNALPOST_NEWS_PUBLICATION", raising=False)
    yield
