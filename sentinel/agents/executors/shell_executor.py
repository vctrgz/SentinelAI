import subprocess
from agents.executors.base_executor import BaseExecutor


class ShellExecutor(BaseExecutor):

    def execute(self, cmd: str) -> dict:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True
            )

            return {
                "command": cmd,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }

        except Exception as e:
            return {
                "command": cmd,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }