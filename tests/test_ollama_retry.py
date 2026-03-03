"""Unit tests for OllamaAdapter retry logic — no network required."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx
from superbot.adapters.ollama import OllamaAdapter


class TestOllamaAdapterRetry(unittest.TestCase):
    def setUp(self):
        self.adapter = OllamaAdapter("http://fake-host:11434", timeout=5, retries=2, retry_delay=0)

    def test_success_on_first_attempt(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "hello"}
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = self.adapter.generate("model-x", "hi")
        self.assertEqual(result, "hello")
        self.assertEqual(mock_post.call_count, 1)

    def test_retries_on_connect_timeout(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "ok"}
        with patch("httpx.post", side_effect=[
            httpx.ConnectTimeout("timeout"),
            mock_resp,
        ]) as mock_post:
            result = self.adapter.generate("model-x", "hi")
        self.assertEqual(result, "ok")
        self.assertEqual(mock_post.call_count, 2)

    def test_retries_on_read_timeout(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "ok after read timeout"}
        with patch("httpx.post", side_effect=[
            httpx.ReadTimeout("read timed out"),
            mock_resp,
        ]) as mock_post:
            result = self.adapter.generate("model-x", "hi")
        self.assertEqual(result, "ok after read timeout")
        self.assertEqual(mock_post.call_count, 2)

    def test_raises_after_all_retries_exhausted(self):
        with patch("httpx.post", side_effect=httpx.ConnectTimeout("timeout")):
            with self.assertRaises(httpx.ConnectTimeout):
                self.adapter.generate("model-x", "hi")

    def test_retries_on_remote_protocol_error(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "recovered"}
        with patch("httpx.post", side_effect=[
            httpx.RemoteProtocolError("disconnected"),
            httpx.RemoteProtocolError("disconnected"),
            mock_resp,
        ]):
            result = self.adapter.generate("model-x", "hi")
        self.assertEqual(result, "recovered")

    def test_non_retryable_error_raises_immediately(self):
        with patch("httpx.post", side_effect=ValueError("unexpected")):
            with self.assertRaises(ValueError):
                self.adapter.generate("model-x", "hi")

    def test_health_returns_true_on_success(self):
        mock_resp = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            self.assertTrue(self.adapter.health())

    def test_health_returns_false_on_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectTimeout("timeout")):
            self.assertFalse(self.adapter.health())


if __name__ == "__main__":
    unittest.main()
