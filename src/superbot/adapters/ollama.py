"""Ollama adapter — POST /api/generate on the remote Ollama endpoint."""
from __future__ import annotations

import time

import httpx


class OllamaAdapter:
    """Thin wrapper around Ollama's /api/generate REST endpoint.

    Args:
        base_url: Ollama base URL, e.g. ``http://192.168.1.65:11434``.
        timeout: Request timeout in seconds (default 120 to allow slow models).
        retries: Number of retry attempts on transient errors (default 2).
        retry_delay: Seconds to wait between retries (default 3).
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        retries: int = 2,
        retry_delay: float = 3.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay

    def health(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return True
        except Exception:
            return False

    def generate(self, model: str, prompt: str, stream: bool = False) -> str:
        """Send a prompt to Ollama and return the response text.

        Retries on transient network errors (ConnectTimeout, RemoteProtocolError).

        Args:
            model: Model name as known by Ollama (e.g. ``deepseek-r1:7b``).
            prompt: The full prompt string.
            stream: Reserved — always False in v0.

        Returns:
            The ``response`` field from Ollama's JSON reply.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
            httpx.ConnectTimeout: If all retries are exhausted.
        """
        payload = {"model": model, "prompt": prompt, "stream": False}
        url = f"{self.base_url}/api/generate"

        last_exc: Exception | None = None
        for attempt in range(1 + self.retries):
            try:
                response = httpx.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()["response"]
            except (httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay)
            except Exception:
                raise

        raise last_exc  # type: ignore[misc]
