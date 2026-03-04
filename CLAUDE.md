# CLAUDE.md — AI Assistant Rules for super-bot

## Project purpose
super-bot is a **personal AI orchestration tool** that routes prompts to locally-running
LLMs (via Ollama) to offload token costs, while being orchestrated by a "super AI" (Claude).
It integrates with GitHub for issue-driven workflows.

## Scope
- **v1 (current):** CLI entrypoint (single-shot, REPL, process-issue, list-models),
  config-driven routing, Ollama HTTP adapter with streaming & retry, GitHub adapter
  (issues + comments + context injection), FastAPI HTTP gateway, append-only request log.
- **v2 (planned):** Multi-turn conversation, auth on HTTP gateway, ML-based mode inference.

## Constraints
1. Never commit `.env` — use `.env.example` as the template.
2. Never store secrets in source files or logs.
3. `logs/requests.jsonl` is gitignored — do not commit it.
4. All adapters must be independently importable (no circular deps).
5. Keep changes minimal and reversible — no sweeping refactors without a plan.

## Tech stack
- Python 3.11+
- httpx (async-capable HTTP client for Ollama)
- PyGithub (GitHub REST wrapper)
- pyyaml (routing config)
- python-dotenv (env loading)

## Runtime
- Ollama runs on a remote host: `http://192.168.1.65:11434`
- GitHub PAT loaded from `GITHUB_TOKEN` env var
- Default repo: `GITHUB_DEFAULT_REPO` env var (e.g. `Thinker-74/super-bot`)

## Key paths
| Path | Purpose |
|------|---------|
| `config/routing.yaml` | Mode → model mapping (edit without code change) |
| `src/superbot/main.py` | CLI entrypoint |
| `src/superbot/router/router.py` | Routing logic |
| `src/superbot/adapters/ollama.py` | Ollama HTTP adapter |
| `src/superbot/adapters/github.py` | GitHub adapter |
| `src/superbot/state/logger.py` | Request logger |
| `docs/` | Architecture, routing, GitHub integration docs |
| `logs/requests.jsonl` | Gitignored request log |

## Commit style
`<type>(<scope>): <short summary>` — types: feat, fix, docs, refactor, test, chore
