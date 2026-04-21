import shlex
from agents.executors.shell_executor import ShellExecutor
from sandbox.sandbox_executor import SandboxExecutor
from agents.executors.tool_manager import ToolManager
from app.config import Config
from utils.logger import logger


# ------------------------------------------------------------------ #
# Categorías de comandos y sus ejecutores asociados                    #
# ------------------------------------------------------------------ #

# Comandos de gestión de paquetes → ToolManager (que controla instalaciones)
PACKAGE_MANAGERS = {"apt", "apt-get", "pip", "pip3", "npm", "yarn", "cargo", "gem", "go"}

# Comandos de red → requieren atención especial
NETWORK_COMMANDS = {"curl", "wget", "nc", "netcat", "nmap", "ping", "ssh", "scp", "ftp"}

# Comandos de sistema críticos → siempre en sandbox si está disponible
SYSTEM_COMMANDS  = {"systemctl", "service", "mount", "umount", "fdisk", "mkfs", "iptables", "ufw"}

# Comandos seguros de lectura → pueden ir directos sin sandbox extra
SAFE_READ_COMMANDS = {"ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "pwd", "whoami", "date", "which", "file"}


class TaskRouter:
    """
    Fix #7: el router original solo comprobaba si el comando empezaba
    por 'apt' o 'pip'. Con eso CyberBench o SWE-bench jamás funcionarían.

    El nuevo router clasifica semánticamente cada comando en una categoría
    y elige el ejecutor más apropiado. También tiene en cuenta si el modo
    sandbox está activo (para benchmarks que requieren aislamiento).
    """

    def __init__(self):
        self.shell_executor   = ShellExecutor()
        self.sandbox_executor = SandboxExecutor()
        self.tool_manager     = ToolManager()

        # Elegir ejecutor por defecto según modo sandbox
        self._default_executor = (
            self.sandbox_executor if Config.SANDBOX_MODE
            else self.shell_executor
        )

        logger.info(
            f"[TaskRouter] Ejecutor por defecto: "
            f"{'SandboxExecutor' if Config.SANDBOX_MODE else 'ShellExecutor'}"
        )

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def route(self, commands: list) -> list:
        """
        Clasifica cada comando y asigna el ejecutor correcto.
        Devuelve lista de dicts con {executor, category, cmd}.
        """
        routed = []
        for cmd_obj in commands:
            cmd = cmd_obj.get("cmd", "") if isinstance(cmd_obj, dict) else str(cmd_obj)
            category, executor_name = self._classify(cmd)
            routed.append({
                "cmd":      cmd,
                "category": category,
                "executor": executor_name,
                "risk":     cmd_obj.get("risk", "medium") if isinstance(cmd_obj, dict) else "medium"
            })
            logger.debug(f"[TaskRouter] {category:12} → {executor_name:16} | {cmd[:60]}")
        return routed

    def execute(self, commands: list) -> list:
        """Clasifica y ejecuta todos los comandos, devolviendo resultados."""
        results = []
        routed  = self.route(commands)

        for item in routed:
            result = self._dispatch(item)
            results.append(result)

        return results

    # ------------------------------------------------------------------ #
    # Clasificación semántica                                              #
    # ------------------------------------------------------------------ #

    def _classify(self, cmd: str) -> tuple[str, str]:
        """
        Clasifica un comando en (categoría, nombre_ejecutor).

        Categorías:
        - package:   gestores de paquetes → tool_manager
        - network:   comandos de red → sandbox (si disponible)
        - system:    comandos de sistema → sandbox obligatorio
        - safe_read: solo lectura → shell directo
        - general:   resto → ejecutor por defecto
        """
        if not cmd or not cmd.strip():
            return "empty", "shell"

        try:
            parts    = shlex.split(cmd)
            base_cmd = parts[0] if parts else ""
        except ValueError:
            base_cmd = cmd.split()[0] if cmd.split() else ""

        # Quitar sudo para analizar el comando real
        if base_cmd == "sudo" and len(parts) > 1:
            base_cmd = parts[1]

        # 1. Gestores de paquetes
        if base_cmd in PACKAGE_MANAGERS:
            return "package", "tool_manager"

        # 2. Comandos de sistema críticos → sandbox obligatorio
        if base_cmd in SYSTEM_COMMANDS:
            return "system", "sandbox"

        # 3. Comandos de red → sandbox recomendado
        if base_cmd in NETWORK_COMMANDS:
            return "network", "sandbox"

        # 4. Comandos de solo lectura → shell directo (seguros)
        if base_cmd in SAFE_READ_COMMANDS:
            return "safe_read", "shell"

        # 5. Scripts Python/Node directos
        if base_cmd in {"python", "python3", "node", "ruby", "perl"}:
            return "script", "sandbox"

        # 6. Operaciones git
        if base_cmd == "git":
            return "vcs", "shell"

        # 7. Docker dentro de sandbox (evitar docker-in-docker si no es necesario)
        if base_cmd == "docker":
            return "container", "shell"

        # 8. Compiladores y builds
        if base_cmd in {"gcc", "g++", "make", "cmake", "cargo", "mvn", "gradle"}:
            return "build", "sandbox"

        # Default
        return "general", ("sandbox" if Config.SANDBOX_MODE else "shell")

    # ------------------------------------------------------------------ #
    # Despacho al ejecutor correcto                                        #
    # ------------------------------------------------------------------ #

    def _dispatch(self, item: dict) -> dict:
        executor_name = item["executor"]
        cmd           = item["cmd"]

        if executor_name == "tool_manager":
            # Extraer nombre de herramienta para install/ensure
            parts = cmd.split()
            tool  = parts[-1] if parts else cmd
            return self.tool_manager.ensure_tool(tool)

        elif executor_name == "sandbox":
            return self.sandbox_executor.execute(cmd)

        else:  # "shell" o cualquier otro
            return self.shell_executor.execute(cmd)