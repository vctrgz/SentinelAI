from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_loader import build_system_prompt
import os
from app.config import Config


class OrchestratorAgent:

    def __init__(self):
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, 'balanceado')
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.system_prompt = build_system_prompt("agents/orchestrator")

    def interpret(self, user_input: str) -> dict:

        user_prompt = f"""
User input:
{user_input}

Return structured JSON.
"""

        response = self.llm.chat(self.system_prompt, user_prompt)

        return safe_json_parse(response)

    def format_confirmation(self, commands: list) -> str:

        user_prompt = f"""
Explain these commands to a human:

{commands}
"""

        return self.llm.chat(self.system_prompt, user_prompt)