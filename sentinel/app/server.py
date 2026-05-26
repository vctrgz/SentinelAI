"""
app/server.py

Adds sudo password collection to the SSE flow:
  • The event_stream() generator polls SudoManager.is_waiting_for_password()
    and emits a "needs_sudo" event when an executor thread is blocked waiting.
  • POST /sudo-auth  — receives the password from the browser modal and
    unblocks the waiting executor thread.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from core.orchestrator import Orchestrator
from utils.input_validator import InputValidator
from utils.llm_client import MultiProviderLLMClient
from utils.logger import logger
from utils.runtime_tracer import get_tracer
from app.config import Config

app = FastAPI(
    title       = "SentinelAI",
    description = "Agente de ciberseguridad con arquitectura multiagente",
    version     = "2.2.0",
)

_orchestrator: Orchestrator | None = None
_validator = InputValidator()
_tracer    = get_tracer()


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        logger.info("[Server] Inicializando Orchestrator…")
        _orchestrator = Orchestrator()
    return _orchestrator


@app.on_event("startup")
async def _startup() -> None:
    warnings = Config.validate()
    for w in warnings:
        logger.warning(f"[Config] {w}")
    client = MultiProviderLLMClient()
    models = client.list_models()
    if models:
        logger.info(f"[Server] LLM providers ready: {models}")
    else:
        logger.warning(
            "[Server] No LLM providers configured. "
            "Set OPENAI_API_KEY and/or OPENROUTER_API_KEY and/or HF_API_TOKEN and/or GROQ_API_KEY in .env"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Static / health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_chatbot() -> HTMLResponse:
    html_path = Path(__file__).parent.parent / "chatbot" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>chatbot/index.html no encontrado</h1>", status_code=404)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> JSONResponse:
    client = MultiProviderLLMClient()
    models = client.list_models()
    return JSONResponse({
        "status":   "ok" if models else "degraded",
        "models":   models,
        "providers": {
            "openai": bool(Config.OPENAI_API_KEY),
            "openrouter": bool(Config.OPENROUTER_API_KEY),
            "huggingface": bool(Config.HF_API_TOKEN),
            "groq":        bool(Config.GROQ_API_KEY),
        },
        "warnings": Config.validate(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# POST /sudo-auth  — browser submits sudo password here
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sudo-auth")
async def sudo_auth(request: Request) -> JSONResponse:
    """
    Receives the sudo password from the browser modal.
    Unblocks any executor thread waiting inside SudoManager.request_password().
    """
    try:
        body     = await request.json()
        password = body.get("password", "").strip()
        if not password:
            return JSONResponse({"error": "Contraseña vacía"}, status_code=400)

        from utils.sudo_manager import SudoManager
        SudoManager.get_instance().set_password(password)
        logger.info("[Server] /sudo-auth: password received, executor unblocked")
        return JSONResponse({"status": "ok"})

    except Exception as exc:
        logger.error(f"[Server] /sudo-auth error: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


# ─────────────────────────────────────────────────────────────────────────────
# POST /chat — streaming SSE
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: Request) -> Response:
    """
    Returns Server-Sent Events while processing.
    Extra events emitted during the stream:
      • "ping"       — keep-alive + status message
      • "needs_sudo" — executor is blocked waiting for sudo password
      • "done"       — final result
      • "error"      — something went wrong
    """
    try:
        body     = await request.json()
        question = body.get("question", "").strip()
        if not question:
            return JSONResponse({"response": "Escribe tu consulta."}, status_code=400)

        validation = _validator.validate(question)
        if validation.blocked:
            return JSONResponse(
                {"response": f"🚫 {validation.block_reason}"}, status_code=400
            )

        logger.info(f"[Server] /chat → {question[:80]}")
        _tracer.log("system", "http_chat_request", {"question": question[:80]})

    except Exception as exc:
        return JSONResponse({"response": f"❌ Bad request: {exc}"}, status_code=400)

    clean_input = validation.clean_input

    async def event_stream():
        loop = asyncio.get_running_loop()
        orch = _get_orchestrator()

        from utils.sudo_manager import SudoManager
        sudo_mgr = SudoManager.get_instance()

        future = loop.run_in_executor(None, orch.handle_user_input, clean_input)

        ping_messages = [
            "🔍 Analizando solicitud…",
            "📋 Consultando modelo de lenguaje…",
            "🌐 Escaneando red…",
            "💻 Ejecutando comandos…",
            "📊 Procesando resultados…",
            "⏳ Los scans completos pueden tardar varios minutos…",
        ]
        ping_idx = 0

        # Track whether we already emitted needs_sudo for the current wait
        sudo_prompt_active = False

        while not future.done():

            # ── Sudo password gate ────────────────────────────────────────
            if sudo_mgr.is_waiting_for_password():
                if not sudo_prompt_active:
                    # First time detecting this wait — emit the prompt
                    payload = json.dumps({
                        "type":    "needs_sudo",
                        "message": (
                            "🔐 Se requieren permisos sudo para ejecutar este comando. "
                            "Por favor, introduce la contraseña del sistema:"
                        ),
                    })
                    yield f"data: {payload}\n\n"
                    sudo_prompt_active = True

                # While waiting for password, send a quiet keep-alive
                payload = json.dumps({
                    "type":    "ping",
                    "message": "⏳ Esperando contraseña sudo…",
                })
                yield f"data: {payload}\n\n"

            else:
                # Reset so we can detect the next sudo request
                sudo_prompt_active = False

                # Normal progress ping
                msg     = ping_messages[ping_idx % len(ping_messages)]
                payload = json.dumps({"type": "ping", "message": msg})
                yield f"data: {payload}\n\n"
                ping_idx += 1

            # Wait up to 2 s for the future to complete before next iteration
            try:
                await asyncio.wait_for(asyncio.shield(future), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        # ── Collect result ────────────────────────────────────────────────
        try:
            response = await future
            payload  = json.dumps({"type": "done", "response": response})
            yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.error(f"[Server] Orchestrator error: {exc}", exc_info=True)
            payload = json.dumps({"type": "error", "response": f"❌ Error interno: {exc}"})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /config-model
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/config-model")
async def config_model(request: Request) -> JSONResponse:
    global _orchestrator
    try:
        body = await request.json()
        mode = body.get("mode", "").strip()
        if mode not in Config.MODELS:
            return JSONResponse(
                {"error": f"Modo inválido. Opciones: {list(Config.MODELS.keys())}"},
                status_code=400,
            )
        Config.DEFAULT_MODEL = mode
        _orchestrator = None
        logger.info(f"[Server] Modo → {mode}")
        return JSONResponse({"status": "ok", "mode": mode})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
