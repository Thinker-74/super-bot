"""CLI entrypoint for super-bot.

Modes:
  Normal       python -m superbot.main --text "..." --mode coding
  With context python -m superbot.main --text "..." --repo Thinker-74/super-bot
  Interactive  python -m superbot.main --interactive [--mode coding]
  Process issue python -m superbot.main --process-issue 5 [--repo ...]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from superbot.adapters.github import GitHubAdapter  # noqa: E402
from superbot.adapters.ollama import OllamaAdapter  # noqa: E402
from superbot.gateway.handler import Request, normalize  # noqa: E402
from superbot.router.router import Router  # noqa: E402
from superbot.state.logger import log_request  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ollama() -> OllamaAdapter:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://192.168.1.65:11434")
    return OllamaAdapter(base_url)


def _make_github(repo: str | None = None) -> GitHubAdapter | None:
    token = os.environ.get("GITHUB_TOKEN")
    default_repo = repo or os.environ.get("GITHUB_DEFAULT_REPO", "")
    if not token or not default_repo:
        return None
    return GitHubAdapter(token, default_repo)


def _build_github_context(gh: GitHubAdapter, repo: str | None) -> str:
    """Fetch open issues and format them as a context block for the prompt."""
    try:
        issues = gh.list_issues(repo=repo, state="open")
    except Exception as e:
        print(f"[superbot] warning: could not fetch issues: {e}", file=sys.stderr)
        return ""
    if not issues:
        return ""
    lines = [f"[GitHub context — {repo or gh._default_repo} — open issues]"]
    for i in issues:
        body_snippet = (i["body"] or "")[:200].replace("\n", " ")
        lines.append(f"  #{i['number']} {i['title']}")
        if body_snippet:
            lines.append(f"    {body_snippet}")
    return "\n".join(lines)


def _call_adapter(adapter_name: str, model: str, prompt: str, stream: bool = False) -> str:
    if adapter_name == "ollama":
        return _make_ollama().generate(model=model, prompt=prompt, stream=stream)
    raise ValueError(f"Adapter '{adapter_name}' not implemented.")


def _run_once(text: str, mode: str | None, repo: str | None, router: Router, inject_context: bool, stream: bool = False) -> str:
    """Normalize → route → (optionally) inject GitHub context → call adapter → log → return response."""
    request = normalize({"text": text, "mode": mode or "", "repo": repo})
    route = router.route(request.mode)
    model, adapter_name = route["model"], route["adapter"]

    prompt = request.text

    # Feature 1: GitHub context injection
    if inject_context and repo:
        gh = _make_github(repo)
        if gh:
            ctx = _build_github_context(gh, repo)
            if ctx:
                prompt = f"{ctx}\n\n---\n\n{prompt}"

    print(f"[superbot] mode={route['mode']} model={model}", file=sys.stderr)
    response = _call_adapter(adapter_name, model, prompt, stream=stream)
    log_request(request, model, response)
    return response


# ---------------------------------------------------------------------------
# Feature 3: process-issue
# ---------------------------------------------------------------------------

def _process_issue(issue_number: int, repo: str | None, mode: str | None, router: Router) -> int:
    """Fetch issue #N, send to LLM, post response as comment."""
    gh = _make_github(repo)
    if not gh:
        print("[superbot] GITHUB_TOKEN or GITHUB_DEFAULT_REPO not set.", file=sys.stderr)
        return 1

    print(f"[superbot] fetching issue #{issue_number}…", file=sys.stderr)
    issue = gh.get_issue(issue_number, repo)

    # Build prompt from issue
    comments_block = ""
    if issue["comments"]:
        comments_block = "\n\nExisting comments:\n" + "\n".join(
            f"  @{c['author']}: {c['body']}" for c in issue["comments"]
        )

    prompt = (
        f"GitHub issue #{issue['number']}: {issue['title']}\n\n"
        f"{issue['body'] or '(no description)'}"
        f"{comments_block}\n\n"
        f"Please analyse this issue and provide a clear, actionable response."
    )

    route = router.route(mode or "reasoning_light")
    model, adapter_name = route["model"], route["adapter"]
    print(f"[superbot] mode={route['mode']} model={model}", file=sys.stderr)

    response = _call_adapter(adapter_name, model, prompt)

    request = normalize({"text": prompt, "mode": route["mode"], "repo": repo})
    log_request(request, model, response)

    print(f"\n--- LLM response ---\n{response}\n")

    comment = gh.add_comment(issue_number, response, repo)
    print(f"[superbot] comment posted: {comment['url']}")
    return 0


# ---------------------------------------------------------------------------
# Feature 2: REPL
# ---------------------------------------------------------------------------

def _repl(mode: str | None, repo: str | None, router: Router, stream: bool = False) -> int:
    """Interactive loop. Commands: /mode <name>, /repo <slug>, /stream, /exit."""
    current_mode = mode or router.default_mode
    current_repo = repo
    inject = bool(current_repo)

    print(f"[superbot] interactive mode — model={router.route(current_mode)['model']} stream={'on' if stream else 'off'}")
    print(f"  /mode <name>  switch mode  (available: {', '.join(router.available_modes)})")
    print(f"  /repo <slug>  set repo for GitHub context")
    print(f"  /stream       toggle streaming on/off")
    print(f"  /exit         quit\n")

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[superbot] bye.")
            return 0

        if not text:
            continue

        if text == "/exit":
            print("[superbot] bye.")
            return 0

        if text.startswith("/mode "):
            new_mode = text[6:].strip()
            if new_mode in router.available_modes:
                current_mode = new_mode
                print(f"[superbot] switched to mode={current_mode} model={router.route(current_mode)['model']}")
            else:
                print(f"[superbot] unknown mode '{new_mode}'. Available: {', '.join(router.available_modes)}")
            continue

        if text.startswith("/repo "):
            current_repo = text[6:].strip() or None
            inject = bool(current_repo)
            print(f"[superbot] repo set to {current_repo or '(none)'}")
            continue

        if text == "/stream":
            stream = not stream
            print(f"[superbot] streaming {'on' if stream else 'off'}")
            continue

        try:
            if stream:
                print("bot> ", end="", flush=True)
            response = _run_once(text, current_mode, current_repo, router, inject_context=inject, stream=stream)
            if not stream:
                print(f"\nbot> {response}\n")
            else:
                print()
        except Exception as e:
            print(f"[superbot] error: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="superbot", description="Route prompts to local LLMs via Ollama.")
    p.add_argument("--mode", default=None, help="Routing mode (coding, reasoning_light, reasoning_heavy, docs)")
    p.add_argument("--repo", default=None, help="GitHub repo slug (e.g. Thinker-74/super-bot)")
    p.add_argument("--stream", "-s", action="store_true", help="Stream tokens to stdout in real time")

    group = p.add_mutually_exclusive_group()
    group.add_argument("--text", help="Prompt text (single-shot mode)")
    group.add_argument("--interactive", "-i", action="store_true", help="Interactive REPL mode")
    group.add_argument("--process-issue", type=int, metavar="N", help="Fetch issue #N, analyse, post comment")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    router = Router()
    stream = args.stream

    # Resolve repo: CLI flag overrides env
    repo = args.repo or os.environ.get("GITHUB_DEFAULT_REPO") or None

    if args.interactive:
        return _repl(args.mode, repo, router, stream=stream)

    if args.process_issue is not None:
        return _process_issue(args.process_issue, repo, router=router, mode=args.mode)

    if not args.text:
        build_parser().print_help()
        return 1

    # Single-shot with optional GitHub context
    inject = bool(repo)
    try:
        response = _run_once(args.text, args.mode, repo, router, inject_context=inject, stream=stream)
        if not stream:
            print(response)
        return 0
    except Exception as e:
        print(f"[superbot] error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
