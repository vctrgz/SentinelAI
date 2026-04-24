"""
utils/ollama_client.py

HTTP client for the Ollama API.
Every API call is timed and traced to stdout + logs/runtime_human.log.
"""

import time
import requests
from app.config import Config
from memory.context_manager import ContextManager
from utils.retry_handler import RetryHandler
from utils.runtime_tracer import get_tracer


class OllamaClient:

    def __init__(self, llm_name: str) -> None:
        self.base_url        = Config.OLLAMA_BASE_URL
        self.model           = Config.MODELS.get(llm_name, llm_name)
        self.context_manager = ContextManager()
        self.retry_handler   = RetryHandler(max_retries=3)
        self._tracer         = get_tracer()
        self._caller_hint    = llm_name   # used in trace output

    def chat(self, system_prompt: str, user_prompt: str, expect_json: bool = False) -> str:
        system_prompt, user_prompt = self.context_manager.truncate_prompt(
            system_prompt, user_prompt
        )

        self._tracer.log("llm", f"ollama_request:{self.model}", {
            "expect_json":      expect_json,
            "sys_prompt_chars": len(system_prompt),
            "user_prompt_chars": len(user_prompt),
        })

        t0 = time.monotonic()

        success, result = self.retry_handler.execute_with_retry(
            self._do_chat,
            system_prompt,
            user_prompt,
            expect_json,
            operation_name=f"chat({self.model})",
        )

        duration = time.monotonic() - t0

        if not success:
            self._tracer.log("llm", f"ollama_failed:{self.model}",
                             {"error": str(result)[:120], "duration_s": round(duration, 2)},
                             level="ERROR")
            raise Exception(f"Ollama no disponible tras 3 reintentos: {result}")

        self._tracer.log_llm_call(
            model=self.model,
            agent=self._caller_hint,
            duration_s=duration,
            tokens_est=len(str(result)) // 4,
            expect_json=expect_json,
        )

        return result

    def _do_chat(self, system_prompt: str, user_prompt: str, expect_json: bool = False) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": False,
        }
        if expect_json:
            payload["format"] = "json"

        try:
            response = requests.post(
                self.base_url,
                json=payload,
                timeout=Config.OLLAMA_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"No se puede conectar con Ollama en {self.base_url}: {exc}"
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Timeout esperando respuesta de Ollama ({self.model}) "
                f"tras {Config.OLLAMA_TIMEOUT}s"
            )

        if response.status_code != 200:
            raise Exception(
                f"Ollama error {response.status_code}: {response.text[:300]}"
            )

        return response.json()["message"]["content"]

    def is_available(self) -> bool:
        try:
            url = self.base_url.replace("/api/chat", "/api/tags")
            return requests.get(url, timeout=5).status_code == 200
        except Exception:
            return False

    def list_models(self) -> list:
        try:
            url      = self.base_url.replace("/api/chat", "/api/tags")
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            pass
        return []