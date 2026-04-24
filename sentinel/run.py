"""
Arranque rapido de SentinelAI.

Servidor web:  python run.py
CLI:           python run.py --cli
"""

import os
import sys

from app.main import run


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run()
    else:
        import uvicorn

        debug_mode = sys.gettrace() is not None
        reload_enabled = os.getenv("UVICORN_RELOAD", "true").lower() == "true"

        uvicorn.run(
            "app.server:app",
            host="0.0.0.0",
            port=8000,
            reload=(reload_enabled and not debug_mode),
        )
