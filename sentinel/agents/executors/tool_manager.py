import shutil
import subprocess


class ToolManager:

    def install_tool(self, tool_name: str) -> dict:

        try:
            cmd = f"sudo apt install {tool_name} -y"

            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True
            )

            return {
                "tool": tool_name,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "installed": result.returncode == 0
            }

        except Exception as e:
            return {
                "tool": tool_name,
                "error": str(e)
            }
        
    def is_installed(self, tool: str) -> bool:
        return shutil.which(tool) is not None

    def ensure_tool(self, tool: str) -> dict:

        if self.is_installed(tool):
            return {"tool": tool, "status": "already_installed"}

        return self.install_tool(tool)