"""
app/config.py

Configuration for SentinelAI.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=False)


class Config:
    HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

    HF_MODEL_PRIMARY = os.getenv("HF_MODEL_PRIMARY", "mistralai/Mistral-7B-Instruct-v0.3")
    HF_MODEL_FALLBACK = os.getenv("HF_MODEL_FALLBACK", "HuggingFaceH4/zephyr-7b-beta")

    GROQ_MODEL_PRIMARY = os.getenv("GROQ_MODEL_PRIMARY", "llama-3.1-8b-instant")
    GROQ_MODEL_FALLBACK = os.getenv("GROQ_MODEL_FALLBACK", "llama-3.3-70b-versatile")
    GROQ_MODEL_TERTIARY = os.getenv("GROQ_MODEL_TERTIARY", "groq/compound")

    OPENROUTER_MODEL_PRIMARY = os.getenv("OPENROUTER_MODEL_PRIMARY", "meta-llama/llama-3.3-70b-instruct")
    OPENROUTER_MODEL_FALLBACK = os.getenv("OPENROUTER_MODEL_FALLBACK", "")
    OPENROUTER_MODEL_SECONDARY = os.getenv("OPENROUTER_MODEL_SECONDARY", "")

    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
    LLM_EMPTY_RESPONSE_RETRIES = int(os.getenv("LLM_EMPTY_RESPONSE_RETRIES", "1"))

    DEFAULT_MODEL = "balanceado"
    MODELS = {
        "defensivo": "mistralai/Mistral-7B-Instruct-v0.3",
        "ofensivo": "HuggingFaceH4/zephyr-7b-beta",
        "balanceado": "llama-3.1-8b-instant",
    }

    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "5"))
    TIMEOUT = int(os.getenv("TIMEOUT", "60"))

    REQUIRE_CONFIRMATION = os.getenv("REQUIRE_CONFIRMATION", "true").lower() == "true"
    ALLOW_DANGEROUS_COMMANDS = os.getenv("ALLOW_DANGEROUS_COMMANDS", "false").lower() == "true"

    LOG_DIR = os.path.join(BASE_DIR, "logs")
    MEMORY_DIR = os.path.join(BASE_DIR, "memory")
    SANDBOX_PATH = os.path.join(BASE_DIR, "sandbox")

    SANDBOX_MODE = os.getenv("SANDBOX_MODE", "true").lower() == "true"
    DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "python:3.11-slim")

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls) -> list[str]:
        warnings: list[str] = []

        if not os.path.exists(DOTENV_PATH):
            warnings.append(f"No se encontro .env en {DOTENV_PATH}")

        if not cls.OPENROUTER_API_KEY:
            warnings.append(
                "OPENROUTER_API_KEY no configurado - OpenRouter deshabilitado. "
                "Obten uno en: https://openrouter.ai/keys"
            )
        if not cls.HF_API_TOKEN:
            warnings.append(
                "HF_API_TOKEN no configurado - HuggingFace deshabilitado. "
                "Obten uno en: https://huggingface.co/settings/tokens"
            )
        if not cls.GROQ_API_KEY:
            warnings.append(
                "GROQ_API_KEY no configurado - Groq deshabilitado. "
                "Obten uno en: https://console.groq.com/keys"
            )
        if not cls.OPENROUTER_API_KEY and not cls.HF_API_TOKEN and not cls.GROQ_API_KEY:
            warnings.append("Ningun proveedor LLM configurado. El sistema no podra generar respuestas.")
        if cls.MAX_ITERATIONS < 1:
            warnings.append("MAX_ITERATIONS debe ser >= 1")
        if cls.TIMEOUT < 5:
            warnings.append("TIMEOUT muy bajo (< 5s)")

        return warnings
