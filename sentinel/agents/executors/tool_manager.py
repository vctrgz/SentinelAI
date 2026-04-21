import platform
import shutil
import subprocess
from typing import Optional
from utils.logger import logger


# ------------------------------------------------------------------ #
# Detección de entorno                                                 #
# ------------------------------------------------------------------ #

def _detect_package_manager() -> Optional[str]:
    """
    Alerta #3: el original usaba 'sudo apt install' incondicionalmente.
    Esto rompe en Alpine (apk), Arch (pacman), macOS (brew), o contenedores
    sin sudo. CyberBench además requiere Kali Linux (apt).

    Detecta el gestor disponible en el sistema actual.
    """
    candidates = [
        ("apt-get", "apt-get"),      # Debian, Ubuntu, Kali Linux
        ("apt",     "apt"),          # Ubuntu moderno
        ("apk",     "apk"),          # Alpine (contenedores)
        ("dnf",     "dnf"),          # Fedora, RHEL 8+
        ("yum",     "yum"),          # CentOS, RHEL 7
        ("pacman",  "pacman"),       # Arch Linux
        ("brew",    "brew"),         # macOS
        ("zypper",  "zypper"),       # openSUSE
    ]
    for cmd, name in candidates:
        if shutil.which(cmd):
            return name
    return None


def _has_sudo() -> bool:
    """Verifica si sudo está disponible y el usuario puede usarlo."""
    if not shutil.which("sudo"):
        return False
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def _build_install_cmd(package_manager: str, tool_name: str) -> list:
    """
    Construye el comando de instalación correcto para cada gestor.
    Devuelve lista de args (shell=False).
    """
    use_sudo = _has_sudo() and package_manager in {"apt-get", "apt", "dnf", "yum", "zypper"}

    commands = {
        "apt-get": (["sudo"] if use_sudo else []) + ["apt-get", "install", "-y", tool_name],
        "apt":     (["sudo"] if use_sudo else []) + ["apt",     "install", "-y", tool_name],
        "apk":     ["apk", "add", "--no-cache", tool_name],
        "dnf":     (["sudo"] if use_sudo else []) + ["dnf",     "install", "-y", tool_name],
        "yum":     (["sudo"] if use_sudo else []) + ["yum",     "install", "-y", tool_name],
        "pacman":  (["sudo"] if use_sudo else []) + ["pacman",  "-S", "--noconfirm", tool_name],
        "brew":    ["brew", "install", tool_name],
        "zypper":  (["sudo"] if use_sudo else []) + ["zypper",  "install", "-y", tool_name],
    }
    return commands.get(package_manager, ["echo", f"Gestor '{package_manager}' no soportado"])


# ------------------------------------------------------------------ #
# ToolManager                                                          #
# ------------------------------------------------------------------ #

class ToolManager:
    """
    Alerta #3: el original solo sabía hacer 'sudo apt install <tool> -y'.
    
    Ahora detecta el gestor de paquetes del sistema, construye el comando
    correcto para ese gestor, y maneja la ausencia de sudo.
    """

    def __init__(self):
        self.package_manager = _detect_package_manager()
        self.os_info         = platform.system()

        if self.package_manager:
            logger.info(
                f"[ToolManager] OS: {self.os_info} | "
                f"Gestor: {self.package_manager} | "
                f"sudo: {_has_sudo()}"
            )
        else:
            logger.warning(
                "[ToolManager] No se detectó ningún gestor de paquetes. "
                "La instalación automática no estará disponible."
            )

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def is_installed(self, tool: str) -> bool:
        """Verifica si una herramienta está disponible en el PATH."""
        return shutil.which(tool) is not None

    def ensure_tool(self, tool: str) -> dict:
        """Instala la herramienta si no está disponible."""
        if self.is_installed(tool):
            logger.debug(f"[ToolManager] '{tool}' ya está instalado.")
            return {"tool": tool, "status": "already_installed"}
        return self.install_tool(tool)

    def install_tool(self, tool_name: str) -> dict:
        """Instala una herramienta usando el gestor detectado."""
        if not self.package_manager:
            return {
                "tool":      tool_name,
                "installed": False,
                "error":     (
                    f"No se encontró gestor de paquetes en {self.os_info}. "
                    "Instala la herramienta manualmente."
                )
            }

        cmd = _build_install_cmd(self.package_manager, tool_name)
        logger.info(f"[ToolManager] Instalando '{tool_name}' con: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                shell=False,        
                capture_output=True,
                text=True,
                timeout=120
            )
            success = result.returncode == 0

            if success:
                logger.info(f"[ToolManager] '{tool_name}' instalado correctamente.")
            else:
                logger.warning(
                    f"[ToolManager] Instalación de '{tool_name}' falló "
                    f"(código {result.returncode}): {result.stderr[:200]}"
                )

            return {
                "tool":      tool_name,
                "installed": success,
                "stdout":    result.stdout.strip(),
                "stderr":    result.stderr.strip(),
                "returncode": result.returncode,
                "command":   " ".join(cmd)
            }

        except subprocess.TimeoutExpired:
            return {
                "tool":      tool_name,
                "installed": False,
                "error":     "Timeout durante la instalación (>120s)"
            }
        except FileNotFoundError:
            return {
                "tool":      tool_name,
                "installed": False,
                "error":     f"Gestor '{self.package_manager}' no encontrado en PATH"
            }
        except Exception as e:
            logger.error(f"[ToolManager] Error inesperado: {e}")
            return {
                "tool":      tool_name,
                "installed": False,
                "error":     str(e)
            }

    def get_system_info(self) -> dict:
        """Información del sistema para diagnóstico."""
        return {
            "os":             self.os_info,
            "platform":       platform.platform(),
            "package_manager": self.package_manager or "none",
            "has_sudo":       _has_sudo(),
            "python":         platform.python_version()
        }