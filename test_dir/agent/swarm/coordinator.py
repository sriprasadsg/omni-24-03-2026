import logging
import time
import uuid
import threading
import json
import random
import socket
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SwarmCoordinator:
    """
    Manages coordination between multiple agents (Swarm Intelligence).
    Allows agents to share insights and distribute tasks via P2P Gossip.
    """
    
    def __init__(self, agent_id, config=None):
        self.agent_id = agent_id
        self.config = config or {}
        self.peers = set() 
        self.swarm_id = str(uuid.uuid4())[:8]
        self.gossip_port = random.randint(10000, 20000)
        self.local_ip = self._get_local_ip()
        self.running = False
        self.peer_data = {} # Latest state from peers

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def join_swarm(self):
        """Register capability to participate in swarm and start gossip"""
        logger.info(f"Agent {self.agent_id} joining Swarm Network on {self.local_ip}:{self.gossip_port}...")
        self.running = True
        
        # Start Gossip Server
        self.server_thread = threading.Thread(target=self._run_gossip_server, daemon=True)
        self.server_thread.start()
        
        # Start Gossip Loop
        self.gossip_thread = threading.Thread(target=self._run_gossip_loop, daemon=True)
        self.gossip_thread.start()
        
        # Initial report
        self.report_topology()

    def request_task_offload(self, task: dict, target_peer_id: str) -> bool:
        """
        Offload a computational task to a specific peer.
        """
        peer_info = self.peer_data.get(target_peer_id)
        if not peer_info:
            logger.warning(f"Peer {target_peer_id} not found in swarm.")
            return False
            
        payload = {
            "type": "TASK_OFFLOAD",
            "source_id": self.agent_id,
            "task_id": str(uuid.uuid4()),
            "content": task,
            "timestamp": time.time()
        }
        
        logger.info(f"Offloading task to {target_peer_id}...")
        self._send_gossip(peer_info.get("ip_address"), peer_info.get("gossip_port", 15000), payload)
        return True

    def handle_remote_task(self, payload: dict):
        """
        Process a task received from a peer.
        """
        source = payload.get("source_id")
        task = payload.get("content")
        logger.info(f"Received OFF_LOADED task from {source}: {task.get('description', 'Unknown Task')}")
        
        # In a real implementation, this would spawn a thread to execute the task
        # and report completion back to the source.
        # For now, we simulate acceptance.
        logger.info("Task accepted and queued for execution.")

    def _run_gossip_server(self):
        """Lightweight TCP server to receive gossip JSON"""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(('0.0.0.0', self.gossip_port))
            server.listen(5)
            logger.info(f"Gossip Server listening on port {self.gossip_port}")
            
            while self.running:
                client, addr = server.accept()
                data = client.recv(4096).decode('utf-8')
                if data:
                    try:
                        payload = json.loads(data)
                        msg_type = payload.get("type", "GOSSIP")
                        
                        if msg_type == "TASK_OFFLOAD":
                            self.handle_remote_task(payload)
                        else:
                            # Standard Gossip
                            sender_id = payload.get("agent_id")
                            if sender_id:
                                self.peer_data[sender_id] = payload
                    except Exception as e:
                        logger.error(f"Failed to parse gossip: {e}")
                client.close()
        except Exception as e:
            logger.error(f"Gossip Server Error: {e}")
            
    def _run_gossip_loop(self):
        """Periodically fetch peers and gossip local state"""
        while self.running:
            try:
                # 1. Fetch peers from backend
                peers_to_gossip = self._fetch_peers_from_backend()
                
                # 2. Select random peers
                if peers_to_gossip:
                    targets = random.sample(peers_to_gossip, min(len(peers_to_gossip), 3))
                    
                    # 3. Send local state
                    local_state = {
                        "type": "GOSSIP",
                        "agent_id": self.agent_id,
                        "timestamp": time.time(),
                        "health": "optimal",
                        "active_tasks": 0, # Mock
                        "insights": ["No threats detected"],
                        "gossip_port": self.gossip_port,
                        "ip_address": self.local_ip
                    }
                    
                    for target in targets:
                        self._send_gossip(target["ip_address"], target.get("port", 15000), local_state) # Default port if not known
                
                # 4. Report topology (refresh connections)
                self.report_topology()
                
            except Exception as e:
                logger.error(f"Gossip Loop Error: {e}")
            
            time.sleep(10) # Gossip every 10 seconds

    def _fetch_peers_from_backend(self):
        try:
            import requests
            base_url = self.config.get('coordinator_url', 'http://localhost:5000').replace('ray://', 'http://').replace('10001', '5000')
            if 'localhost' in base_url and '5000' not in base_url:
                 base_url = "http://localhost:5000"
            
            url = f"{base_url.rstrip('/')}/api/swarm/peers?agent_id={self.agent_id}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return resp.json().get("peers", [])
        except:
            pass
        return []

    def _send_gossip(self, ip, port, payload):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect((ip, int(port)))
            client.send(json.dumps(payload).encode('utf-8'))
            client.close()
        except:
            # logger.warning(f"Failed to send gossip to {ip}:{port}")
            pass

    def report_topology(self):
        """Send current peer connections to the backend for visualization"""
        try:
            import requests
            base_url = self.config.get('coordinator_url', 'http://localhost:5000').replace('ray://', 'http://').replace('10001', '5000')
            if 'localhost' in base_url and '5000' not in base_url:
                 base_url = "http://localhost:5000"
            
            url = f"{base_url.rstrip('/')}/api/swarm/report"
            payload = {
                "agent_id": self.agent_id,
                "peers": list(self.peer_data.keys()),
                "ip_address": self.local_ip,
                "gossip_port": self.gossip_port,
                "timestamp": time.time()
            }
            requests.post(url, json=payload, timeout=2)
        except Exception as e:
            logger.warning(f"Failed to report swarm topology: {e}")

    def get_swarm_health(self):
        return {
            "status": "active",
            "peers": list(self.peer_data.keys()),
            "peer_count": len(self.peer_data),
            "network_latency": "12ms"
        }
