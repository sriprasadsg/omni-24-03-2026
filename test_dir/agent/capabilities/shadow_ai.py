from .base import BaseCapability
import psutil
import socket
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class ShadowAICapability(BaseCapability):
    
    # Known AI Provider domains/keywords for MVP matching
    AI_DOMAINS = [
        "openai.com", "api.openai.com", "chatgpt.com",
        "anthropic.com", "claude.ai",
        "gemini.google.com", "bard.google.com",
        "huggingface.co",
        "githubcopilot.com"
    ]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.dns_cache = {} # Simple cache IP -> Hostname

    @property
    def capability_id(self) -> str:
        return "shadow_ai"
    
    @property
    def capability_name(self) -> str:
        return "Shadow AI Network Monitor"
    
    def collect(self) -> Dict[str, Any]:
        """
        Scan active connections for traffic to known AI services.
        """
        suspicious_connections = []
        
        try:
            # unique active remote IPs on port 443
            connections = psutil.net_connections(kind='inet')
            
            for conn in connections:
                if conn.status == 'ESTABLISHED' and conn.raddr:
                    ip, port = conn.raddr
                    if port == 443:
                        hostname = self._resolve_ip(ip)
                        if self._is_ai_domain(hostname):
                            try:
                                proc = psutil.Process(conn.pid)
                                proc_name = proc.name()
                            except:
                                proc_name = "unknown"

                            suspicious_connections.append({
                                "process": proc_name,
                                "pid": conn.pid,
                                "remote_ip": ip,
                                "remote_host": hostname,
                                "timestamp": datetime.now().isoformat()
                            })

        except Exception as e:
            logger.error(f"Error scanning network: {e}")
            return {"error": str(e)}

        return {
            "ai_connections": suspicious_connections,
            "scan_count": len(connections) if 'connections' in locals() else 0,
            "detected_count": len(suspicious_connections)
        }

    def _resolve_ip(self, ip: str) -> str:
        # Avoid gethostbyaddr hang on Windows
        return ip

    def _is_ai_domain(self, hostname: str) -> bool:
        if not hostname: return False
        return any(domain in hostname.lower() for domain in self.AI_DOMAINS)
