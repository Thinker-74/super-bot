"""Unit tests for GitHub context builder — no network required."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superbot.main import _build_github_context


class TestBuildGithubContext(unittest.TestCase):
    def _mock_gh(self, issues):
        gh = MagicMock()
        gh._default_repo = "owner/repo"
        gh.list_issues.return_value = issues
        return gh

    def test_empty_when_no_issues(self):
        gh = self._mock_gh([])
        self.assertEqual(_build_github_context(gh, "owner/repo"), "")

    def test_contains_issue_title(self):
        gh = self._mock_gh([{"number": 1, "title": "Fix the bug", "body": "Details here"}])
        ctx = _build_github_context(gh, "owner/repo")
        self.assertIn("Fix the bug", ctx)
        self.assertIn("#1", ctx)

    def test_contains_repo_name(self):
        gh = self._mock_gh([{"number": 1, "title": "T", "body": ""}])
        ctx = _build_github_context(gh, "owner/repo")
        self.assertIn("owner/repo", ctx)

    def test_body_truncated_to_200_chars(self):
        long_body = "x" * 300
        gh = self._mock_gh([{"number": 1, "title": "T", "body": long_body}])
        ctx = _build_github_context(gh, "owner/repo")
        self.assertNotIn("x" * 201, ctx)

    def test_none_body_handled(self):
        gh = self._mock_gh([{"number": 1, "title": "T", "body": None}])
        ctx = _build_github_context(gh, "owner/repo")
        self.assertIn("#1", ctx)

    def test_multiple_issues(self):
        gh = self._mock_gh([
            {"number": 1, "title": "First", "body": ""},
            {"number": 2, "title": "Second", "body": ""},
        ])
        ctx = _build_github_context(gh, "owner/repo")
        self.assertIn("#1", ctx)
        self.assertIn("#2", ctx)

    def test_returns_empty_on_exception(self):
        gh = MagicMock()
        gh._default_repo = "owner/repo"
        gh.list_issues.side_effect = Exception("network error")
        ctx = _build_github_context(gh, "owner/repo")
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
