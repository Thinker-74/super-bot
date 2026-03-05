"""Unit tests for the CLI entrypoint (main.py) — no network required."""
from __future__ import annotations

import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superbot.main import build_parser, main


class TestBuildParser(unittest.TestCase):
    """Argument parsing (no I/O)."""

    def test_text_mode(self):
        args = build_parser().parse_args(["--text", "hello", "--mode", "coding"])
        self.assertEqual(args.text, "hello")
        self.assertEqual(args.mode, "coding")

    def test_interactive_flag(self):
        args = build_parser().parse_args(["--interactive"])
        self.assertTrue(args.interactive)

    def test_short_interactive(self):
        args = build_parser().parse_args(["-i"])
        self.assertTrue(args.interactive)

    def test_process_issue(self):
        args = build_parser().parse_args(["--process-issue", "5"])
        self.assertEqual(args.process_issue, 5)

    def test_list_models(self):
        args = build_parser().parse_args(["--list-models"])
        self.assertTrue(args.list_models)

    def test_stream_flag(self):
        args = build_parser().parse_args(["--text", "hi", "--stream"])
        self.assertTrue(args.stream)

    def test_short_stream(self):
        args = build_parser().parse_args(["--text", "hi", "-s"])
        self.assertTrue(args.stream)

    def test_repo_flag(self):
        args = build_parser().parse_args(["--text", "hi", "--repo", "owner/repo"])
        self.assertEqual(args.repo, "owner/repo")

    def test_mutual_exclusion(self):
        # --interactive and --orchestrate are mutually exclusive
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--interactive", "--orchestrate"])


class TestMainDispatch(unittest.TestCase):
    """Test that main() dispatches correctly to adapters (all mocked)."""

    @patch("superbot.main._make_ollama")
    def test_single_shot_returns_0(self, mock_ollama_factory):
        adapter = MagicMock()
        adapter.generate.return_value = "mocked response"
        mock_ollama_factory.return_value = adapter

        buf = StringIO()
        with patch("sys.stdout", buf):
            rc = main(["--text", "hello"])

        self.assertEqual(rc, 0)
        adapter.generate.assert_called_once()
        self.assertIn("mocked response", buf.getvalue())

    def test_no_args_returns_1(self):
        with patch("sys.stderr", StringIO()):
            rc = main([])
        self.assertEqual(rc, 1)

    @patch("superbot.main._make_ollama")
    def test_single_shot_with_mode(self, mock_ollama_factory):
        adapter = MagicMock()
        adapter.generate.return_value = "code output"
        mock_ollama_factory.return_value = adapter

        with patch("sys.stdout", StringIO()):
            rc = main(["--text", "write code", "--mode", "coding"])

        self.assertEqual(rc, 0)
        call_kwargs = adapter.generate.call_args
        self.assertEqual(call_kwargs[1]["model"], "qwen2.5-coder:14b")

    @patch("superbot.main._make_ollama")
    def test_adapter_error_returns_1(self, mock_ollama_factory):
        adapter = MagicMock()
        adapter.generate.side_effect = RuntimeError("connection failed")
        mock_ollama_factory.return_value = adapter

        with patch("sys.stderr", StringIO()):
            rc = main(["--text", "hello"])

        self.assertEqual(rc, 1)


class TestListModels(unittest.TestCase):

    @patch("httpx.get")
    def test_list_models_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "deepseek-r1:7b", "size": 7_000_000_000},
                {"name": "qwen2.5-coder:14b", "size": 14_000_000_000},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        buf = StringIO()
        with patch("sys.stdout", buf):
            rc = main(["--list-models"])

        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("deepseek-r1:7b", output)
        self.assertIn("qwen2.5-coder:14b", output)

    @patch("httpx.get", side_effect=Exception("unreachable"))
    def test_list_models_failure(self, _):
        with patch("sys.stderr", StringIO()):
            rc = main(["--list-models"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
