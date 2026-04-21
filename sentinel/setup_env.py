"""
setup_env.py — Crea el entorno virtual e instala dependencias.

Se ejecuta automáticamente al pulsar F5 en VSCode (preLaunchTask).
Es cross-platform: detecta Windows o Linux/Mac y usa la ruta correcta.
"""

import subprocess
import sys
import os
from pathlib import Path

# Estructura: SentinelAI/sentinel/setup_env.py → SentinelAI/ es la raíz
ROOT  = Path(__file__).parent.parent          # SentinelAI/
VENV  = ROOT / "venv"
IS_WIN = os.name == "nt"

PIP    = VENV / ("Scripts/pip.exe"    if IS_WIN else "bin/pip")
PYTHON = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
REQS   = Path(__file__).parent / "requirements.txt"


def run(cmd: list, **kwargs):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    print("\n🔧 SentinelAI — Setup del entorno\n")

    # 1. Crear venv si no existe
    if not VENV.exists():
        print(f"📦 Creando entorno virtual en: {VENV}")
        run([sys.executable, "-m", "venv", str(VENV)])
        print("  ✅ Entorno creado\n")
    else:
        print(f"✅ Entorno ya existe: {VENV}\n")

    # 2. Actualizar pip silenciosamente
    run([str(PIP), "install", "--upgrade", "pip", "-q"])

    # 3. Instalar dependencias
    if REQS.exists():
        print(f"📥 Instalando dependencias desde {REQS.name}...")
        run([str(PIP), "install", "-r", str(REQS), "-q"])
        print("  ✅ Dependencias instaladas\n")
    else:
        print(f"  ⚠️  No se encontró {REQS} — saltando instalación\n")

    print("🚀 Entorno listo. Arrancando servidor...\n")


if __name__ == "__main__":
    main()