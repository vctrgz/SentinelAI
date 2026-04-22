import os
from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=False)


def _normalize_ollama_host(raw_host: str, fallback_host: str) -> str:
    host = (raw_host or "").strip()
    if not host:
        return fallback_host
    if host == "0.0.0.0":
        return fallback_host
    return host


class Config:
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
    DEFAULT_MODEL = "balanceado"
    MODELS = {
        "defensivo": "foundation-sec:latest",
        "ofensivo": "dolphin-llama3:latest",
        "balanceado": "qwen2.5:latest",
    }

    WINDOWS_IP = "192.168.1.49"

    OLLAMA_HOST = _normalize_ollama_host(
        os.getenv("OLLAMA_HOST", WINDOWS_IP),
        WINDOWS_IP,
    )
    OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
    OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))

    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "5"))
    TIMEOUT = int(os.getenv("TIMEOUT", "30"))

    REQUIRE_CONFIRMATION = os.getenv("REQUIRE_CONFIRMATION", "true").lower() == "true"
    ALLOW_DANGEROUS_COMMANDS = (
        os.getenv("ALLOW_DANGEROUS_COMMANDS", "false").lower() == "true"
    )

    LOG_DIR = os.path.join(BASE_DIR, "logs")
    MEMORY_DIR = os.path.join(BASE_DIR, "memory")
    SANDBOX_PATH = os.path.join(BASE_DIR, "sandbox")

    SANDBOX_MODE = os.getenv("SANDBOX_MODE", "true").lower() == "true"
    DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "python:3.11-slim")

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls) -> list[str]:
        warnings = []

        if not os.path.exists(DOTENV_PATH):
            warnings.append(f"No se encontro .env en {DOTENV_PATH}")

        raw_host = os.getenv("OLLAMA_HOST", "")
        if raw_host.strip() == "0.0.0.0":
            warnings.append(
                "OLLAMA_HOST=0.0.0.0 no es valido para clientes; usando el host normalizado "
                f"{cls.OLLAMA_HOST}"
            )

        if not cls.MODELS.get(cls.DEFAULT_MODEL):
            warnings.append(
                f"DEFAULT_MODEL='{cls.DEFAULT_MODEL}' no existe en MODELS. "
                f"Opciones validas: {list(cls.MODELS.keys())}"
            )

        if cls.MAX_ITERATIONS < 1:
            warnings.append("MAX_ITERATIONS debe ser >= 1")

        if cls.TIMEOUT < 5:
            warnings.append("TIMEOUT muy bajo (< 5s) - puede causar fallos en comandos")

        if cls.OLLAMA_TIMEOUT < 30:
            warnings.append(
                "OLLAMA_TIMEOUT muy bajo (< 30s) - puede causar reintentos innecesarios"
            )

        return warnings
