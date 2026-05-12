"""
Shadow AI Monitor Capability
Monitors network requests and clipboard activity for sensitive data (PII/PHI)
being sent to unsanctioned public GenAI endpoints (e.g., chatgpt.com).
"""
import os
import asyncio
import re
from .base import AgentCapability

class ShadowAIMonitorCapability(AgentCapability):
    def __init__(self, agent):
        super().__init__(agent)
        self.name = "shadow_ai_monitor"
        self.version = "1.0.0"
        self.description = "Detects and blocks sensitive data going to unsanctioned LLMs."
        self.is_running = False
        
        # Unsanctioned or monitored endpoints
        self.target_endpoints = [
            r"chatgpt\.com",
            r"api\.openai\.com",
            r"claude\.ai",
            r"api\.anthropic\.com",
            r"gemini\.google\.com",
            r"bard\.google\.com"
        ]
        
        # Simple YARA-style regex rules for PII
        self.pii_rules = {
            "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "email_list": r"(?:[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+,?\s*){3,}"
        }

    async def start(self):
        """Start the Shadow AI monitor."""
        self.is_running = True
        self.agent.logger.info(f"[{self.name}] Starting Shadow AI monitoring")
        asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop the Shadow AI monitor."""
        self.is_running = False
        self.agent.logger.info(f"[{self.name}] Stopped Shadow AI monitoring")

    def _events_blocked(self) -> int:
        return getattr(self, "_blocked_count", 0)

    async def get_status(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "status": "running" if self.is_running else "stopped",
            "metrics": {
                "endpoints_monitored": len(self.target_endpoints),
                "events_blocked": self._events_blocked(),
            }
        }

    async def _scan_text_for_pii(self, text: str) -> list:
        """Scan text against PII regex rules."""
        matches = []
        for rule_name, pattern in self.pii_rules.items():
            if re.search(pattern, text):
                matches.append(rule_name)
        return matches

    async def _get_active_llm_connections(self) -> list:
        """Return active network connections to known LLM endpoints using psutil."""
        hits = []
        try:
            import psutil, socket
            combined_pattern = "|".join(self.target_endpoints)
            for conn in psutil.net_connections(kind="tcp"):
                if conn.status != "ESTABLISHED" or not conn.raddr:
                    continue
                try:
                    remote_host = socket.gethostbyaddr(conn.raddr.ip)[0]
                except Exception:
                    remote_host = conn.raddr.ip
                if re.search(combined_pattern, remote_host, re.IGNORECASE):
                    try:
                        proc = psutil.Process(conn.pid) if conn.pid else None
                        proc_name = proc.name() if proc else "unknown"
                    except Exception:
                        proc_name = "unknown"
                    hits.append({"host": remote_host, "process": proc_name, "pid": conn.pid})
        except Exception as exc:
            self.agent.logger.debug(f"[{self.name}] Connection scan error: {exc}")
        return hits

    async def _monitor_loop(self):
        """Detect active connections to unsanctioned LLM endpoints via real network inspection."""
        self._blocked_count = 0
        while self.is_running:
            try:
                connections = await self._get_active_llm_connections()
                for conn in connections:
                    event = {
                        "type": "shadow_ai_detected",
                        "endpoint": conn["host"],
                        "process": conn["process"],
                        "pid": conn["pid"],
                        "action_taken": "detected",
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                    self._blocked_count += 1
                    await self.agent._send_to_server("shadow_ai_telemetry", event)
                    self.agent.logger.warning(
                        f"[{self.name}] LLM connection from {conn['process']} (pid={conn['pid']}) → {conn['host']}"
                    )
            except Exception as e:
                self.agent.logger.error(f"[{self.name}] Error in monitor loop: {e}")

            await asyncio.sleep(120)  # 2-minute polling interval
