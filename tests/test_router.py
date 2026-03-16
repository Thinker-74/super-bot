"""Unit tests for Router — no network required."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure src/ is on the path when running directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superbot.router.router import Router

_CONFIG = Path(__file__).parent.parent / "config" / "routing.yaml"


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router(config_path=_CONFIG)

    # ------------------------------------------------------------------
    # Known modes
    # ------------------------------------------------------------------

    def test_coding_mode(self):
        result = self.router.route("coding")
        self.assertEqual(result["mode"], "coding")
        self.assertEqual(result["model"], "qwen2.5-coder:7b")
        self.assertEqual(result["adapter"], "ollama")

    def test_reasoning_light_mode(self):
        result = self.router.route("reasoning_light")
        self.assertEqual(result["mode"], "reasoning_light")
        self.assertEqual(result["model"], "qwen3:8b")

    def test_reasoning_heavy_mode(self):
        result = self.router.route("reasoning_heavy")
        self.assertEqual(result["model"], "qwen3:8b")

    def test_docs_mode(self):
        result = self.router.route("docs")
        self.assertEqual(result["mode"], "docs")
        self.assertEqual(result["model"], "qwen3:8b")

    # ------------------------------------------------------------------
    # Fallback behaviour
    # ------------------------------------------------------------------

    def test_none_falls_back_to_default(self):
        result = self.router.route(None)
        self.assertEqual(result["mode"], self.router.default_mode)

    def test_empty_string_falls_back_to_default(self):
        result = self.router.route("")
        self.assertEqual(result["mode"], self.router.default_mode)

    def test_unknown_mode_falls_back_to_default(self):
        result = self.router.route("nonexistent_mode_xyz")
        self.assertEqual(result["mode"], self.router.default_mode)

    def test_default_mode_is_reasoning_light(self):
        self.assertEqual(self.router.default_mode, "reasoning_light")

    # ------------------------------------------------------------------
    # available_modes
    # ------------------------------------------------------------------

    def test_available_modes_contains_all_config_keys(self):
        modes = self.router.available_modes
        for expected in ("coding", "reasoning_light", "reasoning_heavy", "docs"):
            self.assertIn(expected, modes)

    def test_route_result_has_required_keys(self):
        result = self.router.route("coding")
        self.assertIn("mode", result)
        self.assertIn("model", result)
        self.assertIn("adapter", result)


if __name__ == "__main__":
    unittest.main()
