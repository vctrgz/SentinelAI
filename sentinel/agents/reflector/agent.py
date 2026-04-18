from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from sentinel.utils.prompt_loader import build_system_prompt


class ReflectorAgent:

    def __init__(self):
        self.llm = OllamaClient()
        self.system_prompt = build_system_prompt("agents/reflector")

    def run(self, execution_results: list, task: dict) -> dict:

        user_prompt = f"""
Execution Results:
{execution_results}

Task:
{task}
"""

        response = self.llm.chat(self.system_prompt, user_prompt)

        return safe_json_parse(response)