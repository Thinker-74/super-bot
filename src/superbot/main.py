"""CLI entrypoint for super-bot v0.

Usage:
    python -m superbot.main --text "write a fibonacci function" --mode coding
    python -m superbot.main --text "list issues" --mode reasoning_light --repo Thinker-74/super-bot
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (two levels up from src/superbot/)
_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from superbot.adapters.ollama import OllamaAdapter  # noqa: E402
from superbot.gateway.handler import normalize  # noqa: E402
from superbot.router.router import Router  # noqa: E402
from superbot.state.logger import log_request  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="superbot",
        description="Route a prompt to the right model based on mode.",
    )
    p.add_argument("--text", required=True, help="Prompt text to send to the model")
    p.add_argument(
        "--mode",
        default=None,
        help="Routing mode (coding, reasoning_light, reasoning_heavy, docs). "
        "Defaults to routing.yaml default_mode.",
    )
    p.add_argument(
        "--repo",
        default=None,
        help="GitHub repo slug override (e.g. Thinker-74/super-bot)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 1. Normalise input
    request = normalize({"text": args.text, "mode": args.mode or "", "repo": args.repo})

    # 2. Route
    router = Router()
    route = router.route(request.mode)
    model = route["model"]
    adapter_name = route["adapter"]

    print(f"[superbot] mode={route['mode']} model={model} adapter={adapter_name}")

    # 3. Call adapter
    if adapter_name == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://192.168.1.65:11434")
        adapter = OllamaAdapter(base_url)
        response = adapter.generate(model=model, prompt=request.text)
    else:
        print(f"[superbot] Adapter '{adapter_name}' is not implemented.", file=sys.stderr)
        return 1

    # 4. Log
    log_request(request, model, response)

    # 5. Output
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
