"""
setup_env.py — Crea el entorno virtual e instala dependencias.
Se ejecuta automáticamente al pulsar F5 en VSCode (preLaunchTask).

Fix Windows: usa 'python -m pip' en lugar de pip.exe directamente,
lo que funciona tanto en Python de Microsoft Store como en instalaciones
estándar, y en Linux/Mac sin cambios.
"""

import subprocess
import sys
import os
from pathlib import Path

# Estructura real: SentinelAI/sentinel/setup_env.py
# ROOT = SentinelAI/
ROOT   = Path(__file__).parent.parent.resolve()
VENV   = ROOT / "venv"
IS_WIN = os.name == "nt"

# Ruta al intérprete Python del venv
PYTHON_VENV = VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
REQS        = Path(__file__).parent / "requirements.txt"


def run(cmd: list, desc: str = ""):
    """Ejecuta un comando y aborta si falla."""
    display = " ".join(str(c) for c in cmd)
    # Acortar rutas largas para el log
    display = display.replace(str(ROOT), "<root>")
    print(f"  $ {display}")
    result = subprocess.run([str(c) for c in cmd], capture_output=False)
    if result.returncode != 0:
        print(f"\n❌ Falló: {desc or display}")
        sys.exit(result.returncode)


def main():
    print("\n🔧 SentinelAI — Setup del entorno\n")
    print(f"  Raíz del proyecto : {ROOT}")
    print(f"  Entorno virtual   : {VENV}")
    print(f"  Python del sistema: {sys.executable}\n")

    # 1. Crear venv si no existe
    if not VENV.exists():
        print("📦 Creando entorno virtual...")
        run([sys.executable, "-m", "venv", str(VENV)], "crear venv")
        print("  ✅ Entorno creado\n")
    else:
        print("  ✅ Entorno ya existe\n")

    # Verificar que el intérprete del venv existe
    if not PYTHON_VENV.exists():
        print(f"❌ No se encontró el intérprete en: {PYTHON_VENV}")
        print("   Borra la carpeta venv/ y vuelve a intentarlo.")
        sys.exit(1)

    # 2. Actualizar pip usando 'python -m pip'
    #    (más fiable que llamar pip.exe en Windows Store Python)
    print("🔄 Actualizando pip...")
    run(
        [str(PYTHON_VENV), "-m", "pip", "install", "--upgrade", "pip", "-q"],
        "actualizar pip"
    )

    # 3. Instalar dependencias
    if REQS.exists():
        print(f"📥 Instalando dependencias ({REQS.name})...")
        run(
            [str(PYTHON_VENV), "-m", "pip", "install", "-r", str(REQS), "-q"],
            "instalar requirements"
        )
        print("  ✅ Dependencias instaladas\n")
    else:
        print(f"  ⚠️  No se encontró {REQS} — saltando instalación\n")

    print("🚀 Entorno listo. Arrancando servidor...\n")


if __name__ == "__main__":
    main()