import os
from dotenv import load_dotenv

load_dotenv()


class Config:

    # 🔹 Modelos LLM
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
    DEFAULT_MODEL = 'balanceado'
    MODELS = {
        'defensivo': 'foundation-sec:latest',           # Experto en terminología y SOC
        'ofensivo':  'dolphin-llama3:latest',           # Sin censura para Pentesting
        'balanceado': 'qwen2.5:latest'                  # El mejor siguiendo reglas (Recomendado)
    }

    # 🔹 IP LLM
    WINDOWS_IP = "192.168.1.49"
    # WINDOWS_IP = "10.30.212.36"

    # 🔹 Control de ejecución
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", 5))
    TIMEOUT = int(os.getenv("TIMEOUT", 30))

    # 🔹 Seguridad
    REQUIRE_CONFIRMATION = True
    ALLOW_DANGEROUS_COMMANDS = False

    # 🔹 Paths
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    MEMORY_DIR = os.path.join(BASE_DIR, "memory")

    # 🔹 Sandbox
    SANDBOX_MODE = True
    SANDBOX_PATH = os.path.join(BASE_DIR, "sandbox")

    # 🔹 Debug
    DEBUG = True