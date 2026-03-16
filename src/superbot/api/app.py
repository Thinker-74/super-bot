"""FastAPI gateway for super-bot.

Exposes the same routing + Ollama logic as the CLI over HTTP.

Run:
    uvicorn superbot.api.app:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
    POST /generate          Single-shot prompt
    GET  /models            List available Ollama models
    GET  /health            Liveness check (Ollama + self)
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env", override=False)

from superbot.adapters.ollama import OllamaAdapter  # noqa: E402
from superbot.gateway.handler import normalize  # noqa: E402
from superbot.router.router import Router  # noqa: E402
from superbot.state.logger import log_request  # noqa: E402

app = FastAPI(title="super-bot", version="1.0.0", description="Personal AI orchestration bot — HTTP gateway")

_router = Router()
_ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://192.168.1.63:11434")


def _get_adapter() -> OllamaAdapter:
    return OllamaAdapter(_ollama_base)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    text: str = Field(..., description="Prompt text")
    mode: str | None = Field(None, description="Routing mode (coding, reasoning_light, reasoning_heavy, docs)")
    repo: str | None = Field(None, description="GitHub repo slug for context injection")
    stream: bool = Field(False, description="Stream tokens in response")


class GenerateResponse(BaseModel):
    mode: str
    model: str
    response: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
def health():
    """Liveness check — returns Ollama reachability."""
    adapter = _get_adapter()
    ollama_ok = adapter.health()
    return {"status": "ok", "ollama": ollama_ok, "ollama_url": _ollama_base}


@app.get("/models", tags=["ops"])
def list_models():
    """List models available on the Ollama server."""
    try:
        models = _get_adapter().list_models()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unreachable: {e}")
    return {"ollama_url": _ollama_base, "models": models}


@app.post("/generate", response_model=GenerateResponse, tags=["inference"])
def generate(body: GenerateRequest):
    """Route a prompt to the appropriate model and return the response."""
    try:
        request = normalize({"text": body.text, "mode": body.mode or "", "repo": body.repo})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    route = _router.route(request.mode)
    model, adapter_name = route["model"], route["adapter"]

    if adapter_name != "ollama":
        raise HTTPException(status_code=501, detail=f"Adapter '{adapter_name}' not implemented.")

    adapter = _get_adapter()

    if body.stream:
        def token_generator():
            collected: list[str] = []
            try:
                response_text = adapter.generate(model=model, prompt=request.text, stream=False)
                collected.append(response_text)
                yield response_text
            except Exception as e:
                yield f"\n[superbot] streaming error: {e}"
                return
            finally:
                log_request(request, model, "".join(collected))

        return StreamingResponse(token_generator(), media_type="text/plain")

    try:
        response = adapter.generate(model=model, prompt=request.text)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    log_request(request, model, response)
    return GenerateResponse(mode=route["mode"], model=model, response=response)
