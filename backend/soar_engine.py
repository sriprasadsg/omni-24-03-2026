import asyncio
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class NodeExecutionError(Exception):
    pass

class SOAREngine:
    """
    A simple DAG (Directed Acyclic Graph) execution engine for SOAR playbooks.
    Executes a JSON definition of steps.
    """
    def __init__(self):
        self.plugins = {
            "enrich_ip_vt": self._plugin_enrich_ip_vt,
            "block_ip_firewall": self._plugin_block_ip_firewall,
            "suspend_okta_user": self._plugin_suspend_okta_user,
            "send_slack_message": self._plugin_send_slack_message,
            "isolate_host": self._plugin_isolate_host
        }

    async def execute_playbook(self, playbook_def: dict, trigger_context: dict) -> dict:
        """
        Executes a playbook given its definition and the initial context (e.g. Alert data).
        """
        run_id = str(uuid.uuid4())
        logger.info(f"Starting playbook run {run_id}: {playbook_def.get('name', 'Unnamed')}")
        
        # execution context passed from node to node
        context = {
            "trigger": trigger_context,
            "results": {}
        }
        
        execution_log = []
        
        nodes = {n['id']: n for n in playbook_def.get('nodes', [])}
        edges = playbook_def.get('edges', [])
        
        # Find start nodes (nodes with no incoming edges)
        target_nodes = set(e['target'] for e in edges)
        start_nodes = [n_id for n_id in nodes.keys() if n_id not in target_nodes]
        
        if not start_nodes:
            logger.warning("No start nodes found in playbook.")
            return {"status": "failed", "reason": "No start node"}

        # Very basic BFS execution (assumes no complex dependencies or parallel wait states for now)
        queue = start_nodes.copy()
        visited = set()
        
        status = "completed"

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
                
            visited.add(current_id)
            node = nodes[current_id]
            node_type = node.get('type')
            
            logger.debug(f"Executing node {current_id} ({node_type})")
            
            start_time = datetime.utcnow()
            node_status = "success"
            error_msg = None
            result = None
            
            try:
                # Execute plugin if it exists
                if node_type in self.plugins:
                    result = await self.plugins[node_type](node.get('data', {}), context)
                    context["results"][current_id] = result
                elif node_type == "trigger":
                    result = context["trigger"]
                else:
                    logger.warning(f"Unknown node type: {node_type}")
                    node_status = "skipped"
                    
            except Exception as e:
                logger.error(f"Error executing node {current_id}: {e}")
                node_status = "failed"
                error_msg = str(e)
                status = "failed"
                # For this basic implementation, halt on failure
                break
                
            end_time = datetime.utcnow()
            
            execution_log.append({
                "node_id": current_id,
                "node_type": node_type,
                "status": node_status,
                "result": result,
                "error": error_msg,
                "duration_ms": (end_time - start_time).total_seconds() * 1000
            })
            
            # Find next nodes
            for edge in edges:
                if edge['source'] == current_id:
                    # Basic conditional edge support (e.g. only follow edge if VT score > 10)
                    condition = edge.get('data', {}).get('condition')
                    if condition:
                        if not self._evaluate_condition(condition, context):
                            continue # Skip this edge
                            
                    queue.append(edge['target'])

        return {
            "run_id": run_id,
            "status": status,
            "log": execution_log,
            "final_context": context
        }

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        # Extremely naive condition evaluator for demo purposes.
        # Format "results.node_1.score > 10"
        try:
            parts = condition.split()
            if len(parts) == 3:
                left_path = parts[0].split('.') # ['results', 'node_1', 'score']
                operator = parts[1]
                right_val = int(parts[2])
                
                # resolve left
                val = context
                for p in left_path:
                    val = val.get(p, {})
                
                if operator == '>': return val > right_val
                if operator == '<': return val < right_val
                if operator == '==': return val == right_val
        except Exception as e:
            logger.error(f"Failed to evaluate condition '{condition}': {e}")
            
        return True # Default to pass if eval fails in demo

    # --- PLUGINS (Mocked Integrations) ---

    async def _plugin_enrich_ip_vt(self, data: dict, context: dict):
        ip = data.get("ip", context["trigger"].get("source_ip", "8.8.8.8"))
        await asyncio.sleep(0.5) # simulate API call
        # Mock VT response
        is_malicious = ip.startswith("192.168") # Fake logic
        return {"malicious": is_malicious, "score": 85 if is_malicious else 0, "ip": ip}

    async def _plugin_block_ip_firewall(self, data: dict, context: dict):
        ip = data.get("ip", context["trigger"].get("source_ip"))
        await asyncio.sleep(0.5)
        logger.warning(f"SOAR ACTION: Blocked IP {ip} on Corporate Firewall")
        return {"action": "blocked", "ip": ip, "firewall": "PaloAlto-HQ"}

    async def _plugin_suspend_okta_user(self, data: dict, context: dict):
        user = data.get("username", context["trigger"].get("user", "unknown"))
        await asyncio.sleep(0.5)
        logger.warning(f"SOAR ACTION: Suspended Okta User {user}")
        return {"action": "suspended", "user": user, "idp": "Okta"}

    async def _plugin_send_slack_message(self, data: dict, context: dict):
        channel = data.get("channel", "#soc-alerts")
        msg = data.get("message", "Automated SOAR Action Executed")
        await asyncio.sleep(0.2)
        logger.info(f"SOAR ACTION: Sent Slack message to {channel}: {msg}")
        return {"action": "messaged", "channel": channel}

    async def _plugin_isolate_host(self, data: dict, context: dict):
        host_id = data.get("host_id", context["trigger"].get("agent_id"))
        await asyncio.sleep(1)
        logger.warning(f"SOAR ACTION: Network Isolated Host {host_id}")
        return {"action": "isolated", "host_id": host_id}

# Global engine instance
soar_engine = SOAREngine()
