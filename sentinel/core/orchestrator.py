"""
core/orchestrator.py

Network recon keeps enumeration deterministic and shell-driven.
LLM usage is reserved for interpretation, planning, reflection, and
non-network synthesis.
"""

import uuid
from typing import Any, List

from agents.executors.shell_executor import ShellExecutor
from agents.orchestrator.agent import OrchestratorAgent
from agents.synthesizer.agent import SynthesizerAgent
from agents.web_researcher.agent import WebResearchAgent
from app.config import Config
from app.constants import STATUS_FATAL, STATUS_RETRY, STATUS_SUCCESS
from core.planner import Planner
from core.reflector import Reflector
from core.supervisor import Supervisor
from core.task_router import TaskRouter
from core.translator import Translator
from memory.memory import AgentMemory
from utils.dag_executor import DAGExecutor
from utils.freshness import assess_current_info_need
from utils.logger import setup_logger
from utils.network_parser import parse_discovery_output
from utils.os_context import (
    build_install_hint,
    build_discovery_command,
    build_host_scan_command,
    detect_os_context,
    get_arp_command,
    iter_cidr_detection_commands,
    parse_windows_cidr,
)
from utils.parallel_executor import ParallelExecutor
from utils.research_router import classify_research_intent
from utils.runtime_tracer import get_tracer
from utils.time_context import get_current_time_context

logger = setup_logger()


_NETWORK_KEYWORDS = {
    "red", "network", "dispositivos", "devices", "hosts", "scan",
    "recon", "puertos", "ports", "servicios", "services",
    "conectados", "connected", "nmap", "arp", "descubrir",
    "discover", "enumerar", "enumerate", "topolog",
    "subred", "subnet", "gateway", "router", "lan", "host",
    "mac", "hostname", "fingerprint", "sniff", "inventario",
    "mapa", "mapping", "topologia", "topology",
}


def _is_network_objective(objective: str) -> bool:
    words = set((objective or "").lower().split())
    return bool(words & _NETWORK_KEYWORDS)


def _flatten(results: Any) -> List[dict]:
    flat: List[dict] = []
    if isinstance(results, dict):
        for value in results.values():
            flat.extend(_flatten(value))
    elif isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                flat.append(item)
            elif isinstance(item, list):
                flat.extend(_flatten(item))
    elif isinstance(results, (str, bytes)):
        flat.append({"stdout": str(results), "returncode": 0, "command": ""})
    return flat


class Orchestrator:

    def __init__(self) -> None:
        self._tracer = get_tracer()
        self.agent = OrchestratorAgent()
        self.planner = Planner()
        self.translator = Translator()
        self.supervisor = Supervisor()
        self.reflector = Reflector()
        self.router = TaskRouter()
        self.synthesizer = SynthesizerAgent()
        self.web_agent = WebResearchAgent()
        self.memory = AgentMemory()
        self._shell = ShellExecutor()

        self.parallel_executor = ParallelExecutor(self.router)
        self.dag_executor = DAGExecutor(self.parallel_executor, self.router)

        self._tracer.log("orchestrator", "initialized", {
            "model": Config.MODELS.get(Config.DEFAULT_MODEL),
            "sandbox": Config.SANDBOX_MODE,
        })

    def handle_user_input(self, user_input: str) -> str:
        self._tracer.separator("NEW REQUEST")
        self._tracer.log("orchestrator", "handle_user_input", {"input": user_input[:120]})
        try:
            self.memory.reset_working()
            time_context = get_current_time_context()
            os_context = detect_os_context()
            interpreted = self.agent.interpret(user_input)
            task = self._create_task(interpreted, time_context=time_context, os_context=os_context)
            freshness = assess_current_info_need(f"{user_input}\n{task['objective']}")
            research = classify_research_intent(user_input, task["objective"])
            task["context"]["freshness"] = freshness
            task["context"]["research"] = research

            self._tracer.log("orchestrator", "task_created", {
                "objective": task["objective"][:100],
                "priority": task["priority"],
                "time_context": time_context,
                "os_context": os_context,
                "freshness": freshness,
                "research": research,
            })

            if research.get("route_mode") == "replace" and self.web_agent.should_handle(user_input, task["objective"]):
                self._tracer.log("orchestrator", "route_web_research")
                return self.web_agent.respond(user_input, task["objective"])

            if _is_network_objective(task["objective"]):
                self._tracer.log("orchestrator", "route_network_recon")
                return self._network_recon_loop(task)

            self._tracer.log("orchestrator", "route_react_loop")
            return self._react_loop(task)

        except Exception as exc:
            logger.error(f"[Orchestrator] Error: {exc}", exc_info=True)
            self._tracer.log("orchestrator", "fatal_error", {"error": str(exc)}, level="ERROR")
            return f"Error al procesar la solicitud: {exc}"

    def _create_task(
        self,
        interpreted: dict,
        time_context: dict | None = None,
        os_context: dict | None = None,
    ) -> dict:
        return {
            "task_id": str(uuid.uuid4()),
            "objective": interpreted.get("objective", ""),
            "constraints": interpreted.get("constraints", []),
            "priority": interpreted.get("priority", "medium"),
            "context": {
                "history": [],
                "errors": [],
                "attempt": 0,
                "time_context": time_context or get_current_time_context(),
                "os_context": os_context or detect_os_context(),
                "memory_summary": self.memory.get_context_summary(),
            },
        }

    def _network_recon_loop(self, task: dict) -> str:
        all_results: List[dict] = []

        self._tracer.log_phase("discovery:start")
        cidr = self._detect_cidr()
        self._tracer.log_network_event("cidr_detected", {"cidr": cidr})

        discovered_hosts = self._run_discovery(cidr, all_results)
        self._tracer.log_network_event("discovery_complete", {
            "hosts_found": len(discovered_hosts),
            "ips": discovered_hosts,
        })

        if not discovered_hosts:
            install_hint = build_install_hint("nmap", detect_os_context())
            return (
                "No se detectaron hosts activos en la red.\n"
                "Verifica que estes conectado y que nmap este instalado:\n"
                f"`{install_hint}`"
            )

        self._tracer.log_phase("enumeration:start", {
            "host_count": len(discovered_hosts),
            "hosts": discovered_hosts,
        })

        for ip in discovered_hosts:
            result = self._scan_host(ip)
            all_results.append(result)

        self._tracer.log_phase("enumeration:done", {"result_count": len(all_results)})
        self._tracer.log_phase("synthesis:start")

        self.memory.add_episode({
            "objective": task["objective"],
            "hosts_discovered": discovered_hosts,
            "status": "success",
        })

        return self.synthesizer.synthesize(
            all_results,
            objective=task["objective"],
            phase="network_recon",
            context=task["context"],
        )

    def _detect_cidr(self) -> str:
        os_context = detect_os_context()
        family = os_context["family"]

        for command in iter_cidr_detection_commands(os_context):
            result = self._shell.execute(command)
            if result["returncode"] != 0 or not result["stdout"]:
                continue

            if family == "windows":
                cidr = parse_windows_cidr(result["stdout"])
                if cidr:
                    self._tracer.log("network", "cidr_from_windows", {"cidr": cidr, "command": command})
                    return cidr

            if command == "ip route show":
                for line in result["stdout"].splitlines():
                    parts = line.split()
                    if parts and "/" in parts[0] and not parts[0].startswith("default"):
                        self._tracer.log("network", "cidr_from_ip_route", {"cidr": parts[0]})
                        return parts[0]

            if command == "ip addr show":
                import re
                import ipaddress

                match = re.search(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", result["stdout"])
                if match:
                    try:
                        network = ipaddress.ip_interface(match.group(1)).network
                        cidr = str(network)
                        self._tracer.log("network", "cidr_from_ip_addr", {"cidr": cidr})
                        return cidr
                    except Exception:
                        pass

            if command == "ifconfig":
                import re
                import ipaddress

                for line in result["stdout"].splitlines():
                    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)\s+netmask\s+(\S+)", line)
                    if not match:
                        continue
                    try:
                        ip_str = match.group(1)
                        mask_str = match.group(2)
                        if mask_str.startswith("0x"):
                            mask_int = int(mask_str, 16)
                            mask_str = ".".join(
                                str((mask_int >> (8 * i)) & 0xFF) for i in reversed(range(4))
                            )
                        network = ipaddress.ip_network(f"{ip_str}/{mask_str}", strict=False)
                        if not network.is_loopback:
                            cidr = str(network)
                            self._tracer.log("network", "cidr_from_ifconfig", {"cidr": cidr})
                            return cidr
                    except Exception:
                        continue

        r4 = self._shell.execute(get_arp_command(os_context))
        if r4["returncode"] == 0 and r4["stdout"]:
            import re

            ips = re.findall(r"\((\d+\.\d+\.\d+)\.\d+\)", r4["stdout"])
            if ips:
                cidr = f"{ips[0]}.0/24"
                self._tracer.log("network", "cidr_from_arp_fallback", {"cidr": cidr})
                return cidr

        self._tracer.log("network", "cidr_unknown_using_default", level="WARN")
        return "192.168.1.0/24"

    def _run_discovery(self, cidr: str, all_results: List[dict]) -> List[str]:
        hosts: List[str] = []
        os_context = detect_os_context()
        nmap_cmd = build_discovery_command(cidr, os_context)
        self._tracer.log("shell", f"discovery_sweep: {nmap_cmd}")
        result = self._shell.execute(nmap_cmd)
        all_results.append(result)
        if result["returncode"] == 0 and result["stdout"]:
            hosts = parse_discovery_output(result["stdout"])

        arp_result = self._shell.execute(get_arp_command(os_context))
        all_results.append(arp_result)
        if arp_result["returncode"] == 0 and arp_result["stdout"]:
            arp_hosts = parse_discovery_output(arp_result["stdout"])
            for host in arp_hosts:
                if host not in hosts:
                    hosts.append(host)

        return hosts

    def _scan_host(self, ip: str) -> dict:
        cmd = build_host_scan_command(ip, detect_os_context())
        self._tracer.log("network", f"scan_host:{ip}", {"cmd": cmd})
        result = self._shell.execute(cmd)
        result["target_ip"] = ip
        return result

    def _react_loop(self, task: dict) -> str:
        max_iterations = Config.MAX_ITERATIONS
        all_results: List[dict] = []

        for attempt in range(1, max_iterations + 1):
            self._tracer.separator(f"ReAct iter {attempt}/{max_iterations}")
            task["context"]["attempt"] = attempt

            try:
                self._tracer.log_react_phase(attempt, "reason")
                plan = self.planner.run(task)
                self._tracer.log("planner", "plan_ready", {"task_count": len(plan.get("tasks", []))})

                self._tracer.log_react_phase(attempt, "act")
                results = self.dag_executor.run(plan, self.translator, self.supervisor)
                result_list = _flatten(results)
                all_results.extend(result_list)

                self._tracer.log_react_phase(attempt, "observe", {"result_count": len(result_list)})
                reflection = self.reflector.run(result_list, task)
                status = reflection.get("status", STATUS_FATAL)
                reason = reflection.get("reason", "")

                self._tracer.log("reflector", f"reflect:{status}", {"reason": reason[:100]})

                self.memory.add_episode({
                    "attempt": attempt,
                    "objective": task["objective"],
                    "status": status,
                    "reason": reason,
                })
                task["context"]["history"].append({
                    "attempt": attempt,
                    "status": status,
                    "reason": reason,
                    "result_summary": str(result_list)[:500],
                })
                task["context"]["memory_summary"] = self.memory.get_context_summary()

                if status == STATUS_SUCCESS:
                    return self.synthesizer.synthesize(
                        all_results,
                        task["objective"],
                        context=task["context"],
                    )
                if status == STATUS_RETRY:
                    task["context"]["errors"].append(reason)
                    continue
                return f"Error fatal tras {attempt} intento(s): {reason}"

            except Exception as exc:
                logger.error(f"[ReAct] Exception iter {attempt}: {exc}", exc_info=True)
                self._tracer.log(
                    "orchestrator",
                    "react_exception",
                    {"attempt": attempt, "error": str(exc)[:200]},
                    level="ERROR",
                )
                task["context"]["errors"].append(str(exc))
                if attempt == max_iterations:
                    return f"Error tras {attempt} intento(s): {exc}"

        return f"Maximo de iteraciones ({max_iterations}) alcanzado."
