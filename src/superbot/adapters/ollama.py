"""Ollama adapter — POST /api/generate on the remote Ollama endpoint."""
from __future__ import annotations

import httpx


class OllamaAdapter:
    """Thin wrapper around Ollama's /api/generate REST endpoint.

    Args:
        base_url: Ollama base URL, e.g. ``http://195.168.1.65:11434``.
        timeout: Request timeout in seconds (default 120 to allow slow models).
    """

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, model: str, prompt: str, stream: bool = False) -> str:
        """Send a prompt to Ollama and return the response text.

        Args:
            model: Model name as known by Ollama (e.g. ``deepseek-r1:7b``).
            prompt: The full prompt string.
            stream: If *True*, streams tokens (not yet implemented — always False).

        Returns:
            The ``response`` field from Ollama's JSON reply.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
            httpx.TimeoutException: If Ollama doesn't respond in time.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        url = f"{self.base_url}/api/generate"
        response = httpx.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()["response"]
