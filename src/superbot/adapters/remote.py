"""Remote adapter — placeholder for future cloud/API model support."""
from __future__ import annotations


class RemoteAdapter:
    """Stub adapter for remote (non-Ollama) model endpoints.

    Not implemented in v0.  Raises ``NotImplementedError`` on all calls.
    """

    def generate(self, model: str, prompt: str, **kwargs) -> str:
        raise NotImplementedError(
            "RemoteAdapter is not implemented in v0. "
            "Use OllamaAdapter for local model access."
        )
