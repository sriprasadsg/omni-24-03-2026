"""
Web Request Monitoring Capability
Monitors outbound HTTP/HTTPS connections and correlates them with local processes.
"""
from .base import BaseCapability
import psutil
import socket
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class WebMonitorCapability(BaseCapability):
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.dns_cache = {}

    @property
    def capability_id(self) -> str:
        return "web_monitor"
    
    @property
    def capability_name(self) -> str:
        return "Web Request Monitor"
    
    def collect(self) -> Dict[str, Any]:
        """
        Scan active connections for outbound web traffic.
        """
        web_connections = []
        target_ports = [80, 443, 8080, 8443]
        
        try:
            connections = psutil.net_connections(kind='inet')
            
            for conn in connections:
                if conn.status == 'ESTABLISHED' and conn.raddr:
                    ip, port = conn.raddr
                    if port in target_ports:
                        hostname = self._resolve_ip(ip)
                        
                        try:
                            proc = psutil.Process(conn.pid)
                            proc_name = proc.name()
                            cmdline = " ".join(proc.cmdline())
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            proc_name = "unknown"
                            cmdline = "unknown"

                        web_connections.append({
                            "process": proc_name,
                            "command": cmdline,
                            "pid": conn.pid,
                            "remote_ip": ip,
                            "remote_host": hostname,
                            "port": port,
                            "timestamp": datetime.now().isoformat()
                        })

        except Exception as e:
            logger.error(f"Error scanning network: {e}")
            return {"error": str(e), "status": "error"}

        return {
            "web_connections": web_connections,
            "count": len(web_connections),
            "status": "success"
        }

    def _resolve_ip(self, ip: str) -> str:
        return ip
