import shlex
import subprocess
from agents.executors.base_executor import BaseExecutor
from app.config import Config
from utils.logger import logger


class ShellExecutor(BaseExecutor):
    """
    Ejecutor de comandos de shell.

    Fix #2: el original usaba shell=True → permite command injection.
    Ahora usa shell=False + shlex.split() para parsear el comando de
    forma segura, sin invocar /bin/sh como intermediario.
    """

    def execute(self, cmd: str) -> dict:
        # Parsear el comando con shlex antes de ejecutar
        try:
            args = shlex.split(cmd)
        except ValueError as e:
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Sintaxis de comando inválida: {e}",
                "returncode": -1
            }

        if not args:
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     "Comando vacío",
                "returncode": -1
            }

        logger.debug(f"[ShellExecutor] Ejecutando: {args}")

        try:
            result = subprocess.run(
                args,
                shell=False,         
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT  # evitar comandos bloqueantes
            )

            return {
                "command":    cmd,
                "stdout":     result.stdout.strip(),
                "stderr":     result.stderr.strip(),
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"[ShellExecutor] Timeout ({Config.TIMEOUT}s): {cmd}")
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Timeout: el comando superó {Config.TIMEOUT}s",
                "returncode": -1
            }

        except FileNotFoundError:
            # El comando base no existe en el sistema
            base_cmd = args[0]
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Comando no encontrado: '{base_cmd}'",
                "returncode": 127   # código estándar POSIX para command not found
            }

        except PermissionError:
            # Error de permisos al intentar ejecutar el comando
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Permiso denegado para ejecutar: '{args[0]}'",
                "returncode": 126
            }

        except Exception as e:
            #Inesperado: loguear el error completo para debugging.
            logger.error(f"[ShellExecutor] Error inesperado: {e}")
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     str(e),
                "returncode": -1
            }