"""Append-only JSON-lines logger for all requests and responses."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from superbot.gateway.handler import Request

_LOG_FILE = Path(__file__).parent.parent.parent.parent / "logs" / "requests.jsonl"


def log_request(request: Request, model: str, response: str) -> None:
    """Append one JSON line to ``logs/requests.jsonl``.

    Args:
        request: The normalised Request dataclass.
        model: The model name that produced the response.
        response: The raw response text from the adapter.
    """
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": request.mode,
        "model": model,
        "repo": request.repo,
        "text": request.text,
        "response": response,
    }
    with _LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
