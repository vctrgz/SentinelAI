import time
import random
import functools
from typing import Callable, Optional, Tuple, Type
from utils.logger import logger


# ------------------------------------------------------------------ #
# Clasificación de errores                                             #
# ------------------------------------------------------------------ #

# Errores de conexión → reintentar con backoff (el servidor puede estar arrancando)
CONNECTION_ERRORS = (
    "ConnectionError", "ConnectionRefusedError", "Timeout",
    "No se puede conectar", "ConnectTimeout", "ReadTimeout"
)

# Errores de rate limit → reintentar con espera más larga
RATE_LIMIT_ERRORS = ("429", "rate limit", "too many requests")

# Errores fatales → NO reintentar
FATAL_ERRORS = (
    "ImportError", "SyntaxError", "PermissionError",
    "comando no encontrado", "FileNotFoundError"
)


def classify_error(error: Exception) -> str:
    """
    Clasifica un error para decidir la estrategia de reintento.
    
    Devuelve:
    - "connection": error de red → backoff corto
    - "rate_limit": rate limiting → backoff largo
    - "fatal":      error no recuperable → no reintentar
    - "transient":  error temporal genérico → backoff estándar
    """
    msg = str(error).lower()

    if any(e.lower() in msg for e in FATAL_ERRORS):
        return "fatal"

    if any(e.lower() in msg for e in CONNECTION_ERRORS):
        return "connection"

    if any(e.lower() in msg for e in RATE_LIMIT_ERRORS):
        return "rate_limit"

    return "transient"


# ------------------------------------------------------------------ #
# RetryHandler                                                         #
# ------------------------------------------------------------------ #

class RetryHandler:
    """
    Fix #9: el sistema original no tenía ningún mecanismo de reintento.
    MAX_ITERATIONS estaba definido pero nunca se usaba.
    
    Implementa backoff exponencial con jitter:
        wait = min(base_wait * 2^attempt, max_wait) + random(0, jitter)
    
    Diferentes estrategias según el tipo de error:
    - connection:  esperas cortas (1s, 2s, 4s...)
    - rate_limit:  esperas largas (30s, 60s...)
    - transient:   esperas estándar (2s, 4s, 8s...)
    - fatal:       no se reintenta
    """

    # Configuración por tipo de error: (base_wait, max_wait, jitter)
    STRATEGIES = {
        "connection":  (1.0,  16.0, 0.5),
        "rate_limit":  (30.0, 120.0, 5.0),
        "transient":   (2.0,  30.0, 1.0),
        "fatal":       (0,    0,    0),    # no reintentar
    }

    def __init__(
        self,
        max_retries:  int   = 3,
        base_wait:    float = 2.0,
        max_wait:     float = 30.0,
        jitter:       float = 1.0,
    ):
        self.max_retries = max_retries
        self.base_wait   = base_wait
        self.max_wait    = max_wait
        self.jitter      = jitter

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        operation_name: str = "operación",
        **kwargs
    ) -> Tuple[bool, any]:
        """
        Ejecuta func(*args, **kwargs) con reintento automático.
        
        Devuelve (success: bool, result_or_last_exception).
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"[RetryHandler] '{operation_name}' exitoso en intento {attempt + 1}")
                return True, result

            except Exception as e:
                last_exception = e
                error_type     = classify_error(e)

                if error_type == "fatal":
                    logger.error(f"[RetryHandler] Error fatal en '{operation_name}': {e}. No se reintenta.")
                    return False, e

                if attempt < self.max_retries:
                    wait = self._calculate_wait(attempt, error_type)
                    logger.warning(
                        f"[RetryHandler] '{operation_name}' falló ({error_type}): {e}. "
                        f"Reintento {attempt + 1}/{self.max_retries} en {wait:.1f}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[RetryHandler] '{operation_name}' agotó {self.max_retries} reintentos. "
                        f"Último error: {e}"
                    )

        return False, last_exception

    def _calculate_wait(self, attempt: int, error_type: str) -> float:
        """Calcula el tiempo de espera con backoff exponencial + jitter."""
        base, max_w, jitter = self.STRATEGIES.get(
            error_type,
            (self.base_wait, self.max_wait, self.jitter)
        )
        exponential = min(base * (2 ** attempt), max_w)
        jitter_val  = random.uniform(0, jitter)
        return exponential + jitter_val

    # ------------------------------------------------------------------ #
    # Decorador de conveniencia                                            #
    # ------------------------------------------------------------------ #

    def retry(self, max_retries: Optional[int] = None, operation_name: str = ""):
        """
        Decorador para añadir reintentos a cualquier función.
        
        Uso:
            handler = RetryHandler(max_retries=3)
            
            @handler.retry(operation_name="llamada LLM")
            def call_llm(prompt):
                ...
        """
        retries = max_retries if max_retries is not None else self.max_retries

        def decorator(func: Callable) -> Callable:
            name = operation_name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                success, result = self.execute_with_retry(
                    func, *args,
                    operation_name=name,
                    **kwargs
                )
                if not success:
                    raise result  # relanzar la última excepción
                return result

            return wrapper
        return decorator


# Instancia global con configuración por defecto
DEFAULT_RETRY_HANDLER = RetryHandler(max_retries=3)