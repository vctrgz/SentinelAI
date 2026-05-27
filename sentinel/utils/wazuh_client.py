"""
utils/wazuh_client.py

Cliente REST para la API de Wazuh Manager.
Maneja autenticación JWT, refresco de token y los endpoints principales.
"""
from __future__ import annotations

import time
from typing import Any

import requests
import urllib3

from app.config import Config
from utils.logger import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class WazuhAuthError(Exception):
    pass


class WazuhAPIError(Exception):
    pass


class WazuhClient:
    """
    Wrapper sobre la REST API de Wazuh (v4+).
    Gestiona el ciclo de vida del JWT (expira cada 15 min).
    """

    TOKEN_TTL = 840  # segundos antes de refrescar (14 min, margen de 1 min)

    def __init__(self) -> None:
        self.host     = (Config.WAZUH_HOST or "").rstrip("/")
        self.user     = Config.WAZUH_USER
        self.password = Config.WAZUH_PASSWORD
        self.verify   = Config.WAZUH_VERIFY_SSL
        self._token: str = ""
        self._token_ts: float = 0.0

    # ─────────────────────────────────────────────────────────────
    # Auth
    # ─────────────────────────────────────────────────────────────

    def _authenticate(self) -> None:
        url = f"{self.host}/security/user/authenticate"
        try:
            resp = requests.post(
                url,
                auth=(self.user, self.password),
                verify=self.verify,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token    = data["data"]["token"]
            self._token_ts = time.monotonic()
            logger.info("[WazuhClient] JWT obtenido correctamente.")
        except Exception as exc:
            raise WazuhAuthError(f"Autenticación Wazuh fallida: {exc}") from exc

    def _get_token(self) -> str:
        if not self._token or (time.monotonic() - self._token_ts) > self.TOKEN_TTL:
            self._authenticate()
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ─────────────────────────────────────────────────────────────
    # HTTP helpers
    # ─────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.host}{path}"
        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params or {},
                verify=self.verify,
                timeout=20,
            )
            if resp.status_code == 401:
                # Token expirado a mitad — refrescar y reintentar una vez
                self._token = ""
                resp = requests.get(
                    url,
                    headers=self._headers(),
                    params=params or {},
                    verify=self.verify,
                    timeout=20,
                )
            resp.raise_for_status()
            return resp.json()
        except WazuhAuthError:
            raise
        except Exception as exc:
            raise WazuhAPIError(f"Error GET {path}: {exc}") from exc

    # ─────────────────────────────────────────────────────────────
    # API endpoints
    # ─────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Comprueba conectividad básica."""
        if not self.host or not self.user or not self.password:
            return False
        try:
            self._authenticate()
            return True
        except Exception:
            return False

    def get_alerts(
        self,
        limit: int = 100,
        min_level: int | None = None,
        agent_id: str | None = None,
    ) -> list[dict]:
        """
        Devuelve alertas recientes.
        min_level: filtra por nivel de regla (0–15, 10+ = crítico)
        """
        params: dict[str, Any] = {
            "limit": min(limit, 500),
            "sort": "-timestamp",
        }
        q_parts = []
        if min_level is not None:
            q_parts.append(f"rule.level>={min_level}")
        if agent_id:
            q_parts.append(f"agent.id={agent_id}")
        if q_parts:
            params["q"] = ",".join(q_parts)

        data = self._get("/alerts", params)
        return data.get("data", {}).get("affected_items", [])

    def get_logs(self, limit: int = 100, log_type: str | None = None) -> list[dict]:
        """Devuelve logs del manager."""
        params: dict[str, Any] = {"limit": min(limit, 500), "sort": "-timestamp"}
        if log_type:
            params["type_log"] = log_type
        data = self._get("/manager/logs", params)
        return data.get("data", {}).get("affected_items", [])

    def get_rules(
        self,
        limit: int = 200,
        rule_ids: list[int] | None = None,
        level: int | None = None,
    ) -> list[dict]:
        """Devuelve reglas de detección."""
        params: dict[str, Any] = {"limit": min(limit, 2000)}
        if rule_ids:
            params["rule_ids"] = ",".join(str(r) for r in rule_ids)
        if level is not None:
            params["level"] = level
        data = self._get("/rules", params)
        return data.get("data", {}).get("affected_items", [])

    def get_agents(self, status: str = "active") -> list[dict]:
        """Devuelve agentes registrados."""
        data = self._get("/agents", {"status": status, "limit": 500})
        return data.get("data", {}).get("affected_items", [])

    def get_agent_alerts(self, agent_id: str, limit: int = 50) -> list[dict]:
        """Alertas específicas de un agente."""
        return self.get_alerts(limit=limit, agent_id=agent_id)

    def get_critical_alerts(self, limit: int = 50) -> list[dict]:
        """Shortcut: alertas nivel >= Config.WAZUH_ALERT_LEVEL_MIN."""
        return self.get_alerts(limit=limit, min_level=Config.WAZUH_ALERT_LEVEL_MIN)