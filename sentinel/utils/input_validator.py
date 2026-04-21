import re
from dataclasses import dataclass, field
from typing import List, Optional
from utils.logger import logger


# ------------------------------------------------------------------ #
# Patrones de inyección de prompt                                      #
# ------------------------------------------------------------------ #

# Intentos de manipulación del system prompt
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions?",
    r"disregard\s+(your|the)\s+(previous|system|above)",
    r"forget\s+(everything|your\s+instructions?)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"act\s+as\s+(if\s+you\s+are|a|an)",
    r"new\s+system\s+prompt",
    r"jailbreak",
    r"DAN\s*(mode)?",
    r"developer\s+mode",
    r"override\s+(your|all)\s+(instructions?|rules?)",
    r"<\s*system\s*>",          # inyección de tags XML
    r"\[INST\]",                 # formato Llama instruction injection
    r"###\s*System",             # formato de alternancia de roles
]

# Input que sugiere comandos extremadamente destructivos inyectados
DANGEROUS_PAYLOAD_PATTERNS = [
    r"rm\s+-rf\s+/",
    r":()\{.*\|.*&\}",           # fork bomb
    r"dd\s+if=/dev/zero",
    r"mkfs\.",
    r">\s*/dev/sd[a-z]",
    r"chmod\s+-R\s+777\s+/",
]


# ------------------------------------------------------------------ #
# Resultado de validación                                              #
# ------------------------------------------------------------------ #

@dataclass
class ValidationResult:
    valid:       bool
    clean_input: str
    warnings:    List[str] = field(default_factory=list)
    blocked:     bool      = False
    block_reason: Optional[str] = None


# ------------------------------------------------------------------ #
# InputValidator                                                       #
# ------------------------------------------------------------------ #

class InputValidator:
    """
    Alerta #4: el input del usuario se pasaba directamente al LLM y
    a los comandos sin ninguna sanitización.

    Este validador aplica tres capas de control:
    1. Límites básicos (longitud, caracteres no imprimibles)
    2. Detección de prompt injection
    3. Detección de payloads de comandos peligrosos embebidos
    """

    MAX_INPUT_LENGTH = 4_000   # caracteres
    MIN_INPUT_LENGTH = 1

    def __init__(self):
        self._injection_re = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in PROMPT_INJECTION_PATTERNS
        ]
        self._dangerous_re = [
            re.compile(p, re.IGNORECASE)
            for p in DANGEROUS_PAYLOAD_PATTERNS
        ]

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def validate(self, user_input: str) -> ValidationResult:
        """
        Valida y sanitiza el input del usuario.
        Devuelve ValidationResult con el input limpio y posibles warnings.
        """
        if not isinstance(user_input, str):
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True, block_reason="El input debe ser texto"
            )

        # 1. Límites de longitud
        if len(user_input) < self.MIN_INPUT_LENGTH:
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True, block_reason="Input vacío"
            )

        if len(user_input) > self.MAX_INPUT_LENGTH:
            return ValidationResult(
                valid=False, clean_input=user_input[:self.MAX_INPUT_LENGTH],
                warnings=[
                    f"Input truncado a {self.MAX_INPUT_LENGTH} caracteres "
                    f"(recibido: {len(user_input)})"
                ]
            )

        # 2. Sanitización básica
        clean = self._sanitize(user_input)
        warnings = []

        # 3. Detección de prompt injection
        injection = self._detect_injection(clean)
        if injection:
            logger.warning(f"[InputValidator] Prompt injection detectado: {injection}")
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True,
                block_reason=f"Input bloqueado: posible prompt injection ({injection})"
            )

        # 4. Detección de payloads peligrosos
        dangerous = self._detect_dangerous(clean)
        if dangerous:
            logger.warning(f"[InputValidator] Payload peligroso detectado: {dangerous}")
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True,
                block_reason=f"Input bloqueado: payload de comando peligroso detectado"
            )

        # 5. Advertencias no bloqueantes
        if len(clean) > 1000:
            warnings.append(
                "Input largo — considera dividirlo en consultas más específicas "
                "para obtener mejores resultados"
            )

        return ValidationResult(valid=True, clean_input=clean, warnings=warnings)

    # ------------------------------------------------------------------ #
    # Helpers privados                                                     #
    # ------------------------------------------------------------------ #

    def _sanitize(self, text: str) -> str:
        """Elimina caracteres problemáticos preservando el contenido legítimo."""
        # Eliminar caracteres de control (excepto \n, \t que son legítimos)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # Normalizar espacios múltiples
        cleaned = re.sub(r'  +', ' ', cleaned)
        return cleaned.strip()

    def _detect_injection(self, text: str) -> Optional[str]:
        """Devuelve el patrón de injection encontrado, o None si no hay."""
        for pattern in self._injection_re:
            match = pattern.search(text)
            if match:
                return match.group(0)[:50]
        return None

    def _detect_dangerous(self, text: str) -> Optional[str]:
        """Devuelve el payload peligroso encontrado, o None si no hay."""
        for pattern in self._dangerous_re:
            match = pattern.search(text)
            if match:
                return match.group(0)[:50]
        return None