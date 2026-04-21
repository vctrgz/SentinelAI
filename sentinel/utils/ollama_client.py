import requests
import json
from app.config import Config
from memory.context_manager import ContextManager
from utils.retry_handler import RetryHandler


class OllamaClient:

    def __init__(self, LLM):
        self.base_url = f"http://{Config.WINDOWS_IP}:11434/api/chat"
        self.model = LLM
        self.context_manager = ContextManager()
        self.retry_handler   = RetryHandler(max_retries=3)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        # Truncar si supera ventana de contexto
        system_prompt, user_prompt = self.context_manager.truncate_prompt(
            system_prompt, user_prompt
        )
 
        # Ejecutar con reintentos automáticos en errores de red
        success, result = self.retry_handler.execute_with_retry(
            self._do_chat,
            system_prompt, user_prompt,
            operation_name=f"chat({self.model})"
        )
 
        if not success:
            raise Exception(f"Ollama no disponible tras 3 reintentos: {result}")
 
        return result
 
    def _do_chat(self, system_prompt: str, user_prompt: str) -> str:
        """Llamada HTTP real a Ollama (sin reintentos — los gestiona retry_handler)."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ],
            "stream": False
        }
        try:
            response = requests.post(self.base_url, json=payload, timeout=120)
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"No se puede conectar con Ollama en {self.base_url}: {e}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Timeout esperando respuesta de Ollama ({self.model})")
 
        if response.status_code != 200:
            raise Exception(f"Ollama error {response.status_code}: {response.text[:300]}")
 
        return response.json()["message"]["content"]
 
    def is_available(self) -> bool:
        """Health check"""
        try:
            url = self.base_url.replace("/api/chat", "/api/tags")
            return requests.get(url, timeout=5).status_code == 200
        except Exception:
            return False
 
    def list_models(self) -> list:
        try:
            url = self.base_url.replace("/api/chat", "/api/tags")
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []
 