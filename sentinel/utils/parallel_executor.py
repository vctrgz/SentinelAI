from concurrent.futures import ThreadPoolExecutor, as_completed


class ParallelExecutor:

    def __init__(self, router):
        self.router = router

    def execute(self, tasks_with_commands: dict) -> dict:
        """
        tasks_with_commands:
        {
            task_id: {
                "commands": [...]
            }
        }
        """

        results = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}

            for task_id, data in tasks_with_commands.items():
                futures[executor.submit(self.router.execute, data["commands"])] = task_id

            for future in as_completed(futures):
                task_id = futures[future]
                results[task_id] = future.result()

        return results