import asyncio
import logging
import os
from datetime import datetime, timezone
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
            
            start_time = datetime.now(timezone.utc)
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
                
            end_time = datetime.now(timezone.utc)
            
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
        # Format "results.node_1.score > 10" or "results.node.verdict == malicious"
        try:
            parts = condition.split()
            if len(parts) == 3:
                left_path = parts[0].split('.')
                operator = parts[1]
                raw_right = parts[2]

                # Coerce right-hand value: try int, then float, then keep as string
                try:
                    right_val: Any = int(raw_right)
                except ValueError:
                    try:
                        right_val = float(raw_right)
                    except ValueError:
                        right_val = raw_right  # string comparison

                # Resolve left-hand path
                val = context
                for p in left_path:
                    if not isinstance(val, dict):
                        return False
                    val = val.get(p, {})

                if operator == '>':  return val > right_val
                if operator == '<':  return val < right_val
                if operator == '>=': return val >= right_val
                if operator == '<=': return val <= right_val
                if operator == '==': return val == right_val
                if operator == '!=': return val != right_val
        except Exception as e:
            logger.error(f"Failed to evaluate condition '{condition}': {e}")
            return False  # Fail closed — unknown/malformed conditions must not pass

        return False  # Unrecognised operator also fails closed

    # --- PLUGINS (Real Integrations) ---

    async def _plugin_enrich_ip_vt(self, data: dict, context: dict):
        ip = data.get("ip", context["trigger"].get("source_ip", "8.8.8.8"))
        try:
            from virustotal_client import get_virustotal_client
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: get_virustotal_client().scan_ip(ip))
            malicious = result.get("malicious", 0) > 0
            score = result.get("malicious", 0) * 10
            return {"malicious": malicious, "score": score, "ip": ip, "verdict": result.get("verdict", "Unknown"), "detectionRatio": result.get("detectionRatio", "0/0")}
        except Exception as e:
            logger.error(f"VT enrich failed for {ip}: {e}")
            return {"malicious": False, "score": 0, "ip": ip, "error": str(e)}

    async def _plugin_block_ip_firewall(self, data: dict, context: dict):
        ip = data.get("ip", context["trigger"].get("source_ip"))
        agent_id = data.get("agent_id", context["trigger"].get("agent_id"))
        logger.warning(f"SOAR ACTION: Blocking IP {ip} via agent {agent_id}")
        if agent_id:
            try:
                from database import mongodb
                import uuid as _uuid
                from datetime import timezone
                instruction = {
                    "id": str(_uuid.uuid4()),
                    "agent_id": agent_id,
                    "type": "block_ip",
                    "parameters": {"ip": ip},
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": "soar"
                }
                await mongodb.db.instructions.insert_one(instruction)
                return {"action": "queued", "ip": ip, "agent_id": agent_id, "instruction_id": instruction["id"]}
            except Exception as e:
                logger.error(f"block_ip dispatch failed: {e}")
                return {"action": "failed", "ip": ip, "error": str(e)}
        return {"action": "skipped", "ip": ip, "reason": "no agent_id provided"}

    async def _plugin_suspend_okta_user(self, data: dict, context: dict):
        user = data.get("username", context["trigger"].get("user", "unknown"))
        okta_domain = os.getenv("OKTA_DOMAIN", "")
        okta_token = os.getenv("OKTA_API_TOKEN", "")
        logger.warning(f"SOAR ACTION: Suspending Okta user {user}")
        if not okta_domain or not okta_token:
            return {"action": "skipped", "user": user, "reason": "OKTA_DOMAIN or OKTA_API_TOKEN not configured"}
        try:
            import httpx
            headers = {"Authorization": f"SSWS {okta_token}", "Accept": "application/json"}
            # Lookup user ID first
            async with httpx.AsyncClient(timeout=10) as client:
                from urllib.parse import quote as _quote
                safe_user = _quote(user, safe="")
                search = await client.get(f"https://{okta_domain}/api/v1/users/{safe_user}", headers=headers)
                if search.status_code != 200:
                    return {"action": "failed", "user": user, "reason": f"User not found: {search.status_code}"}
                user_id = search.json().get("id")
                if not user_id or not isinstance(user_id, str):
                    return {"action": "failed", "user": user, "reason": "Okta returned no user ID"}
                safe_user_id = _quote(user_id, safe="")
                resp = await client.post(f"https://{okta_domain}/api/v1/users/{safe_user_id}/lifecycle/suspend", headers=headers)
                if resp.status_code in (200, 204):
                    return {"action": "suspended", "user": user, "idp": "Okta", "okta_user_id": user_id}
                return {"action": "failed", "user": user, "status": resp.status_code, "detail": resp.text[:200]}
        except Exception as e:
            logger.error(f"Okta suspend failed for {user}: {e}")
            return {"action": "failed", "user": user, "error": str(e)}

    async def _plugin_send_slack_message(self, data: dict, context: dict):
        channel = data.get("channel", "#soc-alerts")
        msg = data.get("message", "Automated SOAR Action Executed")
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        slack_token = os.getenv("SLACK_BOT_TOKEN", "")
        logger.info(f"SOAR ACTION: Sending Slack message to {channel}")
        try:
            import httpx
            if webhook_url:
                async with httpx.AsyncClient(timeout=8) as client:
                    resp = await client.post(webhook_url, json={"channel": channel, "text": msg})
                    return {"action": "messaged", "channel": channel, "status": resp.status_code}
            elif slack_token:
                async with httpx.AsyncClient(timeout=8) as client:
                    resp = await client.post("https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {slack_token}"},
                        json={"channel": channel, "text": msg})
                    result = resp.json()
                    return {"action": "messaged" if result.get("ok") else "failed", "channel": channel, "ts": result.get("ts")}
            else:
                return {"action": "skipped", "channel": channel, "reason": "SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN not configured"}
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return {"action": "failed", "channel": channel, "error": str(e)}

    async def _plugin_isolate_host(self, data: dict, context: dict):
        host_id = data.get("host_id", context["trigger"].get("agent_id"))
        logger.warning(f"SOAR ACTION: Isolating host {host_id}")
        if not host_id:
            return {"action": "skipped", "reason": "no host_id provided"}
        try:
            from database import mongodb
            import uuid as _uuid
            from datetime import timezone
            instruction = {
                "id": str(_uuid.uuid4()),
                "agent_id": host_id,
                "type": "network_isolate",
                "parameters": {"mode": "full"},
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "soar"
            }
            await mongodb.db.instructions.insert_one(instruction)
            await mongodb.db.agents.update_one(
                {"id": host_id},
                {"$set": {"isolated": True, "isolation_time": datetime.now(timezone.utc).isoformat()}}
            )
            return {"action": "isolated", "host_id": host_id, "instruction_id": instruction["id"]}
        except Exception as e:
            logger.error(f"isolate_host failed for {host_id}: {e}")
            return {"action": "failed", "host_id": host_id, "error": str(e)}

# Global engine instance
soar_engine = SOAREngine()
