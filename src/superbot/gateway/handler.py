"""Gateway handler — normalizes raw input into a Request dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Request:
    text: str
    mode: str
    repo: str | None = None
    context: dict = field(default_factory=dict)


def normalize(raw_input: dict) -> Request:
    """Convert a raw input dict (e.g. from CLI args) into a Request.

    Required keys: ``text``
    Optional keys: ``mode``, ``repo``, ``context``
    """
    text = raw_input.get("text", "").strip()
    if not text:
        raise ValueError("'text' is required and must not be empty")

    return Request(
        text=text,
        mode=raw_input.get("mode", ""),
        repo=raw_input.get("repo") or None,
        context=raw_input.get("context", {}),
    )
