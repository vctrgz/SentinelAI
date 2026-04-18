import requests
import json
from app.config import Config


class OllamaClient:

    def __init__(self, LLM):
        self.base_url = f"http://{Config.WINDOWS_IP}:11434/api/chat"
        self.model = LLM

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }

        response = requests.post(self.base_url, json=payload)

        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.text}")

        data = response.json()
        return data["message"]["content"]