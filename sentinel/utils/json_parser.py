import json
import re


def safe_json_parse(text: str) -> dict:
    """
    Extrae y parsea JSON de la respuesta del LLM de forma robusta.

    Estrategias (en orden):
    1. Parse directo (respuesta limpia)
    2. Extracción de bloque ```json ... ``` (formato markdown común en Ollama)
    3. Búsqueda del primer { ... } en el texto
    """
    if not text or not isinstance(text, str):
        raise ValueError("El modelo devolvió una respuesta vacía o inválida")

    # 1. Parse directo
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Extraer bloque de código markdown ```json ... ```
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Búsqueda del primer objeto JSON en el texto
    try:
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    raise ValueError(
        f"No se pudo parsear JSON de la respuesta del modelo.\n"
        f"Respuesta recibida (primeros 300 chars): {text[:300]}"
    )