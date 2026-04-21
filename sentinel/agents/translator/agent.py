from app.config import Config
from utils.command_validator import CommandValidator
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
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

        user_prompt = f"""
            Tasks:
            {plan['tasks']}

            Context:
            {context}
            """

        response = self.llm.chat(self.system_prompt, user_prompt)

        return safe_json_parse(response)
    