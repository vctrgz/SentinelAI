from agents.executors.shell_executor import ShellExecutor


class TaskRouter:

    def __init__(self):
        self.shell_executor = ShellExecutor()

    def execute(self, commands: list) -> list:
        results = []

        for cmd in commands:
            result = self.shell_executor.execute(cmd)
            results.append(result)

        return results