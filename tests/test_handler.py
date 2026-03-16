"""Unit tests for the gateway handler."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superbot.gateway.handler import Request, normalize


class TestNormalize(unittest.TestCase):
    def test_basic(self):
        r = normalize({"text": "hello"})
        self.assertEqual(r.text, "hello")
        self.assertEqual(r.mode, "")
        self.assertIsNone(r.repo)
        self.assertEqual(r.context, {})

    def test_all_fields(self):
        r = normalize({"text": "hi", "mode": "coding", "repo": "owner/repo", "context": {"k": 1}})
        self.assertEqual(r.mode, "coding")
        self.assertEqual(r.repo, "owner/repo")
        self.assertEqual(r.context, {"k": 1})

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            normalize({"text": ""})

    def test_missing_text_raises(self):
        with self.assertRaises(ValueError):
            normalize({})

    def test_whitespace_text_raises(self):
        with self.assertRaises(ValueError):
            normalize({"text": "   "})

    def test_empty_mode_preserved(self):
        # handler stores whatever mode is passed; Router handles fallback
        r = normalize({"text": "hi", "mode": ""})
        self.assertEqual(r.mode, "")

    def test_none_repo_stays_none(self):
        r = normalize({"text": "hi", "repo": None})
        self.assertIsNone(r.repo)

    def test_empty_repo_becomes_none(self):
        r = normalize({"text": "hi", "repo": ""})
        self.assertIsNone(r.repo)


if __name__ == "__main__":
    unittest.main()
