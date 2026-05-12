"""
Kubernetes Monitor Capability
Runs as a DaemonSet to intercept cross-pod traffic and monitor container start/stop events.
"""
import os
import asyncio
import json
from .base import AgentCapability

class K8sMonitorCapability(AgentCapability):
    def __init__(self, agent):
        super().__init__(agent)
        self.name = "k8s_monitor"
        self.version = "1.0.0"
        self.description = "eBPF-based Kubernetes pod and traffic monitoring"
        self.is_running = False
        self.namespace = os.environ.get("POD_NAMESPACE", "default")
        self.node_name = os.environ.get("NODE_NAME", "unknown-node")

    async def start(self):
        """Start the K8s monitor capability."""
        if not await self._kubectl_available():
            self.agent.logger.warning(
                f"[{self.name}] kubectl not found or not executable — "
                "K8s monitoring is disabled. Install kubectl and ensure KUBECONFIG is set."
            )
            return
        self.is_running = True
        self.agent.logger.info(f"[{self.name}] Starting K8s monitoring on node {self.node_name}")
        asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop the K8s monitor capability."""
        self.is_running = False
        self.agent.logger.info(f"[{self.name}] Stopped K8s monitoring")

    async def _kubectl_available(self) -> bool:
        """Check if kubectl is installed and can connect to a cluster."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "kubectl", "cluster-info",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    async def get_status(self) -> dict:
        pod_count = await self._count_pods()
        return {
            "name": self.name,
            "version": self.version,
            "status": "running" if self.is_running else "stopped",
            "metrics": {
                "pods_monitored": pod_count,
                "node": self.node_name,
                "namespace": self.namespace,
            }
        }

    async def _count_pods(self) -> int:
        try:
            proc = await asyncio.create_subprocess_exec(
                "kubectl", "get", "pods", "-n", self.namespace, "--no-headers",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return len([l for l in stdout.decode().splitlines() if l.strip()])
        except Exception:
            return 0

    async def _monitor_loop(self):
        """Poll real Kubernetes pod events via kubectl and forward to the platform."""
        while self.is_running:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "kubectl", "get", "events", "-n", self.namespace,
                    "--sort-by=.metadata.creationTimestamp",
                    "-o", "json",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                data = json.loads(stdout.decode())
                items = data.get("items", [])[-10:]  # last 10 events

                for item in items:
                    event = {
                        "type": "k8s_event",
                        "namespace": item.get("metadata", {}).get("namespace", self.namespace),
                        "reason": item.get("reason", ""),
                        "message": item.get("message", ""),
                        "involved_object": item.get("involvedObject", {}).get("name", ""),
                        "node_name": self.node_name,
                        "event_time": item.get("metadata", {}).get("creationTimestamp", ""),
                    }
                    await self.agent._send_to_server("k8s_telemetry", event)
            except Exception as e:
                self.agent.logger.error(f"[{self.name}] Error in monitor loop: {e}")

            await asyncio.sleep(60)  # 60-second polling interval
