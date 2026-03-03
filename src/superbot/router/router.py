"""Config-driven router — maps a mode string to a {model, adapter} dict."""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "routing.yaml"


class Router:
    """Load routing.yaml and resolve mode → {model, adapter}."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        path = Path(config_path) if config_path else _DEFAULT_CONFIG
        with path.open() as fh:
            data = yaml.safe_load(fh)
        self._default_mode: str = data["default_mode"]
        self._modes: dict[str, dict] = data["modes"]

    def route(self, mode: str | None = None) -> dict:
        """Return ``{model, adapter}`` for *mode*, falling back to default.

        Args:
            mode: One of the keys in ``config/routing.yaml``.  If *None* or
                unknown, the default mode is used.

        Returns:
            dict with keys ``model`` (str) and ``adapter`` (str).
        """
        resolved = mode if (mode and mode in self._modes) else self._default_mode
        entry = self._modes[resolved]
        return {"mode": resolved, "model": entry["model"], "adapter": entry["adapter"]}

    @property
    def available_modes(self) -> list[str]:
        return list(self._modes.keys())

    @property
    def default_mode(self) -> str:
        return self._default_mode
