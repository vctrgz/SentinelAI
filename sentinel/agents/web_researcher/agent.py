from __future__ import annotations

import json
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
            if latest:
                return (
                    f"Ultimo CVE localizado en registros recientes de cve.org: `{latest}`\n"
                    f"Nota: {payload.get('note', '')}\n"
                    f"Ambiguedad: {payload.get('ambiguity', '')}\n"
                    "Fuentes:\n"
                    f"{_format_sources(payload.get('results', [])[:5])}"
                )
            return (
                "No se pudo localizar un ultimo CVE de forma fiable en cve.org con la estrategia actual.\n"
                f"Nota: {payload.get('note', '')}"
            )

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
