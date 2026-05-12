from .base import BaseCapability
import psutil
import socket
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ShadowAICapability(BaseCapability):

    # Known AI cloud provider domains
    AI_DOMAINS = [
        "openai.com", "api.openai.com", "chatgpt.com",
        "anthropic.com", "claude.ai",
        "gemini.google.com", "bard.google.com",
        "huggingface.co",
        "githubcopilot.com",
        "cohere.ai", "mistral.ai", "together.ai", "groq.com",
        "perplexity.ai", "replicate.com",
    ]

    # Local AI process names / ports (Ollama, LM Studio, LocalAI, etc.)
    LOCAL_AI_PROCESSES = [
        "ollama", "lm_studio", "lmstudio", "localai", "llamafile",
        "llama.cpp", "llama-server", "koboldcpp", "text-generation-webui",
        "oobabooga", "jan", "lollms", "gpt4all",
    ]
    # Ports commonly used by local AI inference servers
    LOCAL_AI_PORTS = {
        11434: "Ollama",
        1234:  "LM Studio",
        8080:  "LocalAI / llama.cpp",
        5000:  "text-generation-webui (default)",
        7860:  "text-generation-webui (gradio)",
        8000:  "Generic local LLM server",
        11435: "Ollama alt port",
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.dns_cache: Dict[str, str] = {}

    @property
    def capability_id(self) -> str:
        return "shadow_ai"

    @property
    def capability_name(self) -> str:
        return "Shadow AI Network Monitor"

    def collect(self) -> Dict[str, Any]:
        network_hits = self._scan_network_connections()
        local_hits   = self._scan_local_ai_processes()
        port_hits    = self._scan_local_ai_ports()

        return {
            "ai_connections":      network_hits,
            "local_ai_processes":  local_hits,
            "local_ai_ports":      port_hits,
            "detected_count":      len(network_hits) + len(local_hits) + len(port_hits),
            "scan_timestamp":      datetime.now().isoformat(),
        }

    # ── Network traffic scan ──────────────────────────────────────────────────

    def _scan_network_connections(self) -> List[Dict[str, Any]]:
        suspicious = []
        try:
            connections = psutil.net_connections(kind="inet")
            for conn in connections:
                if conn.status == "ESTABLISHED" and conn.raddr:
                    ip, port = conn.raddr
                    if port == 443:
                        hostname = self._resolve_ip(ip)
                        if self._is_ai_domain(hostname):
                            proc_name = "unknown"
                            try:
                                if conn.pid:
                                    proc_name = psutil.Process(conn.pid).name()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                            suspicious.append({
                                "type": "cloud_ai_connection",
                                "process": proc_name,
                                "pid": conn.pid,
                                "remote_ip": ip,
                                "remote_host": hostname,
                                "timestamp": datetime.now().isoformat(),
                            })
        except Exception as e:
            logger.error("Error scanning network connections: %s", e)
        return suspicious

    # ── Local AI process scan ─────────────────────────────────────────────────

    def _scan_local_ai_processes(self) -> List[Dict[str, Any]]:
        findings = []
        try:
            for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    name_lower = (proc.info.get("name") or "").lower()
                    exe_lower  = (proc.info.get("exe") or "").lower()
                    cmd_lower  = " ".join(proc.info.get("cmdline") or []).lower()

                    matched = None
                    for ai_proc in self.LOCAL_AI_PROCESSES:
                        if ai_proc in name_lower or ai_proc in exe_lower or ai_proc in cmd_lower:
                            matched = ai_proc
                            break

                    if matched:
                        findings.append({
                            "type": "local_ai_process",
                            "process": proc.info.get("name"),
                            "pid": proc.info.get("pid"),
                            "matched_pattern": matched,
                            "exe": proc.info.get("exe"),
                            "timestamp": datetime.now().isoformat(),
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error("Error scanning local AI processes: %s", e)
        return findings

    # ── Local AI port scan ────────────────────────────────────────────────────

    def _scan_local_ai_ports(self) -> List[Dict[str, Any]]:
        findings = []
        try:
            listening = {
                conn.laddr.port
                for conn in psutil.net_connections(kind="inet")
                if conn.status == "LISTEN" and conn.laddr
            }
            for port, service in self.LOCAL_AI_PORTS.items():
                if port in listening:
                    findings.append({
                        "type": "local_ai_port",
                        "port": port,
                        "service": service,
                        "timestamp": datetime.now().isoformat(),
                    })
        except Exception as e:
            logger.error("Error scanning local AI ports: %s", e)
        return findings

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_ip(self, ip: str) -> str:
        if ip in self.dns_cache:
            return self.dns_cache[ip]
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            self.dns_cache[ip] = hostname
            return hostname
        except (socket.herror, socket.gaierror, socket.timeout):
            self.dns_cache[ip] = ip
            return ip

    def _is_ai_domain(self, hostname: str) -> bool:
        if not hostname:
            return False
        return any(domain in hostname.lower() for domain in self.AI_DOMAINS)
