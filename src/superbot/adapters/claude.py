"""Claude API adapter — orchestration (routing decisions) and direct generation."""
from __future__ import annotations

import json
import re

import anthropic

_ORCHESTRATOR_MODEL = "claude-haiku-4-5-20251001"
_GENERATION_MODEL = "claude-sonnet-4-6"

_SYSTEM_TEMPLATE = """\
You are a routing orchestrator for an AI cost-saving system.
Decide whether a local LLM can handle the user prompt or if you must respond directly.

Available local LLM modes:
{modes_block}

Reply with JSON only — no markdown fences, no extra text:
{{"action":"delegate","mode":"<mode>","reason":"<one line>"}}
OR
{{"action":"direct","reason":"<one line>"}}

Delegate whenever possible. Only choose direct for tasks requiring
very recent knowledge (after 2024), ethical judgment, or multi-step orchestration.
"""


def _build_system_prompt(modes: dict[str, str]) -> str:
    lines = "\n".join(f"  {mode:<20} → {model}" for mode, model in modes.items())
    return _SYSTEM_TEMPLATE.format(modes_block=lines)


def _parse_decision(text: str, valid_modes: set[str] | None = None, fallback_mode: str = "reasoning_light") -> dict:
    """Extract JSON from Claude's response; fall back gracefully on parse errors."""
    # Strip accidental markdown fences
    cleaned = re.sub(r"```[a-z]*\n?", "", text).strip()
    try:
        data = json.loads(cleaned)
        if data.get("action") not in ("delegate", "direct"):
            raise ValueError("unknown action")
        # Validate mode exists in available modes
        if data.get("action") == "delegate" and valid_modes and data.get("mode") not in valid_modes:
            data["mode"] = fallback_mode
            data["reason"] = f"unknown mode '{data.get('mode')}' — fallback"
        return data
    except (json.JSONDecodeError, ValueError):
        return {"action": "delegate", "mode": fallback_mode, "reason": "parse error — fallback"}


class ClaudeAdapter:
    """Thin wrapper around the Anthropic SDK for orchestration and generation."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def decide(self, prompt: str, modes: dict[str, str]) -> dict:
        """Ask Claude (haiku) to pick delegate/direct. Returns parsed decision dict."""
        system = _build_system_prompt(modes)
        msg = self._client.messages.create(
            model=_ORCHESTRATOR_MODEL,
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            return {"action": "delegate", "mode": "reasoning_light", "reason": "empty response — fallback"}
        return _parse_decision(msg.content[0].text, valid_modes=set(modes.keys()))

    def generate(self, prompt: str, stream: bool = False) -> str:
        """Respond directly using Claude (sonnet). Used when action=direct."""
        if stream:
            return self._generate_stream(prompt)
        msg = self._client.messages.create(
            model=_GENERATION_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            return "[superbot] Claude returned an empty response."
        return msg.content[0].text

    def _generate_stream(self, prompt: str) -> str:
        collected: list[str] = []
        with self._client.messages.stream(
            model=_GENERATION_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
        return "".join(collected)
