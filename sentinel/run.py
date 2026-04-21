from app.main import run

"""
Arranque rápido de SentinelAI.
 
Servidor web:  python run.py
CLI:           python run.py --cli
"""
 
import sys
 
if __name__ == "__main__":
    if "--cli" in sys.argv:
        from app.main import run
        run()
    else:
        import uvicorn
        uvicorn.run(
            "app.server:app",
            host="0.0.0.0",
            port=8000,
            reload=True
        )
 