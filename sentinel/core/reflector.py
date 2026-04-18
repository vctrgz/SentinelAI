from agents.reflector.agent import ReflectorAgent


class Reflector:

    def __init__(self):
        self.agent = ReflectorAgent()

    def analyze(self, execution_results: list, task: dict) -> dict:
        return self.agent.run(execution_results, task)