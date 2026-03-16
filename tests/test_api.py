"""Unit tests for the FastAPI gateway — no network required."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient

from superbot.api.app import app

client = TestClient(app)


class TestHealthEndpoint(unittest.TestCase):

    @patch("superbot.api.app._get_adapter")
    def test_health_ok(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.health.return_value = True
        mock_adapter_factory.return_value = adapter

        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["ollama"])

    @patch("superbot.api.app._get_adapter")
    def test_health_ollama_down(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.health.return_value = False
        mock_adapter_factory.return_value = adapter

        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ollama"])


class TestModelsEndpoint(unittest.TestCase):

    @patch("superbot.api.app._get_adapter")
    def test_models_ok(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.list_models.return_value = [{"name": "qwen3:8b", "size_gb": 5.2}]
        mock_adapter_factory.return_value = adapter

        r = client.get("/models")
        self.assertEqual(r.status_code, 200)
        models = r.json()["models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["name"], "qwen3:8b")

    @patch("superbot.api.app._get_adapter")
    def test_models_ollama_down(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.list_models.side_effect = Exception("unreachable")
        mock_adapter_factory.return_value = adapter
        r = client.get("/models")
        self.assertEqual(r.status_code, 503)


class TestGenerateEndpoint(unittest.TestCase):

    @patch("superbot.api.app._get_adapter")
    def test_generate_ok(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.generate.return_value = "hello world"
        mock_adapter_factory.return_value = adapter

        r = client.post("/generate", json={"text": "say hello"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["response"], "hello world")
        self.assertIn("mode", data)
        self.assertIn("model", data)

    @patch("superbot.api.app._get_adapter")
    def test_generate_with_mode(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.generate.return_value = "code output"
        mock_adapter_factory.return_value = adapter

        r = client.post("/generate", json={"text": "write code", "mode": "coding"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["model"], "qwen2.5-coder:7b")

    def test_generate_empty_text(self):
        r = client.post("/generate", json={"text": ""})
        self.assertEqual(r.status_code, 422)

    def test_generate_missing_text(self):
        r = client.post("/generate", json={})
        self.assertEqual(r.status_code, 422)

    @patch("superbot.api.app._get_adapter")
    def test_generate_adapter_error(self, mock_adapter_factory):
        adapter = MagicMock()
        adapter.generate.side_effect = RuntimeError("timeout")
        mock_adapter_factory.return_value = adapter

        r = client.post("/generate", json={"text": "hello"})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
