from __future__ import annotations

import re


_SPANISH_HINTS = (
    r"\b(el|la|los|las|un|una|de|del|que|por|para|con|sin|como|cual|cuál|ultimo|último|informacion|información|vulnerabilidad|publicado)\b",
)
_ENGLISH_HINTS = (
    r"\b(the|a|an|of|for|with|without|what|which|latest|current|published|vulnerability|information)\b",
)
_PORTUGUESE_HINTS = (
    r"\b(o|a|os|as|de|do|da|que|com|sem|qual|ultimo|último|informacao|informação|vulnerabilidade|publicado)\b",
)
_FRENCH_HINTS = (
    r"\b(le|la|les|de|du|des|que|avec|sans|quel|quelle|dernier|information|vulnérabilité|publie|publié)\b",
)


def detect_language(text: str) -> str:
    normalized = (text or "").lower()
    if any(re.search(pattern, normalized) for pattern in _SPANISH_HINTS):
        return "es"
    if any(re.search(pattern, normalized) for pattern in _PORTUGUESE_HINTS):
        return "pt"
    if any(re.search(pattern, normalized) for pattern in _FRENCH_HINTS):
        return "fr"
    if any(re.search(pattern, normalized) for pattern in _ENGLISH_HINTS):
        return "en"
    return "en"
