"""
agents/executors/shell_executor.py

Executes shell commands safely (shell=False + shlex.split).
Every execution is timed and traced to stdout + logs via RuntimeTracer.
"""

import shlex
import subprocess
import time
from agents.executors.base_executor import BaseExecutor
from app.config import Config
from utils.logger import logger
from utils.runtime_tracer import get_tracer


class ShellExecutor(BaseExecutor):

    def __init__(self) -> None:
        self._tracer = get_tracer()

    def execute(self, cmd: str) -> dict:
        try:
            args = shlex.split(cmd)
        except ValueError as exc:
            self._tracer.log_command(cmd, "shell", returncode=-1, stderr=str(exc))
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Sintaxis de comando inválida: {exc}",
                "returncode": -1,
            }

        if not args:
            self._tracer.log_command(cmd, "shell", returncode=-1, stderr="empty")
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     "Comando vacío",
                "returncode": -1,
            }

        self._tracer.log("shell", f"run: {cmd[:90]}", {"args_count": len(args)})
        t0 = time.monotonic()

        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT,
            )
            duration = time.monotonic() - t0

            self._tracer.log_command(
                cmd=cmd,
                executor="shell",
                returncode=result.returncode,
                stdout_len=len(result.stdout),
                stderr=result.stderr.strip()[:200],
                duration_s=duration,
            )

            return {
                "command":    cmd,
                "stdout":     result.stdout.strip(),
                "stderr":     result.stderr.strip(),
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - t0
            msg      = f"Timeout: el comando superó {Config.TIMEOUT}s"
            logger.warning(f"[ShellExecutor] {msg}: {cmd}")
            self._tracer.log_command(cmd, "shell", returncode=-1, stderr=msg,
                                     duration_s=duration)
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": -1}

        except FileNotFoundError:
            base = args[0]
            msg  = f"Comando no encontrado: '{base}'"
            self._tracer.log_command(cmd, "shell", returncode=127, stderr=msg)
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": 127}

        except PermissionError:
            msg = f"Permiso denegado para ejecutar: '{args[0]}'"
            self._tracer.log_command(cmd, "shell", returncode=126, stderr=msg)
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": 126}

        except Exception as exc:
            logger.error(f"[ShellExecutor] Error inesperado: {exc}")
            self._tracer.log_command(cmd, "shell", returncode=-1, stderr=str(exc))
            return {"command": cmd, "stdout": "", "stderr": str(exc), "returncode": -1}