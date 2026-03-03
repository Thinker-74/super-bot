# super-bot v0 — Architecture

## ASCII Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI  (main.py)                               │
│   python -m superbot.main --text "..." --mode coding --repo ...     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ raw dict
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Gateway / Handler                                │
│   handler.normalize()  →  Request(text, mode, repo, context)        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ Request
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Router                                       │
│   Loads config/routing.yaml                                          │
│   router.route(mode)  →  {mode, model, adapter}                     │
└──────────┬───────────────────────────────────────────────────────────┘
           │ {model, adapter}
           ├────────────────────────────────────────────┐
           ▼                                            ▼
┌──────────────────────┐                    ┌───────────────────────┐
│   OllamaAdapter      │                    │   GitHubAdapter       │
│   POST /api/generate │                    │   list/get/create     │
│   → str response     │                    │   issues, comments    │
└──────────┬───────────┘                    └───────────────────────┘
           │ response text
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     State / Logger                                   │
│   log_request()  →  logs/requests.jsonl  (append-only JSONL)        │
└──────────────────────────────────────────────────────────────────────┘
           │ response
           ▼
        stdout (CLI output)
```

## Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **CLI** | `src/superbot/main.py` | Parse args, wire components, print result |
| **Gateway Handler** | `src/superbot/gateway/handler.py` | Validate & normalize raw input → `Request` dataclass |
| **Router** | `src/superbot/router/router.py` | Load `config/routing.yaml`, map mode → `{model, adapter}` |
| **OllamaAdapter** | `src/superbot/adapters/ollama.py` | HTTP POST to Ollama `/api/generate`, return response text |
| **GitHubAdapter** | `src/superbot/adapters/github.py` | List/read/create issues and comments via PyGithub |
| **RemoteAdapter** | `src/superbot/adapters/remote.py` | Placeholder stub — raises `NotImplementedError` |
| **Logger** | `src/superbot/state/logger.py` | Append JSON record to `logs/requests.jsonl` |
| **Routing config** | `config/routing.yaml` | Source of truth for mode → model mapping |

## Data Flow (happy path)

1. User runs CLI with `--text`, `--mode`, optional `--repo`.
2. `normalize()` validates input and returns a `Request` dataclass.
3. `Router.route(mode)` looks up the mode in YAML; falls back to `default_mode` if unknown.
4. `main.py` instantiates the correct adapter (currently only `OllamaAdapter`).
5. Adapter sends the prompt to the remote Ollama host and returns the text response.
6. `log_request()` appends a timestamped JSON record to `logs/requests.jsonl`.
7. Response is printed to stdout.

## External Dependencies

| System | Address | Protocol |
|--------|---------|---------|
| Ollama (LLM host) | `http://195.168.1.65:11434` | HTTP REST (`/api/generate`) |
| GitHub | `https://api.github.com` | HTTPS REST via PyGithub |

## Open Questions

1. **Streaming** — Ollama supports SSE streaming. Should v1 stream tokens to stdout?
2. **Mode inference** — Should the bot auto-detect the best mode from the prompt text,
   or always require `--mode`?
3. **GitHub context injection** — Should `--repo` automatically fetch open issues and
   inject them into the prompt as context?
4. **Multi-turn conversation** — `logs/requests.jsonl` records history but doesn't replay
   it as context. Is a session/conversation concept needed?
5. **FastAPI gateway** — When do we expose super-bot as an HTTP service?
6. **Auth model** — PAT tokens are fine for v0. OAuth app or GitHub App for v1?
