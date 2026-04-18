from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_loader import build_system_prompt


class PlannerAgent:

    def __init__(self):
        self.llm = OllamaClient()
        self.system_prompt = build_system_prompt("agents/planner")

    def run(self, task: dict) -> dict:

        user_prompt = f"""
Objective:
{task['objective']}

Context:
{task['context']}
"""

        response = self.llm.chat(self.system_prompt, user_prompt)

        return safe_json_parse(response)