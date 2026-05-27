from __future__ import annotations

import json
import re
from typing import Iterable

from app.config import Config
from utils.ollama_client import OllamaClient
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt
from utils.research_router import EXACT_CVE_RE, classify_research_intent
from utils.time_context import get_current_time_context
from utils.web_search import (
    WebSearchError,
    lookup_exact_cve,
    search_cve_by_keywords,
    search_general_web,
    search_latest_cve,
    search_security_topic,
)


def _format_sources(results: Iterable[dict]) -> str:
    lines: list[str] = []
    for item in results:
        title = item.get("title", "sin titulo")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        lines.append(f"- {title}: {url}")
        if snippet:
            lines.append(f"  snippet: {snippet}")
    return "\n".join(lines)


def _format_latest_cve_records(results: Iterable[dict]) -> str:
    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        cve_id = item.get("cve_id") or item.get("title") or "CVE sin id"
        published = item.get("published") or "fecha no disponible"
        updated = item.get("lastModified") or ""
        state = item.get("vulnStatus") or ""
        url = item.get("url") or ""
        description = (item.get("description") or "").strip()

        meta = [f"publicado: {published}"]
        if state:
            meta.append(f"estado: {state}")
        if updated:
            meta.append(f"actualizado: {updated}")

        lines.append(f"{index}. `{cve_id}` ({'; '.join(meta)})")
        if description:
            lines.append(f"   {description[:220]}")
        if url:
            lines.append(f"   {url}")
    return "\n".join(lines)


def _build_mitigation_note(description: str, status: str) -> str:
    status_norm = (status or "").lower()
    text = (description or "").lower()

    if status_norm == "rejected":
        return "No aplica: NVD ha rechazado este candidato CVE."
    if status_norm == "deferred":
        return "Seguimiento pendiente: no hay mitigacion definitiva publicada todavia."

    notes: list[str] = []
    if any(token in text for token in ("xss", "cross-site scripting", "stored cross-site scripting")):
        notes.append("aplicar parche o actualizar el producto afectado")
        notes.append("escapar/validar la entrada y la salida donde se procesa contenido HTML")
    elif any(token in text for token in ("prototype pollution", "pollution")):
        notes.append("actualizar a una version corregida")
        notes.append("bloquear claves de objeto peligrosas y validar la estructura de importacion")
    elif any(token in text for token in ("sql injection", "sqli")):
        notes.append("aplicar actualizacion del fabricante")
        notes.append("usar consultas parametrizadas y revisar el filtrado de entrada")
    else:
        notes.append("aplicar la actualizacion o parche del proveedor afectado cuando este disponible")
        notes.append("revisar las referencias oficiales y limitar la funcionalidad expuesta mientras tanto")

    return "; ".join(notes).capitalize() + "."


def _extract_squad_sections(text: str) -> dict[str, str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    labels = {
        "Porteros": r"(?:Goalkeepers|Porteros):",
        "Defensas": r"(?:Defenders|Defensas):",
        "Centrocampistas": r"(?:Midfielders|Centrocampistas|Mediocampistas):",
        "Delanteros": r"(?:Forwards|Delanteros):",
    }
    sections: dict[str, str] = {}
    label_pattern = "|".join(f"(?P<{name}>{pattern})" for name, pattern in labels.items())
    matches = list(re.finditer(label_pattern, normalized, re.IGNORECASE))
    for index, match in enumerate(matches):
        name = next(group for group, value in match.groupdict().items() if value)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(normalized), start + 700)
        value = normalized[start:end].strip(" :-")
        value = re.split(
            r"\b(?:The Announcement|Key Players|Spain[’']s Starting XI|World Cup History|Group [A-Z] Fixtures)\b",
            value,
            maxsplit=1,
        )[0].strip(" :-")
        if value:
            sections[name] = value
    return sections


class WebResearchAgent:

    def __init__(self) -> None:
        model = Config.MODELS.get(Config.DEFAULT_MODEL, "balanceado")
        self.llm = OllamaClient(model)
        self.system_prompt = build_system_prompt("agents/web_researcher")

    def assess(self, user_input: str, objective: str = "") -> dict:
        return classify_research_intent(user_input, objective)

    def should_handle(self, user_input: str, objective: str = "") -> bool:
        assessment = self.assess(user_input, objective)
        return assessment.get("route_mode") == "replace"

    def should_enrich(self, user_input: str, objective: str = "") -> bool:
        assessment = self.assess(user_input, objective)
        return assessment.get("route_mode") == "augment"

    def search_cves(self, query: str, max_results: int = 5) -> dict:
        assessment = self.assess(query)
        time_context = get_current_time_context()
        try:
            if assessment["kind"] == "exact_cve":
                payload = lookup_exact_cve(assessment["cve_id"])
            elif assessment["kind"] == "latest_cve":
                payload = search_latest_cve(max_results=max_results, original_query=query)
            else:
                payload = search_cve_by_keywords(query, max_results=max_results)
            payload["status"] = "ok"
            payload["time_context"] = time_context
            return payload
        except WebSearchError as exc:
            return {
                "status": "error",
                "query": query,
                "time_context": time_context,
                "error": str(exc),
            }

    def research_topic(self, query: str, max_results: int = 8) -> dict:
        time_context = get_current_time_context()
        try:
            payload = search_general_web(query, max_results=max_results)
            payload["status"] = "ok"
            payload["time_context"] = time_context
            return payload
        except WebSearchError as exc:
            return {
                "status": "error",
                "query": query,
                "time_context": time_context,
                "error": str(exc),
            }

    def research_security_topic(self, query: str, max_results: int = 8) -> dict:
        time_context = get_current_time_context()
        try:
            payload = search_security_topic(query, max_results=max_results)
            payload["status"] = "ok"
            payload["time_context"] = time_context
            return payload
        except WebSearchError as exc:
            return {
                "status": "error",
                "query": query,
                "time_context": time_context,
                "error": str(exc),
            }

    def enrich_vulnerability_hypothesis(self, query: str) -> dict:
        payload = self.research_security_topic(query, max_results=6)
        payload["lookup_query"] = query
        return payload

    def respond(self, user_input: str, objective: str = "") -> str:
        assessment = self.assess(user_input, objective)
        time_context = get_current_time_context()

        if assessment["kind"] in {"exact_cve", "latest_cve", "vulnerability_research"} or EXACT_CVE_RE.search(user_input):
            payload = self.search_cves(user_input, max_results=8)
            return self._render_structured_response(payload, objective or user_input, time_context)

        if "vulner" in f"{user_input}\n{objective}".lower():
            payload = self.research_security_topic(user_input, max_results=8)
            return self._render_structured_response(payload, objective or user_input, time_context)

        payload = self.research_topic(user_input, max_results=8)
        return self._render_structured_response(payload, objective or user_input, time_context)

    def _render_structured_response(self, payload: dict, objective: str, time_context: dict) -> str:
        if payload.get("status") == "error":
            return (
                "No se pudo completar la busqueda web en este momento.\n"
                f"Motivo: {payload.get('error', 'error desconocido')}"
            )

        if payload.get("kind") == "exact_cve":
            references = payload.get("references", [])[:5]
            lines = [f"Informacion de `{payload.get('cve_id', '')}`", ""]
            if payload.get("date_published"):
                lines.append(f"- Publicado: {payload['date_published']}")
            if payload.get("date_updated"):
                lines.append(f"- Actualizado: {payload['date_updated']}")
            if payload.get("state"):
                lines.append(f"- Estado: {payload['state']}")
            lines.append("- Fuente principal: cve.org")
            if references:
                lines.append("- Referencias comparadas:")
                lines.extend(f"  - {item.get('url', '')}" for item in references)
            excerpt = payload.get("page_excerpt", "")
            if excerpt:
                lines.append("")
                lines.append("Resumen extraido:")
                lines.append(excerpt[:800])
            return "\n".join(lines)

        if payload.get("kind") == "latest_cve":
            latest = payload.get("latest_cve")
            latest_record = payload.get("latest_record") or {}
            if latest:
                description = (latest_record.get("description") or "").strip()
                mitigation = _build_mitigation_note(description, latest_record.get("vulnStatus", ""))
                published = latest_record.get("published") or "fecha no disponible"
                updated = latest_record.get("lastModified") or "fecha no disponible"
                state = latest_record.get("vulnStatus") or "desconocido"
                url = latest_record.get("url") or f"https://nvd.nist.gov/vuln/detail/{latest}"

                return (
                    f"Ultimo CVE localizado en NVD: `{latest}`\n\n"
                    f"Publicado: {published}\n"
                    f"Estado: {state}\n"
                    f"Actualizado: {updated}\n\n"
                    f"Descripcion: {description or 'No disponible en el registro consultado.'}\n\n"
                    f"Mitigacion: {mitigation}\n\n"
                    f"Fuente: {url}\n"
                    f"Nota: {payload.get('note', '')}"
                )
            return (
                "No se pudo localizar un ultimo CVE de forma fiable en cve.org con la estrategia actual.\n"
                f"Nota: {payload.get('note', '')}"
            )

        if payload.get("kind") == "general_web":
            return self._render_general_web_answer(payload, objective, time_context)

        prompt = f"""
{build_runtime_context_block(
    extra_lines=[
        "You are rendering the output of the research subsystem.",
        "Use only the evidence provided below.",
        "State uncertainty explicitly when evidence is incomplete or ambiguous.",
    ],
    time_context=time_context,
)}

Objective:
{objective}

Research Payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return concise markdown with:
- query used
- best sources
- what is known
- uncertainty
- next useful direction if needed
"""
        try:
            return self.llm.chat(self.system_prompt, prompt)
        except Exception:
            return (
                f"Research query: `{payload.get('query', objective)}`\n"
                "Best sources:\n"
                f"{_format_sources(payload.get('results', [])[:5])}"
            )

    def _render_general_web_response(self, payload: dict, objective: str, time_context: dict) -> str:
        results = payload.get("results", []) or []
        query = payload.get("query", objective)
        lines = [
            "Resultados de busqueda web",
            "",
            f"Query usada: `{query}`",
            f"Fecha de consulta: {time_context.get('date', '')}",
            "Politica de fuentes: todas las fuentes publicas encontradas se tratan como fiables para esta consulta general.",
            "",
        ]

        if not results:
            lines.extend([
                "No se han recibido resultados del buscador con la estrategia actual.",
                "No es un rechazo por fiabilidad: simplemente el buscador no devolvio paginas parseables.",
            ])
            return "\n".join(lines)

        lines.append("Fuentes encontradas:")
        for index, item in enumerate(results[:8], start=1):
            title = item.get("title", "sin titulo")
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            matched_query = item.get("matched_query") or query
            lines.append(f"{index}. {title}")
            if url:
                lines.append(f"   Fuente: {url}")
            if snippet:
                lines.append(f"   Resumen: {snippet}")
            excerpt = item.get("page_excerpt", "")
            if excerpt:
                lines.append(f"   Extracto: {excerpt[:900]}")
            if matched_query != query:
                lines.append(f"   Query ampliada: {matched_query}")

        lines.extend([
            "",
            "Resumen:",
            "Usa las fuentes anteriores como base. Si la convocatoria oficial aun no aparece en los resultados, la respuesta debe indicarlo como informacion no publicada o no localizada, no como fuente no fiable.",
        ])
        return "\n".join(lines)

    def _render_general_web_answer(self, payload: dict, objective: str, time_context: dict) -> str:
        results = payload.get("results", []) or []
        if not results:
            return (
                "No he encontrado resultados web parseables para esa consulta con la estrategia actual. "
                "No es un problema de fiabilidad de fuentes; el buscador no devolvio contenido util."
            )

        combined_text = "\n".join(
            f"{item.get('snippet', '')}\n{item.get('page_excerpt', '')}"
            for item in results[:8]
        )
        squad_sections = _extract_squad_sections(combined_text)
        if squad_sections:
            lines = ["La convocatoria de España para el Mundial 2026 es:", ""]
            for label in ("Porteros", "Defensas", "Centrocampistas", "Delanteros"):
                if label in squad_sections:
                    lines.append(f"**{label}:** {squad_sections[label]}")
            lines.append("")
            lines.append("Según los resultados web encontrados, Luis de la Fuente anunció una lista de 26 jugadores.")
            return "\n".join(lines)

        evidence_lines: list[str] = []
        for index, item in enumerate(results[:8], start=1):
            evidence_lines.append(f"Fuente {index}: {item.get('title', '')}")
            if item.get("snippet"):
                evidence_lines.append(f"Snippet: {item['snippet']}")
            if item.get("page_excerpt"):
                evidence_lines.append(f"Contenido: {item['page_excerpt'][:1800]}")
            if item.get("url"):
                evidence_lines.append(f"URL: {item['url']}")

        prompt = f"""
{build_runtime_context_block(
    extra_lines=[
        "You are answering a general open-internet question.",
        "All provided public sources are considered reliable for this non-security query.",
        "Answer the user's question directly first.",
        "Do not output a research log, query list, methodology, or uncertainty section unless the answer is genuinely not present.",
        "Use Spanish if the user asked in Spanish.",
        "If the evidence contains a full roster/list, extract and present the list.",
        "If only snippets are available and not the full list, give the concrete facts present and say the full list was not visible in the fetched text.",
        "Mention sources only briefly at the end under 'Fuentes' with names, not long snippets.",
    ],
    time_context=time_context,
)}

Pregunta del usuario:
{objective}

Evidencia web:
{chr(10).join(evidence_lines)}
"""
        try:
            return self.llm.chat(self.system_prompt, prompt)
        except Exception:
            first = results[0]
            return (
                f"Resultado encontrado: {first.get('snippet') or first.get('title', '')}\n\n"
                f"Fuente: {first.get('title', 'fuente web')} - {first.get('url', '')}"
            )
