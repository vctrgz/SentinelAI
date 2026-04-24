"""
core/orchestrator.py

Orchestrator with:
  - Dynamic per-host task injection for network recon (multi-phase)
  - SynthesizerAgent for structured output
  - Full RuntimeTracer instrumentation on every step
"""

import uuid
from typing import Any, List

from agents.orchestrator.agent import OrchestratorAgent
from agents.synthesizer.agent import SynthesizerAgent
from core.planner import Planner
from core.reflector import Reflector
from core.supervisor import Supervisor
from core.task_router import TaskRouter
from core.translator import Translator
from utils.dag_executor import DAGExecutor
from utils.parallel_executor import ParallelExecutor
from utils.network_parser import parse_discovery_output
from memory.memory import AgentMemory
from utils.logger import setup_logger
from utils.runtime_tracer import get_tracer
from app.config import Config
from app.constants import STATUS_SUCCESS, STATUS_RETRY, STATUS_FATAL

logger = setup_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_network_objective(objective: str) -> bool:
    keywords = [
        "red", "network", "dispositivos", "devices", "hosts", "scan",
        "recon", "puertos", "ports", "servicios", "services", "ip",
        "mac", "conectados", "connected", "nmap", "arp", "descubrir",
        "discover", "enumerar", "enumerate", "topolog",
    ]
    obj_lower = objective.lower()
    return any(k in obj_lower for k in keywords)


def _flatten_results(results: Any) -> List[dict]:
    """Recursively flatten nested result structures into a flat list of dicts."""
    flat: List[dict] = []
    if isinstance(results, dict):
        for v in results.values():
            flat.extend(_flatten_results(v))
    elif isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                flat.append(item)
            elif isinstance(item, list):
                flat.extend(_flatten_results(item))
            elif isinstance(item, (str, bytes)):
                flat.append({"stdout": str(item), "returncode": 0, "command": ""})
    elif isinstance(results, (str, bytes)):
        flat.append({"stdout": str(results), "returncode": 0, "command": ""})
    return flat


def _extract_all_stdout(results: Any) -> str:
    return "\n".join(
        r.get("stdout", "") for r in _flatten_results(results) if r.get("stdout")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class Orchestrator:

    def __init__(self) -> None:
        self._tracer     = get_tracer()
        self.agent       = OrchestratorAgent()
        self.planner     = Planner()
        self.translator  = Translator()
        self.supervisor  = Supervisor()
        self.reflector   = Reflector()
        self.router      = TaskRouter()
        self.synthesizer = SynthesizerAgent()
        self.memory      = AgentMemory()

        self.parallel_executor = ParallelExecutor(self.router)
        self.dag_executor      = DAGExecutor(self.parallel_executor, self.router)

        self._tracer.log("orchestrator", "initialized", {
            "model": Config.MODELS.get(Config.DEFAULT_MODEL),
            "sandbox": Config.SANDBOX_MODE,
            "max_iterations": Config.MAX_ITERATIONS,
        })

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def handle_user_input(self, user_input: str) -> str:
        self._tracer.separator("NEW REQUEST")
        self._tracer.log("orchestrator", "handle_user_input",
                         {"input": user_input[:120]})
        try:
            self.memory.reset_working()
            interpreted = self.agent.interpret(user_input)
            task        = self._create_task(interpreted)

            self._tracer.log("orchestrator", "task_created", {
                "task_id":   task["task_id"],
                "objective": task["objective"][:100],
                "priority":  task["priority"],
            })

            if _is_network_objective(task["objective"]):
                self._tracer.log("orchestrator", "route→network_recon_loop")
                return self._network_recon_loop(task)

            self._tracer.log("orchestrator", "route→react_loop")
            return self._react_loop(task)

        except Exception as exc:
            logger.error(f"[Orchestrator] Error: {exc}", exc_info=True)
            self._tracer.log("orchestrator", "fatal_error", {"error": str(exc)}, level="ERROR")
            return f"❌ Error al procesar la solicitud: {exc}"

    # ─────────────────────────────────────────────────────────────────────────
    # Task factory
    # ─────────────────────────────────────────────────────────────────────────

    def _create_task(self, interpreted: dict) -> dict:
        return {
            "task_id":    str(uuid.uuid4()),
            "objective":  interpreted.get("objective", ""),
            "constraints": interpreted.get("constraints", []),
            "priority":   interpreted.get("priority", "medium"),
            "context": {
                "history":        [],
                "errors":         [],
                "attempt":        0,
                "memory_summary": self.memory.get_context_summary(),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Network recon — 3-phase loop with dynamic host injection
    # ─────────────────────────────────────────────────────────────────────────

    def _network_recon_loop(self, task: dict) -> str:
        objective   = task["objective"]
        all_results: List[dict] = []

        # ── Phase 1: Discovery ────────────────────────────────────────────────
        self._tracer.log_phase("discovery:start", {"objective": objective[:80]})

        discovery_plan = {
            "tasks": [
                {
                    "id":          1,
                    "description": "Detect local network CIDR and interface info",
                    "depends_on":  [],
                    "mode":        "parallel",
                    "phase":       "discovery",
                },
                {
                    "id":          2,
                    "description": (
                        "Run a full network host discovery sweep using "
                        "'sudo nmap -sn <CIDR>' across the entire local network CIDR "
                        "to find all live hosts. Also run 'arp -a' for cached entries."
                    ),
                    "depends_on":  [1],
                    "mode":        "sequential",
                    "phase":       "discovery",
                },
            ]
        }

        try:
            discovery_results = self.dag_executor.run(
                discovery_plan, self.translator, self.supervisor,
                context=task["context"]
            )
            all_results.extend(_flatten_results(discovery_results))
            raw_output       = _extract_all_stdout(discovery_results)
            discovered_hosts = parse_discovery_output(raw_output)

            self._tracer.log_network_event("discovery_complete", {
                "hosts_found": len(discovered_hosts),
                "ips": discovered_hosts,
            })

        except Exception as exc:
            logger.error(f"[Recon] Phase 1 failed: {exc}", exc_info=True)
            self._tracer.log("orchestrator", "phase1_failed", {"error": str(exc)}, level="ERROR")
            return f"❌ Error en fase de descubrimiento: {exc}"

        # Fallback: arp -a if nmap found nothing
        if not discovered_hosts:
            self._tracer.log("orchestrator", "discovery_fallback→arp-a", level="WARN")
            from agents.executors.shell_executor import ShellExecutor
            arp_result = ShellExecutor().execute("arp -a")
            if arp_result.get("stdout"):
                all_results.append(arp_result)
                discovered_hosts = parse_discovery_output(arp_result["stdout"])

        if not discovered_hosts:
            return (
                "⚠️ No se detectaron hosts activos en la red.\n"
                "Verifica que estés conectado y que nmap esté instalado:\n"
                "`sudo apt install nmap -y`"
            )

        # ── Phase 2: Per-Host Enumeration ─────────────────────────────────────
        self._tracer.log_phase("enumeration:start", {
            "host_count": len(discovered_hosts),
            "hosts": discovered_hosts,
        })

        host_tasks = [
            {
                "id":          100 + idx,
                "description": (
                    f"Deep port scan, service detection, and OS fingerprinting on host {ip}. "
                    f"Command: sudo nmap -sV -sC -O -T4 --open {ip}"
                ),
                "depends_on":  [],
                "mode":        "parallel",
                "phase":       "enumeration",
                "target_ip":   ip,
            }
            for idx, ip in enumerate(discovered_hosts)
        ]

        try:
            enum_results = self.dag_executor.run(
                {"tasks": host_tasks},
                self.translator,
                self.supervisor,
                context={
                    **task["context"],
                    "discovered_hosts": discovered_hosts,
                    "phase": "enumeration",
                },
            )
            enum_flat = _flatten_results(enum_results)
            all_results.extend(enum_flat)

            self._tracer.log_phase("enumeration:done", {
                "result_count": len(enum_flat),
            })

        except Exception as exc:
            logger.error(f"[Recon] Phase 2 failed: {exc}", exc_info=True)
            self._tracer.log("orchestrator", "phase2_partial_failure",
                             {"error": str(exc)}, level="WARN")

        # Store episode
        self.memory.add_episode({
            "objective":        objective,
            "hosts_discovered": discovered_hosts,
            "result_count":     len(all_results),
            "status":           "success",
        })

        # ── Phase 3: Synthesis ────────────────────────────────────────────────
        self._tracer.log_phase("synthesis:start")
        report = self.synthesizer.synthesize(
            all_results,
            objective=objective,
            phase="network_recon",
        )
        self._tracer.separator("RESULT")
        return report

    # ─────────────────────────────────────────────────────────────────────────
    # Generic ReAct loop
    # ─────────────────────────────────────────────────────────────────────────

    def _react_loop(self, task: dict) -> str:
        max_iterations = Config.MAX_ITERATIONS
        all_results: List[dict] = []

        for attempt in range(1, max_iterations + 1):
            self._tracer.separator(f"ReAct iter {attempt}/{max_iterations}")
            task["context"]["attempt"] = attempt

            try:
                # REASON
                self._tracer.log_react_phase(attempt, "reason")
                plan = self.planner.run(task)
                self._tracer.log("planner", "plan_ready", {
                    "task_count": len(plan.get("tasks", [])),
                })

                # ACT
                self._tracer.log_react_phase(attempt, "act")
                results = self.dag_executor.run(
                    plan, self.translator, self.supervisor
                )
                result_list = _flatten_results(results)
                all_results.extend(result_list)

                # OBSERVE
                self._tracer.log_react_phase(attempt, "observe",
                                             {"result_count": len(result_list)})
                reflection = self.reflector.run(result_list, task)
                status     = reflection.get("status", STATUS_FATAL)
                reason     = reflection.get("reason", "")

                self._tracer.log("reflector", f"reflect:{status}", {"reason": reason[:100]})

                self.memory.add_episode({
                    "attempt":   attempt,
                    "objective": task["objective"],
                    "plan":      plan,
                    "results":   result_list,
                    "status":    status,
                    "reason":    reason,
                })

                task["context"]["history"].append({
                    "attempt":        attempt,
                    "status":         status,
                    "reason":         reason,
                    "result_summary": str(result_list)[:500],
                })
                task["context"]["memory_summary"] = self.memory.get_context_summary()

                if status == STATUS_SUCCESS:
                    self._tracer.log("orchestrator", "react_success")
                    return self.synthesizer.synthesize(all_results, task["objective"])

                if status == STATUS_RETRY:
                    task["context"]["errors"].append(reason)
                    continue

                # FATAL
                self._tracer.log("orchestrator", "react_fatal", {"reason": reason}, level="ERROR")
                return f"❌ Error fatal tras {attempt} intento(s): {reason}"

            except Exception as exc:
                error_msg = str(exc)
                logger.error(f"[ReAct] Exception on attempt {attempt}: {error_msg}", exc_info=True)
                self._tracer.log("orchestrator", "react_exception",
                                 {"attempt": attempt, "error": error_msg[:200]}, level="ERROR")
                task["context"]["errors"].append(error_msg)
                if attempt == max_iterations:
                    return f"❌ Error tras {attempt} intento(s): {error_msg}"

        return f"⚠️ Máximo de iteraciones ({max_iterations}) alcanzado sin resolver la tarea."

    # ─────────────────────────────────────────────────────────────────────────
    # HITL
    # ─────────────────────────────────────────────────────────────────────────

    def _ask_user_confirmation(self, commands: list) -> bool:
        explanation = self.agent.format_confirmation(commands)
        print("\n⚠️  Confirmación requerida:\n")
        print(explanation)
        response = input("\n¿Continuar? (y/n): ").strip().lower()
        return response == "y"