import json
from app.config import Config
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt


class SupervisorAgent:

    def __init__(self) -> None:
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, "qwen2.5:latest")
        self.llm          = OllamaClient(OLLAMA_MODEL)
        self.system_prompt = build_system_prompt("agents/supervisor")  # ← Fix: 1 arg, no 2

    def run(self, commands: dict, objective: str = "") -> dict:
        user_prompt = f"""
{build_runtime_context_block()}

Objective: {objective}

Commands:
{json.dumps(commands, ensure_ascii=False)}
"""
        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)
        return safe_json_parse(response)
