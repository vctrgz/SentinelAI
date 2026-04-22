from agents.executors.shell_executor import ShellExecutor


class TaskRouter:
    def __init__(self):
        self.shell_executor = ShellExecutor()

    def execute(self, commands: list) -> list:
        results = []

        for item in commands:
            cmd = item.get("cmd", "") if isinstance(item, dict) else str(item)
            if not cmd or not str(cmd).strip():
                results.append(
                    {
                        "command": "",
                        "stdout": "",
                        "stderr": "Comando vacio o invalido",
                        "returncode": -1,
                    }
                )
                continue

            results.append(self.shell_executor.execute(str(cmd)))

        return results
