"""
setup_env.py - Crea el entorno virtual e instala dependencias.
Se ejecuta automaticamente al pulsar F5 en VSCode (preLaunchTask).

Tambien detecta venvs rotos o creados en otro sistema operativo y los
reconstruye automaticamente.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent.resolve()
VENV = ROOT / "venv"
IS_WIN = os.name == "nt"

PYTHON_VENV = VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
REQS = Path(__file__).parent / "requirements.txt"


def run(cmd: list, desc: str = ""):
    """Ejecuta un comando y aborta si falla."""
    display = " ".join(str(c) for c in cmd).replace(str(ROOT), "<root>")
    print(f"  $ {display}")
    result = subprocess.run([str(c) for c in cmd], capture_output=False)
    if result.returncode != 0:
        print(f"\nFallo: {desc or display}")
        sys.exit(result.returncode)


def recreate_venv(reason: str):
    print(f"  Entorno virtual invalido: {reason}")
    if VENV.exists():
        print(f"  Eliminando {VENV} ...")
        shutil.rmtree(VENV)
    print("  Recreando entorno virtual...")
    run([sys.executable, "-m", "venv", str(VENV)], "recrear venv")
    print("  Entorno recreado\n")


def main():
    print("\nSentinelAI - Setup del entorno\n")
    print(f"  Raiz del proyecto : {ROOT}")
    print(f"  Entorno virtual   : {VENV}")
    print(f"  Python del sistema: {sys.executable}\n")

    if not VENV.exists():
        print("Creando entorno virtual...")
        run([sys.executable, "-m", "venv", str(VENV)], "crear venv")
        print("  Entorno creado\n")
    else:
        print("  Entorno ya existe\n")

    if not PYTHON_VENV.exists():
        recreate_venv(f"no se encontro el interprete en {PYTHON_VENV}")

    if not PYTHON_VENV.exists():
        print(f"No se encontro el interprete en: {PYTHON_VENV}")
        sys.exit(1)

    print("Actualizando pip...")
    run(
        [str(PYTHON_VENV), "-m", "pip", "install", "--upgrade", "pip", "-q"],
        "actualizar pip",
    )

    if REQS.exists():
        print(f"Instalando dependencias ({REQS.name})...")
        run(
            [str(PYTHON_VENV), "-m", "pip", "install", "-r", str(REQS), "-q"],
            "instalar requirements",
        )
        print("  Dependencias instaladas\n")
    else:
        print(f"  No se encontro {REQS} - saltando instalacion\n")

    print("Entorno listo. Arrancando servidor...\n")


if __name__ == "__main__":
    main()
