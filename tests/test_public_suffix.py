"""Phase 8: the public suffix list is the pinned bundled snapshot; no download, no cache write."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = r"""
import json, os, socket, sys
attempts = []
def blocked(*args, **kwargs):
    attempts.append(repr(args)[:120])
    raise OSError("network blocked in test")
socket.socket.connect = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
sys.path.insert(0, sys.argv[1])
from norway_company_agent.website import _registered_domain
import norway_company_agent.pipeline  # the whole research stack imports without a download
cases = {url: _registered_domain(url) for url in ("https://www.fjordtest.no/om-oss", "https://shop.example.co.uk/", "https://a.b.kommune.no/", "https://x.blogspot.com/")}
print(json.dumps({"cases": cases, "attempts": attempts}))
"""


class PublicSuffixTests(unittest.TestCase):
    def test_no_network_and_no_cache_when_parsing_domains(self):
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home, "XDG_CACHE_HOME": str(Path(home) / "cache"), "TLDEXTRACT_CACHE": str(Path(home) / "tld-cache")}
            completed = subprocess.run([sys.executable, "-c", PROBE, str(ROOT / "src")], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            result = json.loads(completed.stdout)
            self.assertEqual(result["attempts"], [], "no network attempt (publicsuffix.org or GitHub)")
            self.assertEqual(result["cases"]["https://www.fjordtest.no/om-oss"], "fjordtest.no")
            self.assertEqual(result["cases"]["https://shop.example.co.uk/"], "example.co.uk")
            self.assertEqual(result["cases"]["https://x.blogspot.com/"], "blogspot.com", "private PSL section stays off, as before")
            written = [str(path) for path in Path(home).rglob("*")]
            self.assertEqual(written, [], "no suffix-list cache written")

    def test_snapshot_is_the_pinned_one(self):
        import tldextract

        snapshot = Path(tldextract.__file__).with_name(".tld_set_snapshot").read_bytes()
        self.assertEqual(tldextract.__version__, "5.3.2")
        self.assertIn(b"VERSION: 2025-04-07_15-51-09_UTC", snapshot)
        self.assertEqual(hashlib.sha256(snapshot).hexdigest(), "b69315c085d53972724b8f2df111ffc329b0c84fe0a47d62c8c91655cc774a38",
                         "update docs/dependencies.md when the pinned snapshot changes")
        pyproject = (ROOT / "pyproject.toml").read_text()
        self.assertIn('"tldextract==5.3.2"', pyproject)


if __name__ == "__main__":
    unittest.main()
