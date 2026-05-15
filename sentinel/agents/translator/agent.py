import json
from app.config import Config
from utils.command_validator import CommandValidator
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt


class TranslatorAgent:

    def __init__(self):
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, 'balanceado')
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.validator = CommandValidator()
        self.system_prompt = build_system_prompt("agents/translator")

    def validate_commands(self, commands: list) -> list:

        validated = []

        for cmd_obj in commands:
            cmd = cmd_obj["cmd"]

            result = self.validator.validate(cmd)

            cmd_obj["validation"] = result

            validated.append(cmd_obj)

        return validated
    
    def run(self, plan: dict, context: dict) -> dict:
        compact_context = self.llm.context_manager._truncate_context(context)

        user_prompt = f"""
{build_runtime_context_block()}

Tasks:
{json.dumps(plan.get('tasks', []), ensure_ascii=False)}

Context:
{json.dumps(compact_context, ensure_ascii=False)}

Return ONLY valid JSON with this schema:
{{
  "commands": [
    {{
      "cmd": "string",
      "risk": "low|medium|high"
    }}
  ]
}}
"""

        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)
        try:
            return safe_json_parse(response)
        except ValueError:
            repair_prompt = f"""
Convert the following response into valid JSON only.

Required schema:
{{
  "commands": [
    {{
      "cmd": "string",
      "risk": "low|medium|high"
    }}
  ]
}}

Original response:
{response}
"""
            repaired = self.llm.chat(self.system_prompt, repair_prompt, expect_json=True)
            return safe_json_parse(repaired)
    
