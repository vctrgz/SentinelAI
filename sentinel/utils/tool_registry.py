import os
import subprocess
import shlex
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from utils.logger import logger


# ------------------------------------------------------------------ #
# Definición de herramientas                                           #
# ------------------------------------------------------------------ #

@dataclass
class ToolParameter:
    name:        str
    type:        str   # "string" | "integer" | "boolean" | "array"
    description: str
    required:    bool = True
    default:     Any  = None


@dataclass
class Tool:
    name:        str
    description: str
    parameters:  List[ToolParameter]
    handler:     Callable
    category:    str = "general"  # "filesystem" | "shell" | "search" | "edit"

    def to_schema(self) -> dict:
        """Serializa la herramienta al formato de schema estándar."""
        return {
            "name":        self.name,
            "description": self.description,
            "category":    self.category,
            "parameters": {
                "type": "object",
                "properties": {
                    p.name: {
                        "type":        p.type,
                        "description": p.description,
                        **({"default": p.default} if p.default is not None else {})
                    }
                    for p in self.parameters
                },
                "required": [p.name for p in self.parameters if p.required]
            }
        }


# ------------------------------------------------------------------ #
# Registry                                                             #
# ------------------------------------------------------------------ #

class ToolRegistry:
    """
    ToolRegistry mantiene un catálogo de herramientas tipadas que el
    agente puede invocar por nombre con parámetros validados.
    Compatible con el formato de tool-calling de SWE-bench (str_replace,
    view, bash) y con el estándar de IBM/Google para agentes.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.debug(f"[ToolRegistry] Registrada: {tool.name}")

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def list_schemas(self) -> List[dict]:
        return [t.to_schema() for t in self._tools.values()]

    def schemas_as_prompt(self) -> str:
        """Serializa todos los schemas en texto para incluir en el system prompt."""
        lines = ["## Available Tools\n"]
        for tool in self._tools.values():
            schema = tool.to_schema()
            lines.append(f"### {tool.name}")
            lines.append(f"**Descripción**: {tool.description}")
            lines.append(f"**Categoría**: {tool.category}")
            lines.append("**Parámetros**:")
            for p in tool.parameters:
                req = "requerido" if p.required else f"opcional (default: {p.default})"
                lines.append(f"  - `{p.name}` ({p.type}, {req}): {p.description}")
            lines.append("")
        return "\n".join(lines)

    def execute(self, name: str, params: dict) -> dict:
        """Ejecuta una herramienta por nombre con los parámetros dados."""
        tool = self.get(name)
        if not tool:
            return {
                "tool":    name,
                "success": False,
                "error":   f"Herramienta '{name}' no registrada. Disponibles: {self.list_tools()}"
            }

        # Validar parámetros requeridos
        missing = [
            p.name for p in tool.parameters
            if p.required and p.name not in params
        ]
        if missing:
            return {
                "tool":    name,
                "success": False,
                "error":   f"Parámetros requeridos faltantes: {missing}"
            }

        try:
            result = tool.handler(**params)
            return {"tool": name, "success": True, "result": result}
        except Exception as e:
            logger.error(f"[ToolRegistry] Error en {name}: {e}")
            return {"tool": name, "success": False, "error": str(e)}


# ------------------------------------------------------------------ #
# Herramientas predefinidas                                            #
# ------------------------------------------------------------------ #

def _bash_handler(command: str, timeout: int = 30) -> dict:
    """Ejecuta un comando bash de forma segura."""
    try:
        args   = shlex.split(command)
        result = subprocess.run(
            args, shell=False, capture_output=True,
            text=True, timeout=timeout
        )
        return {
            "stdout":     result.stdout.strip(),
            "stderr":     result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout ({timeout}s)", "returncode": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"Comando no encontrado: {command.split()[0]}", "returncode": 127}


def _read_file_handler(path: str) -> str:
    """Lee el contenido de un archivo."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write_file_handler(path: str, content: str) -> str:
    """Escribe contenido en un archivo, creando directorios si es necesario."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Archivo escrito: {path} ({len(content)} chars)"


def _str_replace_handler(path: str, old_str: str, new_str: str) -> str:
    """
    Reemplaza old_str por new_str en un archivo.
    Compatible con el formato str_replace_editor de SWE-bench.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old_str not in content:
        raise ValueError(f"El texto a reemplazar no se encontró en {path}")
    new_content = content.replace(old_str, new_str, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return f"Reemplazo aplicado en {path}"


def _search_code_handler(pattern: str, path: str = ".", case_sensitive: bool = True) -> str:
    """Busca un patrón en archivos de código (wrapper de grep)."""
    flag = "" if case_sensitive else "-i"
    cmd  = f"grep -rn {flag} {shlex.quote(pattern)} {shlex.quote(path)}"
    try:
        args   = shlex.split(cmd)
        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() or "(Sin resultados)"
    except Exception as e:
        return f"Error en búsqueda: {e}"


def _list_directory_handler(path: str = ".", show_hidden: bool = False) -> str:
    """Lista el contenido de un directorio."""
    try:
        entries = os.listdir(path)
        if not show_hidden:
            entries = [e for e in entries if not e.startswith(".")]
        entries.sort()
        result = []
        for entry in entries:
            full = os.path.join(path, entry)
            prefix = "[D]" if os.path.isdir(full) else "[F]"
            result.append(f"{prefix} {entry}")
        return "\n".join(result) if result else "(Directorio vacío)"
    except PermissionError:
        raise PermissionError(f"Sin permisos para leer: {path}")


# ------------------------------------------------------------------ #
# Fábrica: crea el registry con todas las herramientas registradas     #
# ------------------------------------------------------------------ #

def build_default_registry() -> ToolRegistry:
    """
    Construye el registry con el conjunto base de herramientas.
    Este es el mínimo necesario para SWE-bench y Terminal-Bench.
    """
    registry = ToolRegistry()

    registry.register(Tool(
        name="bash",
        description="Ejecuta un comando bash en el entorno del agente",
        category="shell",
        parameters=[
            ToolParameter("command", "string", "Comando bash a ejecutar"),
            ToolParameter("timeout", "integer", "Timeout en segundos", required=False, default=30),
        ],
        handler=_bash_handler
    ))

    registry.register(Tool(
        name="read_file",
        description="Lee el contenido completo de un archivo",
        category="filesystem",
        parameters=[
            ToolParameter("path", "string", "Ruta al archivo a leer"),
        ],
        handler=_read_file_handler
    ))

    registry.register(Tool(
        name="write_file",
        description="Escribe o sobreescribe un archivo con el contenido dado",
        category="filesystem",
        parameters=[
            ToolParameter("path",    "string", "Ruta del archivo a escribir"),
            ToolParameter("content", "string", "Contenido a escribir"),
        ],
        handler=_write_file_handler
    ))

    registry.register(Tool(
        name="str_replace",
        description="Reemplaza una cadena exacta en un archivo (compatible con SWE-bench)",
        category="edit",
        parameters=[
            ToolParameter("path",    "string", "Ruta del archivo"),
            ToolParameter("old_str", "string", "Texto exacto a reemplazar"),
            ToolParameter("new_str", "string", "Nuevo texto"),
        ],
        handler=_str_replace_handler
    ))

    registry.register(Tool(
        name="search_code",
        description="Busca un patrón de texto en archivos de código (grep recursivo)",
        category="search",
        parameters=[
            ToolParameter("pattern",        "string",  "Patrón a buscar"),
            ToolParameter("path",           "string",  "Directorio de búsqueda", required=False, default="."),
            ToolParameter("case_sensitive", "boolean", "Búsqueda sensible a mayúsculas", required=False, default=True),
        ],
        handler=_search_code_handler
    ))

    registry.register(Tool(
        name="list_directory",
        description="Lista el contenido de un directorio",
        category="filesystem",
        parameters=[
            ToolParameter("path",        "string",  "Ruta del directorio", required=False, default="."),
            ToolParameter("show_hidden", "boolean", "Mostrar archivos ocultos", required=False, default=False),
        ],
        handler=_list_directory_handler
    ))

    return registry


# Instancia global lista para usar
DEFAULT_REGISTRY = build_default_registry()