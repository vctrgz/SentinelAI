"""
agents/synthesizer/agent.py

Aggregates multi-phase execution results into structured, human-readable reports.

Fixes vs v1:
  - Removed dead `if isinstance(result, list)` inside `if isinstance(result, dict)` block
    (Pyright narrows the type to Never in that branch → "Never is not iterable")
  - All iteration now goes through _extract_stdout() helper which is shape-safe
  - List comprehension scope fixed (was referencing outer loop variable)
  - Added runtime_tracer calls for live execution visibility
"""

import json
from typing import Any, List

from app.config import Config
from utils.ollama_client import OllamaClient
from utils.prompt_loader import build_system_prompt
from utils.network_parser import NetworkReport
from utils.logger import logger
from utils.runtime_tracer import get_tracer


# ─────────────────────────────────────────────────────────────────────────────
# Shape-safe helpers — the fix for all three "Never is not iterable" errors
# ─────────────────────────────────────────────────────────────────────────────

def _extract_stdout(item: Any) -> str:
    """
    Safely extract stdout from any result shape without type-narrowing issues.
    dict  → item["stdout"]
    list  → concat stdout from each dict element inside the list
    other → ""
    """
    if isinstance(item, dict):
        return item.get("stdout", "") or ""
    if isinstance(item, list):
        parts: List[str] = []
        for element in item:
            if isinstance(element, dict):
                parts.append(element.get("stdout", "") or "")
        return "\n".join(parts)
    return ""


def _extract_stderr(item: Any) -> str:
    """Same pattern as _extract_stdout but for stderr."""
    if isinstance(item, dict):
        return item.get("stderr", "") or ""
    if isinstance(item, list):
        parts: List[str] = []
        for element in item:
            if isinstance(element, dict):
                parts.append(element.get("stderr", "") or "")
        return "\n".join(parts)
    return ""


def _returncode(item: Any) -> int:
    """Return numeric returncode from a result item; defaults to 0."""
    if isinstance(item, dict):
        return int(item.get("returncode", 0) or 0)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class SynthesizerAgent:

    _NETWORK_SIGNATURES = (
        "Nmap scan report", "Host is up", "[ether]",
        "MAC Address:", "PORT   STATE", "open ports",
        "Nmap done", "Starting Nmap",
    )

    def __init__(self) -> None:
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, "qwen2.5:latest")
        self.llm     = OllamaClient(OLLAMA_MODEL)
        self._tracer = get_tracer()
        try:
            self.system_prompt = build_system_prompt("agents/synthesizer")
        except Exception:
            self.system_prompt = (
                "You are a synthesis agent. Summarize execution results clearly "
                "for a cybersecurity professional."
            )

    # ── Public ────────────────────────────────────────────────────────────────

    def synthesize(
        self,
        all_results: List[Any],
        objective: str = "",
        phase: str = "general",
    ) -> str:
        self._tracer.log("synthesizer", "synthesize_start", {
            "phase": phase,
            "result_count": len(all_results),
            "objective": objective[:80],
        })

        if not all_results:
            return "⚠️ No results to synthesize."

        is_network = (phase == "network_recon") or self._is_network_output(all_results)

        if is_network:
            self._tracer.log("synthesizer", "route→network_synthesis")
            out = self._synthesize_network(all_results, objective)
        else:
            self._tracer.log("synthesizer", "route→generic_synthesis")
            out = self._synthesize_generic(all_results, objective)

        self._tracer.log("synthesizer", "synthesize_done", {"output_len": len(out)})
        return out

    # ── Network synthesis (deterministic, no LLM) ────────────────────────────

    def _synthesize_network(self, results: List[Any], objective: str) -> str:
        report = NetworkReport()

        for item in results:
            stdout = _extract_stdout(item)
            if stdout.strip():
                discovered = report.ingest(stdout)
                if discovered:
                    self._tracer.log("synthesizer", "hosts_parsed", {
                        "count": len(discovered),
                        "ips": [h.ip for h in discovered],
                    })

        markdown = report.to_markdown()

        # Append warnings for commands that returned non-zero exit codes
        failed = [_extract_stderr(item) for item in results if _returncode(item) != 0]
        if any(failed):
            markdown += "\n\n---\n### ⚠️ Warnings / Errors\n"
            for err in failed[:5]:
                if err.strip():
                    markdown += f"- `{err[:200]}`\n"

        return markdown

    # ── Generic LLM synthesis ─────────────────────────────────────────────────

    def _synthesize_generic(self, results: List[Any], objective: str) -> str:
        clipped: List[dict] = []

        for item in results[:10]:
            if isinstance(item, dict):
                clipped.append({
                    "command":    item.get("command", ""),
                    "returncode": item.get("returncode", "?"),
                    "stdout":     (item.get("stdout", "") or "")[:500],
                    "stderr":     (item.get("stderr", "") or "")[:300],
                })
            elif isinstance(item, list):
                # FIX: use a local variable 'elem' — not 'r' from outer scope
                batch: List[dict] = []
                for elem in item[:5]:
                    if isinstance(elem, dict):
                        batch.append({
                            "command":    elem.get("command", ""),
                            "returncode": elem.get("returncode", "?"),
                            "stdout":     (elem.get("stdout", "") or "")[:300],
                        })
                clipped.append({"batch_results": batch})

        user_prompt = (
            f"Objective: {objective}\n\n"
            f"Execution Results:\n"
            f"{json.dumps(clipped, ensure_ascii=False, indent=2)}\n\n"
            "Synthesize into a clear, concise summary."
        )

        try:
            return self.llm.chat(self.system_prompt, user_prompt)
        except Exception as exc:
            logger.error(f"[Synthesizer] LLM failed: {exc}")
            parts = [_extract_stdout(item) for item in results if _extract_stdout(item)]
            return "\n\n".join(parts) if parts else "No output captured."

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_network_output(self, results: List[Any]) -> bool:
        for item in results:
            stdout = _extract_stdout(item)
            if any(sig in stdout for sig in self._NETWORK_SIGNATURES):
                return True
        return False