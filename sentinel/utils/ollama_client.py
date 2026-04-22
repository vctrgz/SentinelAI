import requests
from app.config import Config
from memory.context_manager import ContextManager
from utils.retry_handler import RetryHandler


class OllamaClient:
    def __init__(self, llm_name: str):
        self.base_url = Config.OLLAMA_BASE_URL
        self.model = Config.MODELS.get(llm_name, llm_name)
        self.context_manager = ContextManager()
        self.retry_handler = RetryHandler(max_retries=3)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        system_prompt, user_prompt = self.context_manager.truncate_prompt(
            system_prompt, user_prompt
        )

        success, result = self.retry_handler.execute_with_retry(
            self._do_chat,
            system_prompt,
            user_prompt,
            operation_name=f"chat({self.model})",
        )

        if not success:
            raise Exception(f"Ollama no disponible tras 3 reintentos: {result}")

        return result

    def _do_chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        try:
            response = requests.post(
                self.base_url,
                json=payload,
                timeout=Config.OLLAMA_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"No se puede conectar con Ollama en {self.base_url}: {e}")
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Timeout esperando respuesta de Ollama ({self.model}) "
                f"tras {Config.OLLAMA_TIMEOUT}s"
            )

        if response.status_code != 200:
            raise Exception(f"Ollama error {response.status_code}: {response.text[:300]}")

        return response.json()["message"]["content"]

    def is_available(self) -> bool:
        try:
            url = self.base_url.replace("/api/chat", "/api/tags")
            return requests.get(url, timeout=5).status_code == 200
        except Exception:
            return False

    def list_models(self) -> list:
        try:
            url = self.base_url.replace("/api/chat", "/api/tags")
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return [model["name"] for model in response.json().get("models", [])]
        except Exception:
            pass
        return []
