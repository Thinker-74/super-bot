# super-bot

Orchestrator interface to hybridize **local** and **online** AI models behind a single front-end.

## Vision

Most real-world workflows require jumping across many AI tools (ChatGPT, Claude, Perplexity, SaaS copilot tools, etc.).  
super-bot aims to provide **one entrypoint** that can:

- Route each request to the most appropriate model (local via Ollama or remote via APIs)
- Keep project state, issues, and progress tracked in **GitHub**
- Reduce the need for multiple paid subscriptions and fragmented portals

## Core use cases

- **Reasoning & writing**: use local LLMs (DeepSeek, Qwen, etc.) for analysis, planning, and drafting.
- **Coding workflows**: integrate with Claude Code and GitHub for code edits, PRs, and reviews.
- **Project orchestration**: interact with issues, branches, and tasks through a unified conversational interface.

## Initial tech stack (planned)

- Backend: Python (FastAPI or similar)
- Local models: [Ollama](https://ollama.com/) (e.g. Qwen2.5 Coder, DeepSeek-R1)
- Integrations: GitHub API, CLI tools (Claude Code), optionally external LLM APIs

## Status

⚠️ Early experimental stage.  
APIs, architecture, and naming are subject to change as the design is refined.
