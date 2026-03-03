# Routing — Config-Driven Mode → Model Mapping

## Overview

super-bot uses a YAML file (`config/routing.yaml`) as the single source of truth for
routing decisions. No code change is needed to add a new mode or swap a model.

## Config Format

```yaml
default_mode: <mode_name>   # fallback when mode is unknown or omitted

modes:
  <mode_name>:
    model: <ollama_model_tag>
    adapter: ollama | remote
```

### Current config (`config/routing.yaml`)

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

| Mode | Model | Use case |
|------|-------|----------|
| `coding` | `qwen2.5-coder:14b` | Code generation, debugging, refactoring |
| `reasoning_light` | `deepseek-r1:7b` | Quick reasoning, Q&A, summaries (default) |
| `reasoning_heavy` | `deepseek-r1:14b` | Complex reasoning, multi-step planning |
| `docs` | `deepseek-r1:7b` | Documentation generation, explanations |

## Routing Rules

1. If `--mode <name>` matches a key in `modes:`, that entry is used.
2. If `--mode` is omitted or the value is not a known key, `default_mode` is used.
3. `default_mode` must be a valid key in `modes:`.
4. The `adapter` field currently supports only `ollama`. The `remote` value is reserved
   for future use (raises `NotImplementedError` today).

## CLI Examples

```bash
# Explicit coding mode
python -m superbot.main --text "implement binary search in Python" --mode coding

# Default mode (reasoning_light)
python -m superbot.main --text "explain the CAP theorem"

# Heavy reasoning
python -m superbot.main --text "design a fault-tolerant job queue" --mode reasoning_heavy

# Docs mode
python -m superbot.main --text "write docstring for class Router" --mode docs
```

## Adding a New Mode

1. Pull `config/routing.yaml`.
2. Add an entry under `modes:`:
   ```yaml
   summarise:
     model: deepseek-r1:7b
     adapter: ollama
   ```
3. Optionally update `default_mode`.
4. No Python changes required — `Router` picks up the new key at startup.

## Router Implementation Notes

- `Router.__init__` opens the YAML file once at startup.
- `Router.route(mode)` is O(1) dict lookup.
- `Router.available_modes` property exposes the full list for validation/help text.
