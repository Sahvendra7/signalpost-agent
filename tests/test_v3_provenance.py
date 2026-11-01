"""V3 §B8: code-version stamping identifies the source that produced an output."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import provenance  # noqa: E402
from norway_company_agent.contract import build_envelope, validate_envelope  # noqa: E402


class CodeVersionTests(unittest.TestCase):
    def copy_tree(self, target: Path) -> Path:
        shutil.copytree(ROOT / "src", target / "src", ignore=shutil.ignore_patterns("__pycache__"))
        (target / "scripts").mkdir()
        for name in provenance.RUNTIME_FILES:
            source = ROOT / name
            (target / name).write_bytes(source.read_bytes())
        return target

    def test_source_hash_is_deterministic_and_changes_with_the_code(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.copy_tree(Path(raw))
            first = provenance.source_sha256(root)
            self.assertEqual(first, provenance.source_sha256(root))
            module = root / "src" / "norway_company_agent" / "claims.py"
            module.write_text(module.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
            self.assertNotEqual(first, provenance.source_sha256(root))

    def test_without_git_the_git_fields_are_null_and_the_source_hash_is_present(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.copy_tree(Path(raw))
            value = provenance.code_version(root)
            self.assertIsNone(value["git_commit"])
            self.assertIsNone(value["git_dirty"])
            self.assertTrue(provenance.valid_code_version(value))
            self.assertEqual(value["source_sha256"], provenance.source_sha256(root))

    def test_in_this_checkout_the_commit_is_a_full_sha(self):
        value = provenance.code_version()
        if (ROOT / ".git").exists() and shutil.which("git"):
            self.assertRegex(value["git_commit"] or "", r"^[0-9a-f]{40}$")
            self.assertIn(value["git_dirty"], (True, False))
        self.assertTrue(provenance.valid_code_version(value))

    def test_envelopes_carry_the_code_version_and_malformed_values_are_findings(self):
        envelope = build_envelope("911771098", run={"run_id": "t", "started_at": "2026-11-01T00:00:00Z", "completed_at": "2026-11-01T00:00:00Z", "terminal_status": "completed"}, claims=[], evidence=[])
        self.assertEqual(envelope["run"]["code_version"], provenance.code_version())
        self.assertEqual(validate_envelope(envelope), [])
        envelope["run"]["code_version"] = {"source_sha256": "nope"}
        self.assertIn("invalid_code_version", [item["code"] for item in validate_envelope(envelope)])
        del envelope["run"]["code_version"]
        self.assertEqual(validate_envelope(envelope), [], "older envelopes without the field still validate")


if __name__ == "__main__":
    unittest.main()
