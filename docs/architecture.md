# super-bot — Architecture

## ASCII Diagram (v1)

```
┌────────────────────────────────────────────────────────────────────────┐
│                     Entry Points                                        │
│                                                                         │
│  CLI  python -m superbot.main  ──────────────────────────────────────┐ │
│       --text / --interactive / --process-issue / --list-models        │ │
│       --stream / --repo / --mode                                       │ │
│                                                                         │ │
│  HTTP uvicorn superbot.api.app:app                                    │ │
│       POST /generate   GET /models   GET /health                      │ │
└───────────────────────────────────────────────────────────────────────┼─┘
                                                                         │
                               ▼                                         │
┌────────────────────────────────────────────────────────────────────────┤
│                     Gateway / Handler                                   │
│   handler.normalize()  →  Request(text, mode, repo, context)          │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│              GitHub Context Injection  (when --repo is set)            │
│   GitHubAdapter.list_issues()  →  context block prepended to prompt   │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         Router                                          │
│   Loads config/routing.yaml                                            │
│   router.route(mode)  →  {mode, model, adapter}                       │
└───────┬───────────────────────────────────────────────────────────────┘
        │
        ├──────────────────────────────────┐
        ▼                                  ▼
┌───────────────────┐           ┌──────────────────────┐
│  OllamaAdapter    │           │  GitHubAdapter        │
│  POST /api/gen.   │           │  list / get / create  │
│  stream supported │           │  issues + comments    │
│  retry on timeout │           └──────────────────────┘
└────────┬──────────┘
         │ response
         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     State / Logger                                      │
│   log_request()  →  logs/requests.jsonl  (append-only JSONL)          │
└────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **CLI** | `src/superbot/main.py` | Parse args, wire all components |
| **FastAPI gateway** | `src/superbot/api/app.py` | HTTP interface: POST /generate, GET /models, GET /health |
| **Gateway Handler** | `src/superbot/gateway/handler.py` | Validate & normalize raw input → `Request` dataclass |
| **Router** | `src/superbot/router/router.py` | Load `config/routing.yaml`, map mode → `{model, adapter}` |
| **OllamaAdapter** | `src/superbot/adapters/ollama.py` | HTTP POST to Ollama, streaming, retry logic |
| **GitHubAdapter** | `src/superbot/adapters/github.py` | List/read/create issues and comments |
| **RemoteAdapter** | `src/superbot/adapters/remote.py` | Placeholder stub — raises `NotImplementedError` |
| **Logger** | `src/superbot/state/logger.py` | Append JSON record to `logs/requests.jsonl` |
| **Routing config** | `config/routing.yaml` | Source of truth for mode → model mapping |

## CLI Reference

```
superbot [--mode MODE] [--repo SLUG] [--stream]
         (--text TEXT | --interactive | --process-issue N | --list-models)

--text TEXT          Single-shot prompt
--interactive / -i   REPL loop (commands: /mode, /repo, /stream, /exit)
--process-issue N    Fetch issue #N, analyse, post LLM response as comment
--list-models        List models available on Ollama with size

--mode MODE          coding | reasoning_light | reasoning_heavy | docs
--repo SLUG          GitHub repo (e.g. Thinker-74/super-bot) — enables context injection
--stream / -s        Stream tokens to stdout in real time
```

## HTTP API Reference

```
POST /generate
  Body: { "text": "...", "mode": "coding", "repo": "owner/repo", "stream": false }
  Returns: { "mode": "coding", "model": "qwen2.5-coder:14b", "response": "..." }
  stream=true → text/plain streaming response

GET /models
  Returns: { "ollama_url": "...", "models": [{"name": "...", "size_gb": 9.0}] }

GET /health
  Returns: { "status": "ok", "ollama": true, "ollama_url": "..." }
```

## Data Flow — Single-shot with GitHub context

1. `--text "..." --repo owner/repo` parsed by CLI
2. `normalize()` → `Request(text, mode, repo)`
3. `GitHubAdapter.list_issues()` → context block prepended to prompt
4. `Router.route(mode)` → `{model, adapter}`
5. `OllamaAdapter.generate(model, prompt, stream)` — with retry on timeout
6. `log_request()` → `logs/requests.jsonl`
7. Response printed to stdout (or streamed token by token)

## Data Flow — `--process-issue N`

1. `GitHubAdapter.get_issue(N)` → title + body + comments
2. Prompt built from issue content
3. `Router.route(mode)` → model
4. `OllamaAdapter.generate()` → response
5. `log_request()` → log file
6. `GitHubAdapter.add_comment(N, response)` → comment posted on GitHub

## External Dependencies

| System | Address | Protocol |
|--------|---------|---------|
| Ollama (LLM host) | `http://192.168.1.65:11434` | HTTP REST (`/api/generate`, `/api/tags`) |
| GitHub | `https://api.github.com` | HTTPS REST via PyGithub |

## Open Questions

1. **Auth on HTTP gateway** — `/generate` is currently unauthenticated. API key header needed before exposing publicly.
2. **Multi-turn conversation** — request log exists but history is not replayed as context.
3. **ML-based mode inference** — currently requires explicit `--mode`; could be inferred from prompt.
4. **GitHub App vs PAT** — PAT is fine for personal use; GitHub App needed for org-wide deployment.
5. **Streaming in REPL** — `/stream` toggle works but `bot> ` prefix appears before tokens; UX could be improved.
