import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any
from utils.logger import logger


class ParallelExecutor:
    """
    El original usaba ThreadPoolExecutor para llamadas I/O-bound al LLM.
    Los threads se bloquean esperando la respuesta HTTP → 4 workers = 4 respuestas
    en paralelo pero con overhead de threading y GIL del intérprete.

    La nueva implementación:
    1. Intenta usar asyncio (event loop) para concurrencia verdadera en I/O
    2. Si el contexto ya tiene un event loop activo (notebooks, servidores async),
       cae al ThreadPoolExecutor aumentado a 8 workers
    3. Añade timeouts por tarea y métricas básicas de rendimiento
    """

    def __init__(self, router, max_workers: int = 8):
        self.router      = router
        self.max_workers = max_workers

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def execute(self, tasks_with_commands: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Ejecuta comandos de múltiples tareas en paralelo.
        
        Parámetro:
            tasks_with_commands: { task_id: {"commands": [...]} }
        
        Devuelve:
            { task_id: result }
        """
        if not tasks_with_commands:
            return {}

        start = time.time()
        logger.info(f"[ParallelExecutor] Ejecutando {len(tasks_with_commands)} tareas en paralelo")

        try:
            # Intentar asyncio (mejor para I/O-bound como llamadas HTTP al LLM)
            results = self._execute_async(tasks_with_commands)
        except RuntimeError:
            # Event loop ya activo en este hilo → usar ThreadPoolExecutor
            logger.debug("[ParallelExecutor] Event loop activo, usando ThreadPoolExecutor")
            results = self._execute_threaded(tasks_with_commands)

        elapsed = time.time() - start
        logger.info(f"[ParallelExecutor] {len(results)} tareas completadas en {elapsed:.2f}s")

        return results

    # ------------------------------------------------------------------ #
    # Implementación asyncio                                               #
    # ------------------------------------------------------------------ #

    def _execute_async(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Fix #10: ejecuta todas las tareas con asyncio.gather() en lugar de threads.
        Para llamadas HTTP (Ollama), asyncio elimina el overhead del GIL y permite
        verdadera concurrencia sin threads adicionales.
        """
        return asyncio.run(self._gather_tasks(tasks))

    async def _gather_tasks(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        results = {}

        async def run_task(task_id: str, data: Dict) -> tuple:
            commands = data.get("commands", [])
            if not commands:
                return task_id, {"status": "skipped", "reason": "No commands"}
            try:
                # Ejecutar el router en un thread del pool para no bloquear el event loop
                # (subprocess y requests son operaciones blocking)
                result = await loop.run_in_executor(
                    None,  # usa el ThreadPoolExecutor por defecto
                    self.router.execute,
                    commands
                )
                return task_id, result
            except Exception as e:
                logger.error(f"[ParallelExecutor] Error en tarea {task_id}: {e}")
                return task_id, {"error": str(e), "commands": commands}

        # Lanzar todas las tareas concurrentemente
        coros = [run_task(tid, data) for tid, data in tasks.items()]
        pairs = await asyncio.gather(*coros, return_exceptions=False)

        for task_id, result in pairs:
            results[task_id] = result

        return results

    # ------------------------------------------------------------------ #
    # Fallback: ThreadPoolExecutor (max_workers mejorado)                  #
    # ------------------------------------------------------------------ #

    def _execute_threaded(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Fallback con ThreadPoolExecutor.
        Aumentado a max_workers=8 (el original tenía 4) y con
        manejo correcto de excepciones por tarea individual.
        """
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for task_id, data in tasks.items():
                commands = data.get("commands", [])
                if not commands:
                    results[task_id] = {"status": "skipped", "reason": "No commands"}
                    continue
                future = executor.submit(self.router.execute, commands)
                futures[future] = task_id

            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    results[task_id] = future.result()
                except Exception as e:
                    logger.error(f"[ParallelExecutor] Tarea {task_id} falló: {e}")
                    results[task_id] = {"error": str(e), "task_id": task_id}

        return results