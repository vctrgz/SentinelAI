from typing import Optional
from utils.logger import setup_logger

logger = setup_logger()


class DAGExecutor:
    """
    Ejecuta un plan de tareas respetando dependencias (DAG).
    Modos: parallel | sequential | exclusive
    """

    def __init__(self, parallel_executor, router) -> None:
        self.parallel_executor = parallel_executor
        self.router = router

    def run(
        self,
        plan: dict,
        translator,
        supervisor,
        context: Optional[dict] = None,   # ← Fix: era dict = None (ilegal para Pylance)
    ) -> dict:
        tasks = plan.get("tasks", [])
        if not tasks:
            logger.warning("[DAGExecutor] El plan no contiene tareas.")
            return {}

        task_context = context or {}
        completed: dict = {}
        pending = {t["id"]: t for t in tasks}

        while pending:
            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t.get("depends_on", []))
            ]

            if not ready:
                raise Exception(
                    f"Deadlock en el DAG. Tareas bloqueadas: {list(pending.keys())}"
                )

            parallel_tasks:   list = []
            sequential_tasks: list = []
            exclusive_tasks:  list = []

            for task in ready:
                mode = task.get("mode", "parallel")
                if mode == "sequential":
                    sequential_tasks.append(task)
                elif mode == "exclusive":
                    exclusive_tasks.append(task)
                else:
                    parallel_tasks.append(task)

            # 1. Exclusivas
            for task in exclusive_tasks:
                logger.info(f"[DAGExecutor] Exclusiva: {task['id']}")
                result = self._execute_task(task, translator, supervisor, task_context)
                completed[task["id"]] = result
                del pending[task["id"]]

            # 2. Secuenciales
            for task in sequential_tasks:
                logger.info(f"[DAGExecutor] Secuencial: {task['id']}")
                result = self._execute_task(task, translator, supervisor, task_context)
                completed[task["id"]] = result
                del pending[task["id"]]

            # 3. Paralelas
            if parallel_tasks:
                batch: dict = {}
                for task in parallel_tasks:
                    logger.info(f"[DAGExecutor] Paralela: {task['id']}")
                    translated = translator.run({"tasks": [task]}, task_context)
                    validated  = supervisor.run(translated)
                    commands   = self._extract_commands(validated)
                    batch[task["id"]] = {"commands": commands}

                results = self.parallel_executor.execute(batch)
                for task_id, result in results.items():
                    completed[task_id] = result
                    del pending[task_id]

        return completed

    def _extract_commands(self, supervisor_output: dict) -> list:
        if not isinstance(supervisor_output, dict):
            return []
        approved = supervisor_output.get("approved", [])
        if not approved and "commands" in supervisor_output:
            approved = supervisor_output["commands"]
        return approved if isinstance(approved, list) else []

    def _execute_task(self, task: dict, translator, supervisor, context: dict) -> dict:
        translated = translator.run({"tasks": [task]}, context)
        validated  = supervisor.run(translated)
        commands   = self._extract_commands(validated)
        if not commands:
            return {"status": "skipped", "reason": "No approved commands", "commands": []}
        return self.router.execute(commands)