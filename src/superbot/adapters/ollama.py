"""Ollama adapter — POST /api/generate on the remote Ollama endpoint."""
from __future__ import annotations

import json
import sys
import time

import httpx


class OllamaAdapter:
    """Thin wrapper around Ollama's /api/generate REST endpoint.

    Args:
        base_url: Ollama base URL, e.g. ``http://192.168.1.63:11434``.
        timeout: Request timeout in seconds (default 300 for slow models).
        retries: Number of retry attempts on transient errors (default 2).
        retry_delay: Seconds to wait between retries (default 5).
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 300.0,
        retries: int = 2,
        retry_delay: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay

    def list_models(self) -> list[dict]:
        """Return list of models available on the Ollama server."""
        r = httpx.get(f"{self.base_url}/api/tags", timeout=8)
        r.raise_for_status()
        models = r.json().get("models", [])
        return [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1)} for m in models]

    def health(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return True
        except Exception:
            return False

    def generate(self, model: str, prompt: str, stream: bool = False) -> str:
        """Send a prompt to Ollama and return the full response text.

        When ``stream=True``, tokens are printed to stdout as they arrive and
        the complete text is also returned for logging.

        Retries on transient errors: ConnectTimeout, ReadTimeout,
        RemoteProtocolError, ConnectError.

        Args:
            model: Model name as known by Ollama (e.g. ``deepseek-r1:7b``).
            prompt: The full prompt string.
            stream: If True, streams tokens to stdout in real time.

        Returns:
            The complete response text.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
            httpx.ConnectTimeout: If all retries are exhausted.
        """
        url = f"{self.base_url}/api/generate"
        last_exc: Exception | None = None

        for attempt in range(1 + self.retries):
            try:
                if stream:
                    return self._generate_streaming(url, model, prompt)
                else:
                    payload = {"model": model, "prompt": prompt, "stream": False}
                    response = httpx.post(url, json=payload, timeout=self.timeout)
                    response.raise_for_status()
                    return response.json()["response"]
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay)
            except Exception:
                raise

        raise last_exc  # type: ignore[misc]

    def _generate_streaming(self, url: str, model: str, prompt: str) -> str:
        """Stream tokens from Ollama, printing each to stdout as it arrives.

        Returns the full concatenated response for logging.
        """
        payload = {"model": model, "prompt": prompt, "stream": True}
        full_response: list[str] = []

        with httpx.stream("POST", url, json=payload, timeout=self.timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("response", "")
                if token:
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    full_response.append(token)
                if chunk.get("done"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    break

        return "".join(full_response)
