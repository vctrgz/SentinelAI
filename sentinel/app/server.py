"""
SentinelAI — Servidor FastAPI.

Punto de entrada para uvicorn:
    uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

O desde VSCode con la configuración "SentinelAI: Servidor Web".
"""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.orchestrator import Orchestrator
from utils.input_validator import InputValidator
from utils.ollama_client import OllamaClient
from utils.logger import logger
from app.config import Config

# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="SentinelAI",
    description="Agente de ciberseguridad con arquitectura multiagente",
    version="1.0.0",
)

# ── Estado de sesión ──────────────────────────────────────────────────
_orchestrator: Orchestrator | None = None
_validator = InputValidator()


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        logger.info("[Server] Inicializando Orchestrator...")
        _orchestrator = Orchestrator()
    return _orchestrator


# ── Ciclo de vida ─────────────────────────────────────────────────────
@app.on_event("startup")
async def _startup():
    warnings = Config.validate()
    for w in warnings:
        logger.warning(f"[Config] {w}")
    client = OllamaClient()
    if client.is_available():
        logger.info(f"[Server] Ollama conectado. Modelos: {client.list_models()}")
    else:
        logger.warning(
            f"[Server] Ollama no disponible en {Config.ollama_base_url()}. "
            "Configura OLLAMA_HOST en .env"
        )


# ── Endpoints ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_chatbot():
    html_path = Path(__file__).parent.parent / "chatbot" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>chatbot/index.html no encontrado</h1>", status_code=404)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    client = OllamaClient()
    ok = client.is_available()
    return JSONResponse({
        "status":     "ok" if ok else "degraded",
        "ollama":     "connected" if ok else "unreachable",
        "ollama_url": Config.ollama_base_url(),
        "models":     client.list_models() if ok else [],
    })


@app.post("/chat")
async def chat(request: Request):
    try:
        body     = await request.json()
        question = body.get("question", "").strip()
        if not question:
            return JSONResponse({"response": "Escribe tu consulta."}, status_code=400)

        validation = _validator.validate(question)
        if validation.blocked:
            return JSONResponse({"response": f"🚫 {validation.block_reason}"}, status_code=400)

        logger.info(f"[Server] /chat -> {question[:80]}")
        response = _get_orchestrator().handle_user_input(validation.clean_input)
        return JSONResponse({"response": response})

    except Exception as e:
        logger.error(f"[Server] /chat error: {e}", exc_info=True)
        return JSONResponse({"response": f"❌ Error interno: {e}"}, status_code=500)


@app.post("/config-model")
async def config_model(request: Request):
    global _orchestrator
    try:
        body = await request.json()
        mode = body.get("mode", "").strip()
        if mode not in Config.MODELS:
            return JSONResponse(
                {"error": f"Modo inválido. Opciones: {list(Config.MODELS.keys())}"},
                status_code=400
            )
        Config.DEFAULT_MODEL = mode
        _orchestrator = None
        logger.info(f"[Server] Modo -> {mode} ({Config.MODELS[mode]})")
        return JSONResponse({"status": "ok", "mode": mode, "model": Config.MODELS[mode]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)