import uuid

from agents.orchestrator.agent import OrchestratorAgent
from sentinel.core.planner import Planner
from sentinel.core.reflector import Reflector
from sentinel.core.supervisor import Supervisor
from sentinel.core.task_router import TaskRouter
from sentinel.core.translator import Translator
from sentinel.utils.dag_executor import DAGExecutor
from sentinel.utils.parallel_executor import ParallelExecutor
# ... resto imports


class Orchestrator:

    def __init__(self):
        self.agent = OrchestratorAgent()
        self.planner = Planner()
        self.translator = Translator()
        self.supervisor = Supervisor()
        self.reflector = Reflector()
        self.router = TaskRouter()
        # Ejecutor de tareas en paralelo en prueba
        self.parallel_executor = ParallelExecutor(self.router)
        self.dag_executor = DAGExecutor(self.parallel_executor)

    def handle_user_input(self, user_input: str) -> str:

        # 🔹 Interpretar con LLM
        interpreted = self.agent.interpret(user_input)

        task = self._create_task(interpreted)

        result = self._execution_loop(task)

        return result

    def _create_task(self, interpreted: dict) -> dict:
        return {
            "task_id": str(uuid.uuid4()),
            "objective": interpreted["objective"],
            "context": {
                "history": [],
                "errors": [],
                "attempt": 1
            }
        }

    # 🔐 HITL mejorado
    def _ask_user_confirmation(self, commands: list) -> bool:

        explanation = self.agent.format_confirmation(commands)

        print("\n⚠️ Confirmación requerida:\n")
        print(explanation)

        response = input("\n¿Continuar? (y/n): ")

        return response.lower() == "y"
    
    # 🔐 Supervisor mejorado en pruebas
    def _execution_loop(self, task):

        plan = self.planner.run(task)

        results = self.dag_executor.run(
            plan,
            self.translator,
            self.supervisor
        )

        reflection = self.reflector.run(results)

        return reflection