from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_loader import build_system_prompt


class SupervisorAgent:

    def __init__(self):
        self.llm = OllamaClient()

    def run(self, commands: dict, objective: str = "") -> dict:

        system_prompt = build_system_prompt("agents/supervisor", objective)

        user_prompt = f"""
Commands:
{commands}
"""

        response = self.llm.chat(system_prompt, user_prompt)

        return safe_json_parse(response)