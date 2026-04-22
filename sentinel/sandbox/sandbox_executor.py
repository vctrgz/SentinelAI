import shlex
import shutil
import subprocess
from typing import Optional
from agents.executors.base_executor import BaseExecutor
from app.config import Config
from utils.logger import logger


class SandboxExecutor(BaseExecutor):
    """    
    Este ejecutor añade aislamiento en dos niveles:

    Nivel 1 — Docker (preferido, requerido por SWE-bench y Terminal-Bench):
      Ejecuta cada comando en un contenedor efímero con:
      - Sin acceso a red (--network=none)
      - Memoria limitada (--memory)
      - CPU limitada (--cpus)
      - Sistema de archivos de solo lectura excepto /tmp y /workspace
      - Usuario no-root
      
    Nivel 2 — Fallback restringido (cuando Docker no está disponible):
      Subprocess con timeout + PATH reducido.
      NO es aislamiento real; solo un nivel mínimo de contención.
    """

    # Imagen Docker base para comandos generales
    DEFAULT_IMAGE = "python:3.11-slim"

    def __init__(self, image: Optional[str] = None, workspace: Optional[str] = None):
        self.image       = image or self.DEFAULT_IMAGE
        self.workspace   = workspace or Config.SANDBOX_PATH
        self._docker_ok  = self._check_docker()

        if self._docker_ok:
            logger.info(f"[SandboxExecutor] Modo Docker activo (imagen: {self.image})")
        else:
            logger.warning(
                "[SandboxExecutor] Docker no disponible — usando fallback restringido. "
                "Para aislamiento real instala Docker y asegúrate de que el daemon esté corriendo."
            )

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def execute(self, cmd: str) -> dict:
        if Config.SANDBOX_MODE and self._docker_ok:
            return self._execute_docker(cmd)
        return self._execute_restricted(cmd)

    # ------------------------------------------------------------------ #
    # Nivel 1: Ejecución en contenedor Docker                              #
    # ------------------------------------------------------------------ #

    def _execute_docker(self, cmd: str) -> dict:
        """
        Ejecuta el comando en un contenedor Docker efímero.
        Compatible con el harness de evaluación de Terminal-Bench 2.0
        y SWE-bench (que requieren entornos Docker aislados por tarea).
        """
        docker_cmd = [
            "docker", "run",
            "--rm",                         # eliminar contenedor al terminar
            "--network=none",               # sin acceso a red
            "--memory=512m",                # límite de RAM
            "--memory-swap=512m",           # sin swap extra
            "--cpus=1.0",                   # límite de CPU
            "--read-only",                  # sistema de archivos de solo lectura
            "--tmpfs=/tmp:size=100m",        # /tmp escribible en RAM
            f"--volume={self.workspace}:/workspace:rw",   # directorio de trabajo
            "--workdir=/workspace",
            "--user=nobody",                # no ejecutar como root
            self.image,
            "bash", "-c", cmd
        ]

        logger.debug(f"[SandboxExecutor][Docker] {cmd}")

        try:
            result = subprocess.run(
                docker_cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT
            )
            return {
                "command":    cmd,
                "stdout":     result.stdout.strip(),
                "stderr":     result.stderr.strip(),
                "returncode": result.returncode,
                "sandbox":    "docker"
            }

        except subprocess.TimeoutExpired:
            # Matar el contenedor si sigue corriendo
            subprocess.run(["docker", "kill", "--signal=SIGKILL"], capture_output=True)
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Docker timeout tras {Config.TIMEOUT}s",
                "returncode": -1,
                "sandbox":    "docker"
            }

        except Exception as e:
            logger.error(f"[SandboxExecutor][Docker] Error: {e}")
            # Si Docker falla inesperadamente, caer al fallback
            return self._execute_restricted(cmd)

    # ------------------------------------------------------------------ #
    # Nivel 2: Fallback con restricciones mínimas                          #
    # ------------------------------------------------------------------ #

    def _execute_restricted(self, cmd: str) -> dict:
        """
        Fallback cuando Docker no está disponible.
        Aplica restricciones mínimas vía subprocess:
        - Timeout obligatorio
        - PATH reducido a herramientas seguras conocidas
        - shell=False
        """
        safe_paths = "/usr/bin:/bin:/usr/local/bin"

        try:
            args = shlex.split(cmd)
        except ValueError as e:
            return {"command": cmd, "stdout": "", "stderr": str(e), "returncode": -1, "sandbox": "restricted"}

        logger.debug(f"[SandboxExecutor][Restricted] {args}")

        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT,
                env={"PATH": safe_paths}   # PATH reducido
            )
            return {
                "command":    cmd,
                "stdout":     result.stdout.strip(),
                "stderr":     result.stderr.strip(),
                "returncode": result.returncode,
                "sandbox":    "restricted"
            }

        except subprocess.TimeoutExpired:
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Timeout tras {Config.TIMEOUT}s",
                "returncode": -1,
                "sandbox":    "restricted"
            }
        except FileNotFoundError:
            return {
                "command":    cmd,
                "stdout":     "",
                "stderr":     f"Comando no encontrado: '{args[0] if args else cmd}'",
                "returncode": 127,
                "sandbox":    "restricted"
            }
        except Exception as e:
            return {
                "command": cmd, "stdout": "", "stderr": str(e),
                "returncode": -1, "sandbox": "restricted"
            }

    # ------------------------------------------------------------------ #
    # Utilidades                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_docker() -> bool:
        """Verifica si Docker está disponible y el daemon responde."""
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False