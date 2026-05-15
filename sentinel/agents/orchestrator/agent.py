import json
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt
from app.config import Config


class OrchestratorAgent:

    def __init__(self):
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, 'balanceado')
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.system_prompt = build_system_prompt("agents/orchestrator")

    def interpret(self, user_input: str) -> dict:

        user_prompt = f"""
{build_runtime_context_block([
    "Resolve whether the request depends on current or time-sensitive information before interpreting intent."
])}

User input:
{json.dumps({"input": user_input}, ensure_ascii=False)}

Return structured JSON.
"""

        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)

        return safe_json_parse(response)

    def format_confirmation(self, commands: list) -> str:

        user_prompt = f"""
{build_runtime_context_block()}

Explain these commands to a human:

{json.dumps(commands, ensure_ascii=False)}
"""

        return self.llm.chat(self.system_prompt, user_prompt)
