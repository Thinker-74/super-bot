# Routing — Config-Driven Mode → Model Mapping

## Overview

super-bot uses `config/routing.yaml` as the single source of truth for routing.
No code change needed to add a mode or swap a model.

## Config Format

```yaml
default_mode: <mode_name>

modes:
  <mode_name>:
    model: <ollama_model_tag>
    adapter: ollama | remote
```

### Current config

```yaml
default_mode: reasoning_light

modes:
  coding:
    model: qwen2.5-coder:14b
    adapter: ollama
  reasoning_light:
    model: deepseek-r1:7b
    adapter: ollama
  reasoning_heavy:
    model: deepseek-r1:14b
    adapter: ollama
  docs:
    model: deepseek-r1:7b
    adapter: ollama
```

## Mode Reference

| Mode | Model | Size | Use case |
|------|-------|------|----------|
| `coding` | `qwen2.5-coder:14b` | 9.0 GB | Code generation, debugging, refactoring |
| `reasoning_light` | `deepseek-r1:7b` | 4.7 GB | Quick reasoning, Q&A, summaries **(default)** |
| `reasoning_heavy` | `deepseek-r1:14b` | 9.0 GB | Complex reasoning, multi-step planning |
| `docs` | `deepseek-r1:7b` | 4.7 GB | Documentation generation, explanations |

## Routing Rules

1. If `--mode <name>` matches a key in `modes:`, that entry is used.
2. If `--mode` is omitted or unknown → `default_mode` is used.
3. `default_mode` must be a valid key in `modes:`.
4. `adapter: remote` is reserved — raises `NotImplementedError` today.

## CLI Examples

```bash
# Explicit coding mode with streaming
superbot --text "implement binary search in Python" --mode coding --stream

# Default mode (reasoning_light) with GitHub context
superbot --text "what should I work on?" --repo Thinker-74/super-bot

# Heavy reasoning
superbot --text "design a fault-tolerant job queue" --mode reasoning_heavy

# Interactive REPL — switch mode mid-session
superbot --interactive
you> /mode coding
you> write a merge sort
you> /stream
you> explain quicksort  # streamed
you> /exit
```

## HTTP Examples

```bash
# Single-shot
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "write fibonacci", "mode": "coding"}'

# Check what models are available
curl http://localhost:8000/models
```

## Adding a New Mode

1. Edit `config/routing.yaml`:
   ```yaml
   summarise:
     model: deepseek-r1:7b
     adapter: ollama
   ```
2. No Python changes required — `Router` picks up the new key at startup.
3. Verify with `superbot --list-models` that the model exists on Ollama.
