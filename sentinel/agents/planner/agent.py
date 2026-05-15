import json
from app.config import Config
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt


class PlannerAgent:

    def __init__(self):
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, 'balanceado')
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.system_prompt = build_system_prompt("agents/planner")

    def run(self, task: dict) -> dict:
        task_context = self.llm.context_manager.prepare_task_context(task)

        user_prompt = f"""
{build_runtime_context_block()}

Objective:
{task['objective']}

Context:
{json.dumps(task_context, ensure_ascii=False)}
"""

        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)

        return safe_json_parse(response)
