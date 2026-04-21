import uuid

from agents.orchestrator.agent import OrchestratorAgent
from core.planner import Planner
from core.reflector import Reflector
from core.supervisor import Supervisor
from core.task_router import TaskRouter
from core.translator import Translator
from utils.dag_executor import DAGExecutor
from utils.parallel_executor import ParallelExecutor
from memory.memory import AgentMemory        
from utils.logger import setup_logger
from app.config import Config
from app.constants import STATUS_SUCCESS, STATUS_RETRY, STATUS_FATAL

logger = setup_logger()


class Orchestrator:

    def __init__(self):
        self.agent     = OrchestratorAgent()
        self.planner   = Planner()
        self.translator = Translator()
        self.supervisor = Supervisor()
        self.reflector  = Reflector()
        self.router     = TaskRouter()

        # Sistema de memoria multicapa
        self.memory = AgentMemory()

        self.parallel_executor = ParallelExecutor(self.router)

        # DAGExecutor.__init__ requiere (parallel_executor, router)
        self.dag_executor = DAGExecutor(self.parallel_executor, self.router)


    # ------------------------------------------------------------------ #
    # Punto de entrada principal                                           #
    # ------------------------------------------------------------------ #

    def handle_user_input(self, user_input: str) -> str:
        try:
            # Resetear memoria de trabajo para la nueva tarea
            self.memory.reset_working()

            interpreted = self.agent.interpret(user_input)
            task = self._create_task(interpreted)

            # Bucle ReAct en lugar del único ciclo lineal
            result = self._react_loop(task)
            return result

        except Exception as e:
            logger.error(f"[Orchestrator] Error en handle_user_input: {e}", exc_info=True)
            return f"❌ Error al procesar la solicitud: {str(e)}"


    # ------------------------------------------------------------------ #
    # Construcción del objeto tarea                                        #
    # ------------------------------------------------------------------ #

    def _create_task(self, interpreted: dict) -> dict:
        return {
            "task_id":    str(uuid.uuid4()),
            "objective":  interpreted.get("objective", ""),
            "constraints": interpreted.get("constraints", []),
            "priority":   interpreted.get("priority", "medium"),
            "context": {
                "history":        [],     # historial de intentos de esta tarea
                "errors":         [],     # errores acumulados entre iteraciones
                "attempt":        0,
                # Fix #8: inyectar el resumen de memoria episódica en el contexto
                "memory_summary": self.memory.get_context_summary()
            }
        }


    # ------------------------------------------------------------------ #
    # Bucle ReAct — Reason → Act → Observe                        #
    # ------------------------------------------------------------------ #

    def _react_loop(self, task: dict) -> str:
        """
        Implementación del patrón ReAct (Yao et al., 2022):
        En cada iteración el agente:
          1. REASON  — planifica basándose en el contexto actual
          2. ACT     — traduce, supervisa y ejecuta las tareas
          3. OBSERVE — reflexiona sobre los resultados y decide
                       si terminar (success/fatal) o reintentar (retry)

        CONFIG: MAX_ITERATIONS controla el número máximo de ciclos.
        """
        max_iterations = Config.MAX_ITERATIONS

        for attempt in range(1, max_iterations + 1):
            logger.info(f"[ReAct] ── Iteración {attempt}/{max_iterations} ──────────────")
            task["context"]["attempt"] = attempt

            try:
                # ── REASON: planificar ──────────────────────────────────
                logger.info("[ReAct] Planificando...")
                plan = self.planner.run(task)

                # ── ACT: ejecutar el DAG ────────────────────────────────
                logger.info("[ReAct] Ejecutando tareas...")
                results = self.dag_executor.run(
                    plan,
                    self.translator,
                    self.supervisor
                )

                # ── OBSERVE: reflexionar ────────────────────────────────
                logger.info("[ReAct] Reflexionando...")
                result_list = (
                    list(results.values())
                    if isinstance(results, dict)
                    else results
                )
                reflection = self.reflector.run(result_list, task)

                status = reflection.get("status", STATUS_FATAL)
                reason = reflection.get("reason", "")

                # Guardar episodio en memoria episódica
                self.memory.add_episode({
                    "attempt":   attempt,
                    "objective": task["objective"],
                    "plan":      plan,
                    "results":   result_list,
                    "status":    status,
                    "reason":    reason
                })

                # Actualizar contexto de tarea con lo observado
                task["context"]["history"].append({
                    "attempt":        attempt,
                    "status":         status,
                    "reason":         reason,
                    "result_summary": str(result_list)[:500]
                })
                # Actualizar resumen de memoria para la próxima iteración
                task["context"]["memory_summary"] = self.memory.get_context_summary()

                logger.info(f"[ReAct] Estado: {status} | {reason}")

                # ── Decisión post-observación ───────────────────────────
                if status == STATUS_SUCCESS:
                    logger.info("[ReAct] ✅ Éxito.")
                    return self.agent.format_confirmation(result_list)

                elif status == STATUS_RETRY:
                    logger.info(f"[ReAct] 🔄 Reintentando: {reason}")
                    task["context"]["errors"].append(reason)
                    continue  # siguiente iteración del bucle

                else:  # STATUS_FATAL
                    logger.error(f"[ReAct] ❌ Fallo fatal: {reason}")
                    return f"Error fatal tras {attempt} intento(s): {reason}"

            except Exception as e:
                error_msg = str(e)
                logger.error(f"[ReAct] Excepción en iteración {attempt}: {error_msg}", exc_info=True)
                task["context"]["errors"].append(error_msg)

                if attempt == max_iterations:
                    return f"❌ Error tras {attempt} intento(s): {error_msg}"
                # En iteraciones intermedias, intentar recuperarse
                continue

        return f"⚠️ Máximo de iteraciones ({max_iterations}) alcanzado sin resolver la tarea."


    # ------------------------------------------------------------------ #
    # HITL: confirmación humana                                            #
    # ------------------------------------------------------------------ #

    def _ask_user_confirmation(self, commands: list) -> bool:
        """Human-In-The-Loop: explica los comandos y pide confirmación."""
        explanation = self.agent.format_confirmation(commands)
        print("\n⚠️  Confirmación requerida:\n")
        print(explanation)
        response = input("\n¿Continuar? (y/n): ").strip().lower()
        return response == "y"