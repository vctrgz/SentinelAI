class DAGExecutor:

    def __init__(self, parallel_executor, router):
        self.parallel_executor = parallel_executor
        self.router = router

    def run(self, plan, translator, supervisor):

        tasks = plan["tasks"]

        completed = {}
        pending = {t["id"]: t for t in tasks}

        while pending:

            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t["depends_on"])
            ]

            if not ready:
                raise Exception("Deadlock detected")

            # 🔥 separar por modo
            parallel_tasks = []
            sequential_tasks = []
            exclusive_tasks = []

            for task in ready:
                mode = task.get("mode", "parallel")

                if mode == "parallel":
                    parallel_tasks.append(task)
                elif mode == "sequential":
                    sequential_tasks.append(task)
                elif mode == "exclusive":
                    exclusive_tasks.append(task)

            # 🔥 1. ejecutar exclusivas (una a una)
            for task in exclusive_tasks:
                result = self._execute_task(task, translator, supervisor)
                completed[task["id"]] = result
                del pending[task["id"]]

            # 🔥 2. ejecutar secuenciales
            for task in sequential_tasks:
                result = self._execute_task(task, translator, supervisor)
                completed[task["id"]] = result
                del pending[task["id"]]

            # 🔥 3. ejecutar paralelas
            if parallel_tasks:
                batch = {}

                for task in parallel_tasks:
                    translated = translator.run({"tasks": [task]}, {})
                    validated = supervisor.run(translated)

                    batch[task["id"]] = validated

                results = self.parallel_executor.execute(batch)

                for task_id, result in results.items():
                    completed[task_id] = result
                    del pending[task_id]

        return completed

    def _execute_task(self, task, translator, supervisor):
        translated = translator.run({"tasks": [task]}, {})
        validated = supervisor.run(translated)
        return self.router.execute(validated["commands"])