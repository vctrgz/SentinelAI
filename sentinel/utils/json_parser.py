import json


def safe_json_parse(text: str):
    """
    Intenta extraer JSON incluso si el modelo añade texto extra.
    """

    try:
        return json.loads(text)
    except:
        pass

    # intentar encontrar bloque JSON
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        raise ValueError("No se pudo parsear JSON del modelo")