from utils.logger import setup_logger

logger = setup_logger()


class DAGExecutor:
    """
    Ejecuta un plan de tareas respetando dependencias (DAG).
    Soporta tres modos de ejecución por tarea:
    - parallel:   se ejecutan en paralelo con otras del mismo batch
    - sequential: se ejecutan en orden, una tras otra
    - exclusive:  se ejecutan solas, sin concurrencia
    """

    def __init__(self, parallel_executor, router):
        self.parallel_executor = parallel_executor
        self.router = router

    def run(self, plan: dict, translator, supervisor, context: dict = None) -> dict:
        tasks = plan.get("tasks", [])
        if not tasks:
            logger.warning("[DAGExecutor] El plan no contiene tareas.")
            return {}

        task_context = context or {}
        completed = {}
        pending = {t["id"]: t for t in tasks}

        while pending:
            # Tareas listas: todas sus dependencias están completadas
            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t.get("depends_on", []))
            ]

            if not ready:
                remaining = list(pending.keys())
                raise Exception(
                    f"Deadlock detectado en el DAG. "
                    f"Tareas bloqueadas: {remaining}"
                )

            parallel_tasks   = []
            sequential_tasks = []
            exclusive_tasks  = []

            for task in ready:
                mode = task.get("mode", "parallel")
                if mode == "parallel":
                    parallel_tasks.append(task)
                elif mode == "sequential":
                    sequential_tasks.append(task)
                elif mode == "exclusive":
                    exclusive_tasks.append(task)
                else:
                    parallel_tasks.append(task)  # default

            # 1. Exclusivas: una a una, sin concurrencia
            for task in exclusive_tasks:
                logger.info(f"[DAGExecutor] Ejecutando exclusiva: {task['id']}")
                result = self._execute_task(task, translator, supervisor, task_context)
                completed[task["id"]] = result
                del pending[task["id"]]

            # 2. Secuenciales: en orden
            for task in sequential_tasks:
                logger.info(f"[DAGExecutor] Ejecutando secuencial: {task['id']}")
                result = self._execute_task(task, translator, supervisor, task_context)
                completed[task["id"]] = result
                del pending[task["id"]]

            # 3. Paralelas: todas juntas con ThreadPoolExecutor
            if parallel_tasks:
                batch = {}
                for task in parallel_tasks:
                    logger.info(f"[DAGExecutor] Preparando paralela: {task['id']}")
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
        """
        Extrae los comandos aprobados de cualquiera de los dos formatos.
        """
        if not isinstance(supervisor_output, dict):
            return []

        # Formato correcto del supervisor según AGENTS.md
        approved = supervisor_output.get("approved", [])

        # Compatibilidad con formato alternativo legacy
        if not approved and "commands" in supervisor_output:
            approved = supervisor_output["commands"]

        return approved if isinstance(approved, list) else []

    def _execute_task(self, task: dict, translator, supervisor, context: dict) -> dict:
        """Traduce, supervisa y ejecuta una tarea individual."""
        translated = translator.run({"tasks": [task]}, context)
        validated  = supervisor.run(translated)
        commands   = self._extract_commands(validated)

        if not commands:
            logger.warning(f"[DAGExecutor] Tarea {task['id']} sin comandos aprobados.")
            return {
                "status":   "skipped",
                "reason":   "No approved commands from supervisor",
                "commands": []
            }

        return self.router.execute(commands)