"""Unit tests for the Claude orchestrator flow (_orchestrate in main.py)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from superbot.adapters.claude import _parse_decision
from superbot.router.router import Router


# ---------------------------------------------------------------------------
# _parse_decision unit tests
# ---------------------------------------------------------------------------

class TestParseDecision:
    def test_delegate_valid(self):
        raw = '{"action":"delegate","mode":"coding","reason":"code task"}'
        result = _parse_decision(raw)
        assert result == {"action": "delegate", "mode": "coding", "reason": "code task"}

    def test_direct_valid(self):
        raw = '{"action":"direct","reason":"needs fresh knowledge"}'
        result = _parse_decision(raw)
        assert result["action"] == "direct"

    def test_strips_markdown_fence(self):
        raw = "```json\n{\"action\":\"direct\",\"reason\":\"ok\"}\n```"
        result = _parse_decision(raw)
        assert result["action"] == "direct"

    def test_malformed_json_falls_back(self):
        result = _parse_decision("not json at all", fallback_mode="reasoning_light")
        assert result["action"] == "delegate"
        assert result["mode"] == "reasoning_light"

    def test_unknown_action_falls_back(self):
        result = _parse_decision('{"action":"unknown"}', fallback_mode="docs")
        assert result["action"] == "delegate"
        assert result["mode"] == "docs"


# ---------------------------------------------------------------------------
# _orchestrate integration-style tests (all external calls mocked)
# ---------------------------------------------------------------------------

class TestOrchestrate:
    def _run(self, text: str, decision: dict, stream: bool = False):
        """Helper: run _orchestrate with a mocked ClaudeAdapter."""
        from superbot import main as m

        router = Router()
        mock_claude = MagicMock()
        mock_claude.decide.return_value = decision

        with (
            patch.object(m, "_make_claude", return_value=mock_claude),
            patch.object(m, "_run_once", return_value="ollama-response") as mock_run_once,
            patch("builtins.print"),
        ):
            rc = m._orchestrate(text, repo=None, router=router, stream=stream)
            return rc, mock_run_once, mock_claude

    def test_delegate_calls_run_once(self):
        decision = {"action": "delegate", "mode": "coding", "reason": "code task"}
        rc, mock_run_once, _ = self._run("Write quicksort", decision)
        assert rc == 0
        mock_run_once.assert_called_once()
        _, kwargs = mock_run_once.call_args
        # mode is passed as positional arg index 1
        assert mock_run_once.call_args[0][1] == "coding"

    def test_direct_calls_claude_generate(self):
        decision = {"action": "direct", "reason": "needs recent data"}
        from superbot import main as m
        router = Router()
        mock_claude = MagicMock()
        mock_claude.decide.return_value = decision
        mock_claude.generate.return_value = "claude-response"

        with (
            patch.object(m, "_make_claude", return_value=mock_claude),
            patch.object(m, "_run_once") as mock_run_once,
            patch("builtins.print"),
        ):
            rc = m._orchestrate("Latest AI news?", repo=None, router=router, stream=False)

        assert rc == 0
        mock_claude.generate.assert_called_once_with("Latest AI news?", stream=False)
        mock_run_once.assert_not_called()

    def test_delegate_unknown_mode_uses_default(self):
        """If Claude returns an unrecognised mode, _run_once still gets called."""
        decision = {"action": "delegate", "mode": "nonexistent", "reason": "oops"}
        rc, mock_run_once, _ = self._run("Hello", decision)
        assert rc == 0
        mock_run_once.assert_called_once()

    def test_missing_api_key_raises(self):
        from superbot import main as m
        import os
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                m._make_claude()
