import json
from core.orchestrator import Orchestrator
from utils.logger import setup_logger

logger = setup_logger()


def run():
    print("🧠 SentinelAI iniciado. Escribe 'exit' para salir.\n")

    orchestrator = Orchestrator()

    while True:
        try:
            user_input = input(">> ")

            if user_input.lower() in ["exit", "quit"]:
                print("👋 Cerrando SentinelAI...")
                break

            # Procesar input
            result = orchestrator.handle_user_input(user_input)

            print("\n📤 Resultado:\n")
            print(result)
            print("\n" + "=" * 50 + "\n")

        except KeyboardInterrupt:
            print("\n👋 Interrumpido por el usuario.")
            break

        except Exception as e:
            logger.error(f"Error en main loop: {str(e)}")
            print("❌ Ha ocurrido un error inesperado.")


if __name__ == "__main__":
    run()